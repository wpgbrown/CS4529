"""
Generate LaTeX table definitions for the neural based recommender to be used in the report.
"""
import json
from argparse import ArgumentParser

import common
from evaluation.results.rule_based_results_to_latex_table_format import round_float
from recommender.neural_network_recommender.neural_network_recommender import ModelMode

argument_parser = ArgumentParser(
        description="Prints the evaluation data into LaTeX table form. Used to write the report.")
argument_parser.add_argument('repositories', nargs='*', help="The repositories to filter for")
arguments = argument_parser.parse_args()

# Repo file count metrics
repo_file_counts = json.load(open(common.path_relative_to_root("data_collection/raw_data/repository_file_counts.json"), 'r'))
repo_file_counts_in_order = [(k, v) for k, v in repo_file_counts.items()]
repo_file_counts_in_order = sorted(repo_file_counts_in_order, key=lambda x: x[1])
if len(arguments.repositories):
    print("Only printing data for repos specified in the arguments")
    repo_file_counts_in_order = list(filter(lambda x: x[0] in arguments.repositories, repo_file_counts_in_order))
repo_test_changes_counts = json.load(open(common.path_relative_to_root("data_collection/raw_data/repository_test_data_counts.json"), 'r'))
repo_test_changes_counts_in_order = [(k, v) for k, v in repo_test_changes_counts.items()]
repo_test_changes_counts_in_order = sorted(repo_test_changes_counts_in_order, key=lambda x: x[1]["changes_count"])
if len(arguments.repositories):
    repo_test_changes_counts_in_order = list(filter(lambda x: x[0] in arguments.repositories, repo_test_changes_counts_in_order))

neural_network_testing_after_training_results = json.load(open("neural_network_training_test_results.json", 'r'))
if len(arguments.repositories):
    # Filter for generic and the models for the repositories provided.
    neural_network_testing_after_training_results_temp = {}
    for model_name, data in neural_network_testing_after_training_results.items():
        repository = model_name.split("_")[0].replace('-', '/')
        if repository in arguments.repositories or model_name in ['generic_approved', 'generic_voted']:
            neural_network_testing_after_training_results_temp[model_name] = data
    neural_network_testing_after_training_results = neural_network_testing_after_training_results_temp

# Accuracy score
print("\n\n\n")
print("Accuracy score")
for vote_type in ["approved", "voted"]:
    for appendix in ["", "_open", "_merged", "_abandoned"]:
        for keys in [['average', 'min', 'max'], ['10th-percentile', '90th-percentile']]:
            print("\n\n\n\n")
            print(vote_type, "and", appendix, "and", keys)
            for model_name, data in neural_network_testing_after_training_results.items():
                if 'accuracy_score' not in data:
                    continue
                if not model_name.endswith(vote_type):
                    continue
                if appendix and appendix not in model_name:
                    continue
                if not appendix:
                    try:
                        for appendix_2 in ["_open", "_merged", "_abandoned"]:
                            if appendix_2 in model_name:
                                raise StopIteration
                    except StopIteration:
                        continue
                repository = model_name.split("_")[0].replace('-', '/')
                if repository == "generic":
                    repository = "Generic"
                print(repository, '&', end=' ')
                for key in keys:
                    if key in data['accuracy_score']:
                        if data['accuracy_score'][key] is not None:
                            print(round(data['accuracy_score'][key], 3), end='')
                        else:
                            print("None", end='')
                    if key != keys[-1]:
                        print(' & ', end='')
                    else:
                        print(' \\\\')

# Top-k
evaluation_results = json.load(open("neural_network_recommender.json", 'r'))
top_k_accuracies = evaluation_results['top-k']
mrr_score = evaluation_results['mrr']
for status in [ModelMode.MERGED.value]:
    for vote_type in ["approved", "voted"]:
        for selection_mode in ["in-order"]:
            for model_type in [ModelMode.REPO_SPECIFIC]:
                model_type = model_type.value
                if model_type in [ModelMode.OPEN.value, ModelMode.MERGED.value, ModelMode.ABANDONED.value]:
                    if status != model_type:
                        continue
                print("\n")
                print(status + ",", vote_type + ',', selection_mode, "and", model_type)
                for repository, repository_top_ks in top_k_accuracies.items():
                    if model_type not in repository_top_ks.keys():
                        continue
                    if selection_mode not in repository_top_ks[model_type].keys():
                        continue
                    if status not in repository_top_ks[model_type][selection_mode]:
                        continue
                    if vote_type not in repository_top_ks[model_type][selection_mode][status]:
                        continue
                    if len(arguments.repositories) and repository not in arguments.repositories:
                        continue
                    vote_type_top_ks = repository_top_ks[model_type][selection_mode][status][vote_type]
                    print(repository, end=' ')
                    for top_k_score in vote_type_top_ks.values():
                        print('&', round_float(top_k_score, 3), end=' ')
                    print("\\\\")

# MRR
print("\n\n\n")
print("MRR")
for status in [ModelMode.MERGED.value]:
    for selection_mode in ["in-order"]:
        for model_type in [ModelMode.REPO_SPECIFIC]:
            model_type = model_type.value
            if model_type in [ModelMode.OPEN.value, ModelMode.MERGED.value, ModelMode.ABANDONED.value]:
                if status != model_type:
                    continue
            print("\n")
            print(status + ",", vote_type + ',', selection_mode, "and", model_type)
            for repository, repository_mrr in mrr_score.items():
                if model_type not in repository_mrr.keys():
                    continue
                if not len(repository_mrr[model_type]):
                    continue
                if selection_mode not in repository_mrr[model_type].keys():
                    continue
                if not len(repository_mrr[model_type][selection_mode]):
                    continue
                if status not in repository_mrr[model_type][selection_mode].keys():
                    continue
                if not len(repository_mrr[model_type][selection_mode][status]):
                    continue
                if len(arguments.repositories) and repository not in arguments.repositories:
                    continue
                print(repository, end=' ')
                for vote_type_mrr_score in repository_mrr[model_type][selection_mode][status].values():
                    print('&', round_float(vote_type_mrr_score, 3), end=' ')
                print("\\\\")

# Line of best fit stats
associated_line_of_best_fit_stats = json.load(open('neural_network_line_of_best_fit_stats.json', 'r'))

print("\n\n\n")
print("Line of best fit stats")
for graph_title, stats in associated_line_of_best_fit_stats.items():
    print(graph_title, end=' ')
    for stat in stats:
        print('&', round_float(stat, 3), end=' ')
    print("\\\\")