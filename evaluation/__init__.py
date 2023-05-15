"""
Common functions used for the evalaution of the implementations.
"""
import copy
import json
import logging
from enum import Enum
from functools import lru_cache
from typing import Callable, Union, List, Tuple
import random

from sklearn.exceptions import NotFittedError

import common
from recommender import Recommendations


class KValues(Enum):
    """
    The values of K used for the valuation using the Top-k metric.
    """
    TOP_1 = 1
    TOP_3 = 3
    TOP_5 = 5
    TOP_10 = 10

def get_reviewers_and_approvers_for_change(change_info: dict) -> Tuple[set, set, set, set]:
    """
    Gets the actual reviewers and approvers on a change given its change information dictionary

    :param change_info: The change info dictionary for the change.
    """
    # Use a set to de-duplicate.
    actual_approvers_names = set()
    actual_reviewers_names = set()
    actual_approvers_emails = set()
    actual_reviewers_emails = set()
    for vote in change_info['code_review_votes']:
        if vote['value'] == 2:
            # If the vote "value" is 2, then this is an approval vote.
            if 'name' in vote:
                actual_approvers_names.add(common.convert_name_to_index_format(vote['name']))
            if 'display_name' in vote:
                actual_approvers_names.add(common.convert_name_to_index_format(vote['display_name']))
            if 'username' in vote:
                actual_approvers_names.add(common.convert_name_to_index_format(vote['username']))
            if 'email' in vote:
                actual_approvers_emails.add(common.convert_email_to_index_format(vote['email']))
        # All votes, including approval votes, are recorded under the reviewers list.
        if 'name' in vote:
            actual_reviewers_names.add(common.convert_name_to_index_format(vote['name']))
        if 'display_name' in vote:
            actual_reviewers_names.add(common.convert_name_to_index_format(vote['display_name']))
        if 'username' in vote:
            actual_reviewers_names.add(common.convert_name_to_index_format(vote['username']))
        if 'email' in vote:
            actual_reviewers_emails.add(common.convert_email_to_index_format(vote['email']))
    return actual_approvers_names, actual_approvers_emails, actual_reviewers_names, actual_reviewers_emails

def top_k_accuracy_for_repo(
        method: Callable[[dict], Recommendations], repository: str, num_changes: int, branch: Union[str, None]
) -> dict[str, dict[str, dict[str, float]]]:
    """
    Performs the Top-k evaluation for the repository using the method provided in the first argument.

    :param method: The method to call to get the recommendations
    :param repository: The repository to perform the Top-k evaluation on
    :param num_changes: The number of changes to analyse to perform Top-k evaluation
    :param branch: The branch these changes should be selected from
    :return: The Top-k accuracy scores
    """
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
        # If the changes in this part of the test data have
        #  one or no changes then skip this.
        sub_test_data = list(sub_test_data.values())
        if len(sub_test_data) <= 1:
            continue
        # Perform Top-k evaluation for the changes with the specified status
        top_k_accuracies_for_repo[status] = {"approved": {}, "voted": {}}
        # Shuffle the data and then take the top "num_changes"
        random.shuffle(sub_test_data)
        if len(sub_test_data) > num_changes:
            sub_test_data = sub_test_data[:num_changes]
        # Prepare the result dictionary for the repository
        top_k_accuracies_for_repo[status] = {}
        top_k_accuracies_for_repo[status]["approved"] = {k.value: 0 for k in KValues}
        top_k_accuracies_for_repo[status]["voted"] = {k.value: 0 for k in KValues}
        try:
            for change_info in sub_test_data:
                # Remove possibility for cheating by the implementations by removing code review votes
                #  and reviewers on change from change_info.
                sanitised_change_info = copy.copy(change_info)
                del sanitised_change_info['code_review_votes']
                del sanitised_change_info['reviewers']
                actual_approvers_names, actual_approvers_emails, actual_reviewers_names, actual_reviewers_emails = get_reviewers_and_approvers_for_change(
                    change_info)
                # Get recommendations from the function/method provided.
                recommendations = method(sanitised_change_info)
                for k in KValues:
                    # Perform the Top-k evaluation for this particular value of k.
                    k = k.value
                    recommended_reviewers = recommendations.top_n(k)
                    # Perform the Top-k evaluation for approvers
                    for reviewer in recommended_reviewers:
                        if any(name for name in reviewer.names if common.convert_name_to_index_format(name) in actual_approvers_names):
                            top_k_accuracies_for_repo[status]["approved"][k] += (1/num_changes)
                            break
                        if any(email for email in reviewer.emails if common.convert_email_to_index_format(email) in actual_approvers_emails):
                            top_k_accuracies_for_repo[status]["approved"][k] += (1/num_changes)
                            break
                    # Perform the Top-k evaluation for voters
                    for reviewer in recommended_reviewers:
                        if any(name for name in reviewer.names if common.convert_name_to_index_format(name) in actual_reviewers_names):
                            top_k_accuracies_for_repo[status]["voted"][k] += (1/num_changes)
                            break
                        if any(email for email in reviewer.emails if common.convert_email_to_index_format(email) in actual_reviewers_emails):
                            top_k_accuracies_for_repo[status]["voted"][k] += (1/num_changes)
                            break
        except NotFittedError as e:
            logging.error("Model not fitted. Skipping this model", exc_info=e)
    return top_k_accuracies_for_repo

def mrr_result_for_repo(method: Callable[[dict], Recommendations], repository: str, num_changes: int, branch: Union[str, None]) -> dict[str, dict[str, float]]:
    """
    Performs MRR results for the repository provided using the method to get the recommendation.

    :param method: The method to call to get the recommendations
    :param repository: The repository to perform the MRR evaluation on
    :param num_changes: The number of changes to analyse to perform MRR evaluation
    :param branch: The branch these changes should be selected from
    :return: The MRR scores
    """
    # MRR results for repositories
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
        # Skip if there are one or no changes in the appropriate part of the training and testing
        #  data set.
        sub_test_data = list(sub_test_data.values())
        if len(sub_test_data) <= 1:
            continue
        mrr_results_for_repo[status] = {}
        # Shuffle the testing data and then select the top "num_changes" changes
        random.shuffle(sub_test_data)
        sub_test_data = sub_test_data[:num_changes]
        mrr_score_for_approved = 0
        mrr_score_for_voted = 0
        try:
            for change_info in sub_test_data:
                # Remove possibility for cheating by removing code review votes and reviewers on change from change_info
                sanitised_change_info = copy.copy(change_info)
                del sanitised_change_info['code_review_votes']
                del sanitised_change_info['reviewers']
                # Get recommendation
                recommended_reviewers = method(sanitised_change_info).recommendations
                actual_approvers_names, actual_approvers_emails, actual_reviewers_names, actual_reviewers_emails = get_reviewers_and_approvers_for_change(change_info)
                # MRR score for approvers
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
                # MRR score for voters
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
            # Perform the rest of the MRR equation.
            mrr_results_for_repo[status]["approved"] = (1 / num_changes) * mrr_score_for_approved
            mrr_results_for_repo[status]["voted"] = (1 / num_changes) * mrr_score_for_voted
        except NotFittedError as e:
            logging.error("Model not fitted. Skipping.", exc_info=e)
    return mrr_results_for_repo

@lru_cache(maxsize=1)
def get_repos_to_use_for_evaluation() -> List[str]:
    """
    Gets repositories used for evaluation.
    """
    return json.load(open(common.path_relative_to_root("data_collection/raw_data/repos_selected_for_evaluation.json"), 'r'))