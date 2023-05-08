import argparse
import json
import logging
import sys
import pandas

import common
from evaluation import top_k_accuracy_for_repo, mrr_result_for_repo
from recommender.rule_based_recommender import RuleBasedImplementation

if __name__ == "__main__":
    if len(sys.argv) > 1:
        argument_parser = argparse.ArgumentParser(
            description="The evaluation script for the rule based recommender")
        argument_parser.add_argument('repositories', nargs='+', help="The repositories to evaluate")
        argument_parser.add_argument(
            '--num-changes', help="The number of changes to randomly select to test with. If less than this number of changes exist in the test data set, no more changes are requested from the server to fill this.", required=False, default=150, type=int
        )
        argument_parser.add_argument(
            '--branch', help="Only test using changes from this branch", default=None, required=False, type=str
        )
        argument_parser.add_argument(
            '--raw', action='store_true', help="Return results as the raw result dictionary"
        )
        command_line_arguments = argument_parser.parse_args()
        repositories = command_line_arguments.repositories
        branch = command_line_arguments.branch
        num_changes = command_line_arguments.num_changes
        raw = command_line_arguments.raw
    else:
        repositories = [input("Please enter the repository:").strip()]
        branch = input("Please enter the branch (empty for no branch filtering):").strip()
        if not branch:
            branch = None
        while True:
            try:
                num_changes = input("Please enter the number of changes to process (empty for 100):").strip()
                if not num_changes:
                    num_changes = 100
                num_changes = int(num_changes)
                break
            except ValueError:
                print("Number of changes was not an integer. Please try again.")
        raw = False
    logging.info("Evaluating with the repos " + str(repositories))
    top_k_accuracies = {}
    mrr_score = {}
    try:
        for repository in repositories:
            print("Evaluating", repository)
            top_k_accuracies[repository] = top_k_accuracy_for_repo(
                RuleBasedImplementation(repository).recommend_using_change_info, repository, num_changes, branch
            )
            mrr_score[repository] = mrr_result_for_repo(
                RuleBasedImplementation(repository).recommend_using_change_info, repository, num_changes, branch
            )
    except BaseException as e:
        print("Error:", e)
        logging.error("Error occurred. Exiting early.", exc_info=e)
    if raw:
        print({'top-k': top_k_accuracies, 'mrr': mrr_score})
    else:
        for repository, repository_top_ks in top_k_accuracies.items():
            print("Top K accuracy for repository", repository)
            for status, status_top_ks in repository_top_ks.items():
                print("Patch type:", status)
                for vote_type, vote_type_top_ks in status_top_ks.items():
                    print("Vote type:", vote_type)
                    print(pandas.DataFrame.from_dict(status_top_ks))
        for repository, repository_mrr in mrr_score.items():
            print("MRR score for repository", repository)
            print(pandas.DataFrame.from_dict(repository_mrr))
    json.dump({'top-k': top_k_accuracies, 'mrr': mrr_score}, open(common.path_relative_to_root("evaluation/results/rule_based_recommender.json"), 'w'))