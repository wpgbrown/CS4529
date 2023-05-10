import json
import statistics

import numpy

import common
from recommender.neural_network_recommender.neural_network_recommender import ModelMode

# Repo file count metrics
repo_file_counts = json.load(open(common.path_relative_to_root("data_collection/raw_data/repository_file_counts.json"), 'r'))
repo_file_counts_in_order = [(k, v) for k, v in repo_file_counts.items()]
repo_file_counts_in_order = sorted(repo_file_counts_in_order, key=lambda x: x[1])
repo_test_changes_counts = json.load(open(common.path_relative_to_root("data_collection/raw_data/repository_test_data_counts.json"), 'r'))
repo_test_changes_counts_in_order = [(k, v) for k, v in repo_test_changes_counts.items()]
repo_test_changes_counts_in_order = sorted(repo_test_changes_counts_in_order, key=lambda x: x[1]["changes_count"])

min_file_count = min(repo_file_counts_in_order, key=lambda x: x[1])
min_changes_count = min(repo_test_changes_counts_in_order, key=lambda x: x[1]["changes_count"])
print("Minimum &", min_file_count[1], "&", min_changes_count[1]["changes_count"], "\\\\")
max_file_count = max(repo_file_counts_in_order, key=lambda x: x[1])
max_changes_count = max(repo_test_changes_counts_in_order, key=lambda x: x[1]["changes_count"])
print("Maximum &", max_file_count[1], "&", max_changes_count[1]["changes_count"], "\\\\")
mode_file_count = statistics.mode([x[1] for x in repo_file_counts_in_order])
mode_changes_count = statistics.mode([x[1]["changes_count"] for x in repo_test_changes_counts_in_order])
print("Mode &", mode_file_count, "&", mode_changes_count, "\\\\")
median_file_count = statistics.median([x[1] for x in repo_file_counts_in_order])
median_changes_count = statistics.median([x[1]["changes_count"] for x in repo_test_changes_counts_in_order])
print("Median &", int(median_file_count), "&", int(median_changes_count), "\\\\")
ten_percentile_file_count = numpy.percentile([x[1] for x in repo_file_counts_in_order], 10)
ten_percentile_changes_count = numpy.percentile([x[1]["changes_count"] for x in repo_test_changes_counts_in_order], 10)
print("10th percentile &", int(ten_percentile_file_count), "&", int(ten_percentile_changes_count), "\\\\")
ninety_percentile_file_count = numpy.percentile([x[1] for x in repo_file_counts_in_order], 90)
ninety_percentile_changes_count = numpy.percentile([x[1]["changes_count"] for x in repo_test_changes_counts_in_order], 90)
print("90th percentile &", int(ninety_percentile_file_count), "&", int(ninety_percentile_changes_count), "\\\\")

# Top-k
evaluation_results = json.load(open("rule_based_recommender.json", 'r'))
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
        print(repository, end=' ')
        for vote_type_mrr_score in repository_mrr[status].values():
            print('&', round(vote_type_mrr_score, 3), end=' ')
        print("\\\\")