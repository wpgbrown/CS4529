import json
import statistics
from argparse import ArgumentParser

import numpy

import common
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


# Accuracy score

# Top-k
evaluation_results = json.load(open("neural_network_recommender.json", 'r'))
top_k_accuracies = evaluation_results['top-k']
mrr_score = evaluation_results['mrr']
for status in [ModelMode.OPEN.value, ModelMode.MERGED.value, ModelMode.ABANDONED.value]:
    for vote_type in ["approved", "voted"]:
        print("\n\n\n")
        print("Status:", status)
        print("Vote type:", vote_type)
        for repository, repository_top_ks in top_k_accuracies.items():
            if status not in repository_top_ks:
                continue
            if vote_type not in repository_top_ks[status]:
                continue
            if len(arguments.repositories) and repository not in arguments.repositories:
                continue
            vote_type_top_ks = repository_top_ks[status][vote_type]
            print(repository, end=' ')
            for top_k_score in vote_type_top_ks.values():
                print('&', round(top_k_score, 3), end=' ')
            print("\\\\")

for status in [ModelMode.OPEN.value, ModelMode.MERGED.value, ModelMode.ABANDONED.value]:
    print("\n\n\n")
    print("Status:", status)
    for repository, repository_mrr in mrr_score.items():
        if status not in repository_mrr:
            continue
        if len(arguments.repositories) and repository not in arguments.repositories:
            continue
        print(repository, end=' ')
        for vote_type_mrr_score in repository_mrr[status].values():
            print('&', round(vote_type_mrr_score, 3), end=' ')
        print("\\\\")