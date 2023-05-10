import argparse
import json
import logging
import sys
import pandas

import common
from evaluation import top_k_accuracy_for_repo, mrr_result_for_repo
from recommender.neural_network_recommender.neural_network_recommender import ModelMode, MLPClassifierImplementation, \
    SelectionMode

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
            '--exclude-repo-specific', action='store_true', help="Exclude the repo specific models from evaluation"
        )
        argument_parser.add_argument(
            '--exclude-generic', action='store_true', help="Exclude the generic models from evaluation"
        )
        argument_parser.add_argument(
            '--exclude-open', action='store_true', help="Exclude the open models from evaluation"
        )
        argument_parser.add_argument(
            '--exclude-abandoned', action='store_true', help="Exclude the abandoned models from evaluation"
        )
        argument_parser.add_argument(
            '--exclude-merged', action='store_true', help="Exclude the merged models from evaluation"
        )
        command_line_arguments = argument_parser.parse_args()
        repositories = command_line_arguments.repositories
        branch = command_line_arguments.branch
        num_changes = command_line_arguments.num_changes
        raw = command_line_arguments.raw
        test_models = []
        if not command_line_arguments.exclude_generic:
            test_models.append(ModelMode.GENERIC)
        if not command_line_arguments.exclude_repo_specific:
            test_models.append(ModelMode.REPO_SPECIFIC)
        if not command_line_arguments.exclude_open:
            test_models.append(ModelMode.OPEN)
        if not command_line_arguments.exclude_abandoned:
            test_models.append(ModelMode.ABANDONED)
        if not command_line_arguments.exclude_merged:
            test_models.append(ModelMode.MERGED)
        if not test_models:
            argument_parser.error("The at least one type of model must be evaluated.")
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
            model_mode = input("Please enter the models to evaluate (repo-specific, generic, open, abandoned, merged or all):").strip().lower()
            if not model_mode:
                # Interpret empty as all
                model_mode = "all"
            if model_mode not in ["repo-specific", "generic", "open", "abandoned", "merged", "all"]:
                print("Please select repo-specific, generic, open, abandoned, merged or all for the models to test.")
                continue
            break
        if model_mode == "all":
            test_models = [ModelMode.GENERIC, ModelMode.REPO_SPECIFIC, ModelMode.MERGED, ModelMode.ABANDONED, ModelMode.OPEN]
        else:
            test_models = [ModelMode(model_mode)]
        raw = False
    logging.info("Evaluating with the repos " + str(repositories))
    top_k_accuracies = {}
    mrr_score = {}
    for repository in repositories:
        try:
            print("Evaluating", repository + ":")
            test_data_for_repo = common.get_test_data_for_repo(repository)
            if test_data_for_repo is None:
                # Skip if no test data for repo.
                print("No test data for", repository + ". Skipping.")
                continue
            time_period = test_data_for_repo[0]
            top_k_accuracies[repository] = {}
            mrr_score[repository] = {}
            for model in test_models:
                print(" Evaluating using model type", model.value + ":")
                top_k_accuracies[repository][model.value] = {}
                mrr_score[repository][model.value] = {}
                for selection_mode in SelectionMode:
                    print("  Evaluating using selection mode", selection_mode.value)
                    top_k_accuracies[repository][model.value][selection_mode.value] = top_k_accuracy_for_repo(
                        MLPClassifierImplementation(repository, model, time_period, selection_mode).recommend_using_change_info, repository, num_changes, branch
                    )
                    mrr_score[repository][model.value][selection_mode.value] = mrr_result_for_repo(
                        MLPClassifierImplementation(repository, model, time_period, selection_mode).recommend_using_change_info, repository, num_changes, branch
                    )
        except BaseException as e:
            print("Error:", e)
            logging.error("Error occurred. Moving to next repo.", exc_info=e)
    if raw:
        print({'top-k': top_k_accuracies, 'mrr': mrr_score})
    else:
        try:
            for repository, repository_top_ks in top_k_accuracies.items():
                print("Top K accuracy for repository", repository)
                for model, model_top_ks in repository_top_ks.items():
                    print("Model type:", model)
                    for selection_mode, selection_mode_top_ks in model_top_ks.items():
                        print("Selection mode:", selection_mode)
                        for status, status_top_ks in repository_top_ks.items():
                            print("Patch type:", status)
                            for vote_type, vote_type_top_ks in status_top_ks.items():
                                print("Vote type:", vote_type)
                                print(pandas.DataFrame.from_dict(status_top_ks))
            for repository, repository_mrr in mrr_score.items():
                print("MRR score for repository", repository)
                for model, model_mrr in repository_mrr.items():
                    print("Model type:", model)
                    for selection_mode, selection_mode_mrr in model_mrr.items():
                        print("Selection mode:", selection_mode)
                        print(pandas.DataFrame.from_dict(selection_mode_mrr))
        except BaseException as e:
            pass
    json.dump({'top-k': top_k_accuracies, 'mrr': mrr_score},
              open(common.path_relative_to_root("evaluation/results/neural_network_recommender.json"), 'w'))