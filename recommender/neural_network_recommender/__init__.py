import itertools
import pandas
import common
from comment_votes_and_members_of_repos_to_data_frame import preprocess_into_pandas_data_frame
from recommender.rule_based_recommender import RuleBasedImplementation


def add_change_specific_attributes_to_data_frame(repository: str, change_info: dict, data_frame: pandas.DataFrame) -> pandas.DataFrame:
    data_frame = data_frame.copy(True)
    time_period_to_key = {y: y.replace(' ', '_') + "_lines_count" for y in common.TimePeriods.DATE_RANGES}
    # TODO: Fix. Don't use RuleBasedImplementation in the neural network solution. Used to allow access to Base implementation's get_change_git_blame_info
    git_blame_info = RuleBasedImplementation(repository).get_change_git_blame_info(change_info)
    # Get the files modified (added, changed or deleted) by the change
    for name in itertools.chain.from_iterable([
        [y + x for y in common.TimePeriods.DATE_RANGES] for x in
        [" author git blame percentage", " reviewer git blame percentage"]
    ]):
        data_frame[name] = 0
    for time_period, column in {y: y + " author git blame percentage" for y in
                                common.TimePeriods.DATE_RANGES}.items():
        for author_email, percentage in git_blame_info["authors"][time_period_to_key[time_period]].items():
            if author_email in git_blame_info["names"] and len(git_blame_info["names"][author_email]):
                name = git_blame_info["names"][author_email][0]
            else:
                name = author_email
            if name not in data_frame.index.values:
                data_frame.loc[name, :] = 0
            data_frame.at[name, column] = percentage
    for time_period, column in {y: y + " author git blame percentage" for y in
                                common.TimePeriods.DATE_RANGES}.items():
        for committer_email, percentage in git_blame_info["committers"][time_period_to_key[time_period]].items():
            if committer_email in git_blame_info["names"] and len(git_blame_info["names"][committer_email]):
                name = git_blame_info["names"][committer_email][0]
            else:
                name = committer_email
            if name not in data_frame.index.values:
                data_frame.loc[name, :] = 0
            data_frame.at[name, column] = percentage
    return data_frame