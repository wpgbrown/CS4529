import itertools
import logging
from typing import List

import pandas
import common
from recommender import get_reviewer_data, get_comment_data, get_members_of_repo, RecommenderImplementation, \
    RecommenderImplementationBase

class MLPClassifierImplementationBase(RecommenderImplementationBase):
    @staticmethod
    def preprocess_into_pandas_data_frame(repository: str) -> dict[str, pandas.DataFrame]:
        return_data = {}
        reviewer_data = get_reviewer_data()[repository]
        for key in common.TimePeriods.DATE_RANGES:
            return_data[key] = pandas.DataFrame.from_dict(reviewer_data[key]).transpose()
            return_data[key].rename(index={x: x.strip() for x in return_data[key].index.array})
            for username in common.username_exclude_list:
                username = common.convert_name_to_index_format(username)
                if username in return_data[key].index:
                    return_data[key].drop(username)

        index_form_to_data_frame_username = {
            key: {common.convert_name_to_index_format(name): name for name in return_data[key].index} for key in common.TimePeriods.DATE_RANGES
        }

        comment_data = get_comment_data()[repository]
        for key in common.TimePeriods.DATE_RANGES:
            return_data[key]["Comments"] = 0
            for username, comment_count in comment_data[key].items():
                if common.convert_name_to_index_format(username) in common.username_exclude_list:
                    continue
                index_form_username = common.convert_name_to_index_format(username)
                if index_form_username in index_form_to_data_frame_username[key].keys():
                    username = index_form_to_data_frame_username[key][index_form_username]
                else:
                    # Username doesn't exist. Add it.
                    (return_data[key]).loc[username] = 0
                    # Add it to the index
                    index_form_to_data_frame_username[key][index_form_username] = username
                (return_data[key]).at[username.strip(), "Comments"] = comment_count
        users_with_rights_to_merge = get_members_of_repo(repository)
        logging.debug("users with right to merge: " + str(users_with_rights_to_merge))
        for key, data_frame in return_data.items():
            data_frame: pandas.DataFrame
            data_frame["Can merge changes?"] = False
            for user in users_with_rights_to_merge:
                def mark_as_can_merge_changes(key_for_user: str):
                    if key_for_user in user:
                        username_index_form = common.convert_name_to_index_format(user[key_for_user])
                        if username_index_form in index_form_to_data_frame_username[key].keys():
                            username = index_form_to_data_frame_username[key][username_index_form]
                            data_frame.at[username, "Can merge changes?"] = True
                            return True
                    return False
                for key_for_name in ['name', 'display_name', 'username']:
                    if mark_as_can_merge_changes(key_for_name):
                        break
                else:
                    username = user['name']
                    # Add the user with the right to merge to the data frame.
                    (return_data[key]).loc[username] = 0
                    data_frame.at[username, "Can merge changes?"] = True
                    # Add it to the index
                    index_form_to_data_frame_username[key][common.convert_name_to_index_format(username)] = username
        return return_data

    @classmethod
    def add_change_specific_attributes_to_data_frame(cls, repository: str, change_info: dict, data_frame: pandas.DataFrame) -> pandas.DataFrame:
        data_frame = data_frame.copy(True)
        time_period_to_key = {y: y.replace(' ', '_') + "_lines_count" for y in common.TimePeriods.DATE_RANGES}
        index_form_to_data_frame_username = {
            common.convert_name_to_index_format(name): name for name in data_frame.index
        }
        git_blame_info = cls.get_change_git_blame_info(repository, change_info)
        # Get the files modified (added, changed or deleted) by the change
        for name in itertools.chain.from_iterable([
            [y + x for y in common.TimePeriods.DATE_RANGES] for x in
            [" author git blame percentage", " reviewer git blame percentage"]
        ]):
            data_frame[name] = 0
        def is_a_name_used_in_data_frame(names: List[str]):
            for name in names:
                # De-duplicate by using index format to find similar usernames that
                #  are almost certainly the same person.
                name_index_form = common.convert_name_to_index_format(name)
                if name_index_form in index_form_to_data_frame_username.keys():
                    return index_form_to_data_frame_username[name_index_form]
            return False
        for time_period, column in {y: y + " author git blame percentage" for y in
                                    common.TimePeriods.DATE_RANGES}.items():
            for author_email, percentage in git_blame_info["authors"][time_period_to_key[time_period]].items():
                if author_email in git_blame_info["names"] and len(git_blame_info["names"][author_email]):
                    data_frame_name = is_a_name_used_in_data_frame(git_blame_info["names"][author_email])
                    if not data_frame_name:
                        # If the data frame doesn't have any of the names, then use the first name
                        data_frame_name = git_blame_info["names"][author_email][0]
                else:
                    # Shouldn't occur, but use email if no name was given for the commit.
                    data_frame_name = author_email
                if data_frame_name not in data_frame.index.values:
                    data_frame.loc[data_frame_name, :] = 0
                data_frame.at[data_frame_name, column] = percentage
        for time_period, column in {y: y + " reviewer git blame percentage" for y in
                                    common.TimePeriods.DATE_RANGES}.items():
            for committer_email, percentage in git_blame_info["committers"][time_period_to_key[time_period]].items():
                if committer_email in git_blame_info["names"] and len(git_blame_info["names"][committer_email]):
                    data_frame_name = is_a_name_used_in_data_frame(git_blame_info["names"][committer_email])
                    if not data_frame_name:
                        # If the data frame doesn't have any of the names, then use the first name
                        data_frame_name = git_blame_info["names"][committer_email][0]
                else:
                    # Shouldn't occur, but use email if no name was given for the commit.
                    data_frame_name = committer_email
                if data_frame_name not in data_frame.index.values:
                    data_frame.loc[data_frame_name, :] = 0
                data_frame.at[data_frame_name, column] = percentage
        return data_frame