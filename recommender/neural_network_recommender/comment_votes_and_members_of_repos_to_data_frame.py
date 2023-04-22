import logging
import pandas
import numpy
import re
from pathvalidate import sanitize_filename
from sklearn import metrics, preprocessing
import common
from recommender import TimePeriods, get_reviewer_data, get_comment_data, get_members_of_repo, \
    load_members_of_mediawiki_repos

def preprocess_into_pandas_data_frame(repository: str) -> dict[str,pandas.DataFrame]:
    # TODO: Cache using the generated pandas json file?
    return_data = {}
    reviewer_data = get_reviewer_data()[repository]
    for key in TimePeriods.DATE_RANGES:
        match key:
            case TimePeriods.LAST_MONTH:
                key_temp = "last 30 days"
            case TimePeriods.LAST_3_MONTHS:
                key_temp = "last 3 months"
            case TimePeriods.ALL_TIME:
                key_temp = "all"
            case _:
                key_temp = key
        return_data[key] = pandas.DataFrame.from_dict(reviewer_data[key_temp]).transpose()

    comment_data = get_comment_data()[repository]
    for key in TimePeriods.DATE_RANGES:
        match key:
            case TimePeriods.LAST_MONTH:
                key_temp = "last 30 days"
            case TimePeriods.LAST_3_MONTHS:
                key_temp = "last 3 months"
            case TimePeriods.ALL_TIME:
                key_temp = "all"
            case _:
                key_temp = key
        return_data[key]["Comments"] = 0
        for username, comment_count in comment_data[key_temp].items():
            (return_data[key]).at[username, "Comments"] = comment_count

    # TODO: Git change stats here?
    # TODO: Take into account git blame stats per change when training, testing and recommending

    users_with_rights_to_merge = get_members_of_repo(repository)
    logging.debug("users with right to merge: " + str(users_with_rights_to_merge))
    for data_frame in return_data.values():
        data_frame: pandas.DataFrame
        data_frame["Can merge changes?"] = False
        for user in users_with_rights_to_merge:
            if 'email' in user and user['email'] in data_frame.index:
                data_frame.at[user['email'], "Can merge changes?"] = True
            elif 'name' in user and user['name'] in data_frame.index:
                data_frame.at[user['name'], "Can merge changes?"] = True
            elif 'username' in user and user['username'] in data_frame.index:
                data_frame.at[user['username'], "Can merge changes?"] = True
            elif 'display_name' in user and user['display_name'] in data_frame.index:
                data_frame.at[user['display_name'], "Can merge changes?"] = True
            elif 'name' in user:
                data_frame.at[user['name'], "Can merge changes?"] = True
    return return_data

if __name__ == "__main__":
    logging.basicConfig(filename=common.path_relative_to_root("logs/preprocess_into_data_frame.log.txt"), level=logging.DEBUG)
    repos_and_associated_members = load_members_of_mediawiki_repos()
    for repo in repos_and_associated_members['groups_for_repository'].keys():
        logging.debug("Preprocesing repo " + repo)
        print("Processing", repo)
        for time_period, data_frame in preprocess_into_pandas_data_frame(repo).items():
            data_frame.to_json(open(common.path_relative_to_root(
                "data_collection/raw_data/pandas_data_frames/" + sanitize_filename(
                    re.sub(r'/', '-', repo)) + '-' + sanitize_filename(time_period) + '.json'
            ), 'w'))