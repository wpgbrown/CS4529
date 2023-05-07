import copy
import json
import logging
from functools import lru_cache
from typing import Callable, Union, List, Tuple
import random
import common
from recommender import Recommendations


class KValues:
    TOP_1 = 1
    TOP_3 = 3
    TOP_5 = 5
    TOP_10 = 10
    ALL_VALUES = [TOP_1, TOP_3, TOP_5, TOP_10]

def get_reviewers_and_approvers_for_change(change_info: dict) -> Tuple[set, set, set, set]:
    actual_approvers_names = set()
    actual_reviewers_names = set()
    actual_approvers_emails = set()
    actual_reviewers_emails = set()
    for vote in change_info['code_review_votes']:
        if vote['value'] == 2:
            if 'name' in vote:
                actual_approvers_names.add(common.convert_name_to_index_format(vote['name']))
            if 'display_name' in vote:
                actual_approvers_names.add(common.convert_name_to_index_format(vote['display_name']))
            if 'username' in vote:
                actual_approvers_names.add(common.convert_name_to_index_format(vote['username']))
            if 'email' in vote:
                actual_approvers_emails.add(common.convert_email_to_index_format(vote['email']))
        if 'name' in vote:
            actual_reviewers_names.add(common.convert_name_to_index_format(vote['name']))
        if 'display_name' in vote:
            actual_reviewers_names.add(common.convert_name_to_index_format(vote['display_name']))
        if 'username' in vote:
            actual_reviewers_names.add(common.convert_name_to_index_format(vote['username']))
        if 'email' in vote:
            actual_reviewers_emails.add(common.convert_email_to_index_format(vote['email']))
    return actual_approvers_names, actual_approvers_emails, actual_reviewers_names, actual_reviewers_emails

def top_k_accuracy_for_repo(method: Callable[[dict], Recommendations], repository: str, num_changes: int, branch: Union[str, None]) -> dict[str, dict[str, dict[str, float]]]:
    top_k_accuracies_for_repo = {}
    test_data = common.get_test_data_for_repo(repository)
    test_data = test_data[1]
    for status, sub_test_data in test_data.items():
        logging.debug("Status: " + status)
        if branch is not None:
            # Filter for changes from the specified branch only
            test_data = {k: v for k, v in sub_test_data.items() if v['branch'] == branch}
        # Use test_train_split to shuffle appropriately and then select the first "num_changes" changes as the test data
        for change_id in sub_test_data.keys():
            sub_test_data[change_id]["id"] = change_id
        sub_test_data = list(sub_test_data.values())
        if len(sub_test_data) <= 1:
            continue
        top_k_accuracies_for_repo[status] = {"approved": {}, "voted": {}}
        for k in KValues.ALL_VALUES:
            random.shuffle(sub_test_data)
            if len(sub_test_data) > num_changes:
                sub_test_data = sub_test_data[:num_changes]
            top_k_score_for_approved = 0
            top_k_score_for_voted = 0
            for change_info in sub_test_data:
                # Remove possibility for cheating by removing code review votes and reviewers on change from change_info
                sanitised_change_info = copy.copy(change_info)
                del sanitised_change_info['code_review_votes']
                del sanitised_change_info['reviewers']
                # Get recommendations
                recommended_reviewers = method(sanitised_change_info).top_n(k)
                actual_approvers_names, actual_approvers_emails, actual_reviewers_names, actual_reviewers_emails = get_reviewers_and_approvers_for_change(change_info)
                for reviewer in recommended_reviewers:
                    if any(name for name in reviewer.names if common.convert_name_to_index_format(name) in actual_approvers_names):
                        top_k_score_for_approved += 1
                        break
                    if any(email for email in reviewer.emails if common.convert_email_to_index_format(email) in actual_approvers_emails):
                        top_k_score_for_approved += 1
                        break
                for reviewer in recommended_reviewers:
                    if any(name for name in reviewer.names if common.convert_name_to_index_format(name) in actual_reviewers_names):
                        top_k_score_for_voted += 1
                        break
                    if any(email for email in reviewer.emails if common.convert_email_to_index_format(email) in actual_reviewers_emails):
                        top_k_score_for_approved += 1
                        break
            top_k_accuracies_for_repo[status]["approved"][k] = top_k_score_for_approved / num_changes
            top_k_accuracies_for_repo[status]["voted"][k] = top_k_score_for_approved / num_changes
    return top_k_accuracies_for_repo

def mrr_result_for_repo(method: Callable[[dict], Recommendations], repository: str, num_changes: int, branch: Union[str, None]) -> dict[str, dict[str, float]]:
    mrr_results_for_repo = {}
    test_data = common.get_test_data_for_repo(repository)
    test_data = test_data[1]
    for status, sub_test_data in test_data.items():
        logging.debug("Status: " + status)
        if branch is not None:
            # Filter for changes from the specified branch only
            test_data = {k: v for k, v in sub_test_data.items() if v['branch'] == branch}
        # Use test_train_split to shuffle appropriately and then select the first "num_changes" changes as the test data
        for change_id in sub_test_data.keys():
            sub_test_data[change_id]["id"] = change_id
        sub_test_data = list(sub_test_data.values())
        if len(sub_test_data) <= 1:
            continue
        mrr_results_for_repo[status] = {}
        random.shuffle(sub_test_data)
        sub_test_data = sub_test_data[:num_changes]
        mrr_score_for_approved = 0
        mrr_score_for_voted = 0
        for change_info in sub_test_data:
            # Remove possibility for cheating by removing code review votes and reviewers on change from change_info
            sanitised_change_info = copy.copy(change_info)
            del sanitised_change_info['code_review_votes']
            del sanitised_change_info['reviewers']
            # Get recommendation
            # TODO: Limit to top-n?
            recommended_reviewers = method(sanitised_change_info).recommendations
            actual_approvers_names, actual_approvers_emails, actual_reviewers_names, actual_reviewers_emails = get_reviewers_and_approvers_for_change(change_info)
            for position, reviewer in enumerate(recommended_reviewers):
                if any(name for name in reviewer.names if common.convert_name_to_index_format(name) in actual_approvers_names):
                    mrr_score_for_approved += 1/(position+1)
                    break
                if any(email for email in reviewer.emails if common.convert_email_to_index_format(email) in actual_approvers_emails):
                    mrr_score_for_approved += 1/(position+1)
                    break
            else:
                # If no recommended reviewer actually approved, then use the length of the list
                mrr_score_for_approved += 1/len(recommended_reviewers)
            for position, reviewer in enumerate(recommended_reviewers):
                if any(name for name in reviewer.names if common.convert_name_to_index_format(name) in actual_reviewers_names):
                    mrr_score_for_voted += 1/(position+1)
                    break
                if any(email for email in reviewer.emails if common.convert_email_to_index_format(email) in actual_reviewers_emails):
                    mrr_score_for_approved += 1/(position+1)
                    break
            else:
                # If no recommended reviewer actually approved, then use the length of the list
                mrr_score_for_voted += 1/len(recommended_reviewers)
        mrr_results_for_repo[status]["approved"] = (1 / num_changes) * mrr_score_for_approved
        mrr_results_for_repo[status]["voted"] = (1 / num_changes) * mrr_score_for_voted
    return mrr_results_for_repo

@lru_cache(maxsize=1)
def get_repos_to_use_for_evaluation() -> List[str]:
    return json.load(open(common.path_relative_to_root("data_collection/raw_data/repos_selected_for_evaluation.json"), 'r'))