import argparse
import logging
import sys
import pandas

from common import TimePeriods
from evaluation import top_k_accuracy_for_repo
from recommender.neural_network_recommender.neural_network_recommender import ModelMode, MLPClassifierImplementation

if __name__ == "__main__":
    if len(sys.argv) > 1:
        argument_parser = argparse.ArgumentParser(
            description="The evaluation script for the neural network recommender")
        argument_parser.add_argument('repositories', nargs='+', help="The repositories to evaluate")
        argument_parser.add_argument(
            '--num-changes', help="The number of changes to randomly select to test with", required=False, default=100, type=int
        )
        argument_parser.add_argument(
            '--branch', help="Only test using changes from this branch", default=None, required=False, type=str
        )
        argument_parser.add_argument(
            '--raw', action='store_true', help="Return results as the raw result dictionary"
        )
        argument_parser.add_argument(
            '--raw', action='store_true', help="Return results as the raw result dictionary"
        )
        argument_parser.add_argument(
            '--exclude-repo-specific', action='store_true', help="Exclude the repo specific models from evaluation"
        )
        argument_parser.add_argument(
            '--exclude-generic', action='store_true', help="Exclude the generic models from evaluation"
        )
        command_line_arguments = argument_parser.parse_args()
        repositories = command_line_arguments.repositories
        branch = command_line_arguments.branch
        num_changes = command_line_arguments.num_changes
        raw = command_line_arguments.raw
        test_models = []
        if not command_line_arguments.exclude_repo_specific:
            test_models.append(ModelMode.REPO_SPECIFIC)
        if not command_line_arguments.exclude_generic:
            test_models.append(ModelMode.GENERIC)
        # TODO: Handle open/abandoned/merged models
        if not test_models:
            argument_parser.error("The arguments exclude-repo-specific and exclude-generic cannot both be used.")
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
        while True:
            model_mode = input("Please enter the models to evaluate (repo-specific, generic, or both):").strip().lower()
            if not model_mode:
                # Interpret empty as both
                model_mode = "both"
            if model_mode not in ["repo-specific", "generic", "both"]:
                print("Please select repo-specific, generic or both for the models to test.")
                continue
            break
        match model_mode:
            # TODO: Handle open/abandoned/merged model types?
            case "both":
                test_models = [ModelMode.REPO_SPECIFIC, ModelMode.GENERIC]
            case "repo-specific":
                test_models = [ModelMode.REPO_SPECIFIC]
            case "generic":
                test_models = [ModelMode.GENERIC]
            case _:
                # Should never occur, but just in case add a default condition.
                test_models = ModelMode.DEFAULT
        raw = False
    logging.info("Evaluating with the repos " + str(repositories))
    top_k_accuracies = {}
    for repository in repositories:
        for model in test_models:
            # TODO: Allow custom time period here
            top_k_accuracies[repository][model] = top_k_accuracy_for_repo(
                MLPClassifierImplementation(repository, model, TimePeriods.LAST_YEAR).recommend_using_change_info, repository, num_changes, branch
            )
    if raw:
        print(top_k_accuracies)
    else:
        for repository, repository_top_ks in top_k_accuracies.items():
            print("Top K accuracy for repository", repository)
            for status, status_top_ks in repository_top_ks.items():
                print("Patch type:", status)
                for vote_type, vote_type_top_ks in status_top_ks.items():
                    print("Vote type:", vote_type)
                    print(pandas.DataFrame.from_dict(status_top_ks))