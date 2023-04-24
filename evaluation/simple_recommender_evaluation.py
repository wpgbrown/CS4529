import argparse
import copy
import logging
import random

from sklearn.model_selection import train_test_split
import common
from recommender.simple_recommender import recommend_reviewers_for_patch_using_change_info

if __name__ == "__main__":
    argument_parser = argparse.ArgumentParser(
        description="The evaluation script for the simple recommender")
    argument_parser.add_argument('repositories', nargs='+', help="The repositories to evaluate")
    argument_parser.add_argument(
        '--num_changes', help="The number of changes to randomly select to test with", required=False, default=100, type=int
    )
    argument_parser.add_argument(
        '--branch', help="Only test using changes from this branch", default=None, required=False, type=str
    )
    command_line_arguments = argument_parser.parse_args()
    repositories = command_line_arguments.repositories
    branch = command_line_arguments.branch
    num_changes = command_line_arguments.num_changes
    logging.info("Evaluating with the repos " + str(repositories))
    for repository in repositories:
        test_data = common.get_test_data_for_repo(repository)
        time_period = test_data[0]
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
            random.shuffle(sub_test_data)
            sub_test_data = sub_test_data[:num_changes]
            for change_info in sub_test_data:
                # Remove possibility for cheating by removing code review votes and reviewers on change from change_info
                sanitised_change_info = copy.copy(change_info)
                del sanitised_change_info['code_review_votes']
                del sanitised_change_info['reviewers']
                # Get recommendation
                recommended_reviewers = recommend_reviewers_for_patch_using_change_info(repository, sanitised_change_info)
                actual_approvers = [vote['name'] for vote in change_info['code_review_votes'] if vote['value'] == 2]
                actual_reviewers = [vote['name'] for vote in change_info['code_review_votes'] if vote['value'] != 2]
                score = 0
                for approver in actual_approvers:
                    if recommended_reviewers.get_reviewer_by_name(approver):
                        score += 1
                for reviewer in actual_reviewers:
                    if recommended_reviewers.get_reviewer_by_name(reviewer):
                        score += 0.5
                print(score)