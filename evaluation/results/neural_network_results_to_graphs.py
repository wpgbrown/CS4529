import itertools
import json

import numpy
from matplotlib import pyplot

import common
from evaluation import KValues
from evaluation.results.rule_based_results_to_graphs import create_and_save_graph
from recommender.neural_network_recommender.neural_network_recommender import ModelMode

repo_test_files_counts = json.load(open(common.path_relative_to_root("data_collection/raw_data/repository_file_counts.json"), 'r'))
repo_test_files_counts_in_order = [(k, v) for k, v in repo_test_files_counts.items()]
repo_test_files_counts_in_order = sorted(repo_test_files_counts_in_order, key=lambda x: x[1])

repo_test_changes_counts = json.load(open(common.path_relative_to_root("data_collection/raw_data/repository_test_data_counts.json"), 'r'))
repo_test_changes_counts_in_order = [(k, v) for k, v in repo_test_changes_counts.items()]
repo_test_changes_counts_in_order = sorted(repo_test_changes_counts_in_order, key=lambda x: x[1]["changes_count"])

neural_network_results = json.load(open("neural_network_recommender.json", 'r'))
neural_network_top_k = neural_network_results['top-k']
neural_network_mrr = neural_network_results['mrr']
neural_network_testing_after_training_results = json.load(open("neural_network_training_test_results.json", 'r'))

model_types_to_appendixes = {
    ModelMode.REPO_SPECIFIC: ['_approved', '_voted'],
    ModelMode.MERGED: ['_merged_approved', '_merged_voted'],
    ModelMode.ABANDONED: ['_abandoned_approved', '_abandoned_voted'],
    ModelMode.OPEN: ['_open_approved', '_open_voted']
}

"""for model_mode, matching_appendixes in model_types_to_appendixes.items():
    # Plot average of accuracy_score
    x = []
    y = []
    for model_name, testing_after_training_results in neural_network_testing_after_training_results.items():
        if model_name in ["generic_voted", "generic_approved"]:
            # Can't graph the generic models as there is only two values.
            continue
        model_name: str
        repository = ''
        for matching_appendix in matching_appendixes:
            if model_name.endswith(matching_appendix):
                if model_mode == ModelMode.REPO_SPECIFIC:
                    # Ensure match was not for _X_approved/_X_voted where X is open, abandoned or merged.
                    for exclude_appendix in itertools.chain(model_types_to_appendixes[ModelMode.OPEN], model_types_to_appendixes[ModelMode.MERGED], model_types_to_appendixes[ModelMode.ABANDONED]):
                        if model_name.endswith(exclude_appendix):
                            break
                    else:
                        repository = model_name.replace(matching_appendix, '').replace('-', '/')
                        break
                else:
                    repository = model_name.replace(matching_appendix, '').replace('-', '/')
                    break
        else:
            # Skip if no appendixes matched.
            continue
        if repository not in repo_test_changes_counts:
            continue
        if testing_after_training_results["accuracy_score"]["average"] is None:
            continue
        # TODO: Graphs with file count and test changes count as x to show neither are a good way to graph?
        # Add to the data to plot.
        x.append(repo_test_changes_counts[repository]["changes_count"])
        y.append(testing_after_training_results["accuracy_score"]["average"])
    # Sort x and y by values of x keeping the x and y paired
    x_and_y = [(x_item, y_item) for x_item, y_item in zip(x, y)]
    x_and_y = sorted(x_and_y, key=lambda x: x[0])
    x = [x for x, _ in x_and_y]
    y = [y for _, y in x_and_y]
    create_and_save_graph(
        x, y, "Average accuracy score",
        "Average accuracy scores for " + model_mode.value + " models",
        'neural-network-avg-accuracy-' + model_mode.value + '.png',
        line_label="Average accuracy score"
    )"""


"""for vote_type in ["approved", "voted"]:
    for top_k_value in KValues.ALL_VALUES:
        for model_mode in ModelMode:
            for selection_mode in ['in-order', 'random', 'semi-random']:
                x = []
                y = []
                for repo, info in repo_test_changes_counts_in_order:
                    if repo not in neural_network_top_k.keys():
                        continue
                    if model_mode.value not in neural_network_top_k[repo].keys():
                        continue
                    if not len(neural_network_top_k[repo][model_mode.value]):
                        continue
                    if selection_mode not in neural_network_top_k[repo][model_mode.value].keys():
                        continue
                    if not len(neural_network_top_k[repo][model_mode.value][selection_mode]):
                        continue
                    if "merged" not in neural_network_top_k[repo][model_mode.value][selection_mode].keys():
                        continue
                    if repo == "mediawiki/core":
                        continue
                    x.append(info["changes_count"])
                    y.append(neural_network_top_k[repo][model_mode.value][selection_mode]["merged"][vote_type][str(top_k_value)])
                if not len(x):
                    continue
                create_and_save_graph(
                    x, y, "Top-k score",
                    "Top-k scores for " + vote_type + ", model type " + model_mode.value + ", selection mode " + selection_mode + ", and k of " + str(top_k_value) + " without mediawiki/core",
                    'neural-network-top-k-' + vote_type + '-k-' + str(top_k_value) + '-model-mode-' + model_mode.value + '-selection-mode-' + selection_mode + '-no-core.png',
                    line_label="Top-k score for k = " + str(top_k_value)
                )
                # Add mediawiki/core for next graph
                # Skip for now.
                # TODO: Remove below after core results generated.
                continue
                x.append(repo_test_changes_counts["mediawiki/core"]["changes_count"])
                y.append(neural_network_top_k["mediawiki/core"][model_mode.value][selection_mode]["merged"][vote_type][str(top_k_value)])
                create_and_save_graph(
                    x, y, "Top-k score",
                    "Top-k scores for " + vote_type + ", model type " + model_mode.value + ", selection mode " + selection_mode + ", and k of " + str(top_k_value),
                    'neural-network-top-k-' + vote_type + '-k-' + str(top_k_value) + '-model-mode-' + model_mode.value + '-selection-mode-' + selection_mode + '.png',
                    line_label="Top-k score for k = " + str(top_k_value)
                )"""

for vote_type in ["approved", "voted"]:
    for model_mode in ModelMode:
        for selection_mode in ['in-order', 'random', 'semi-random']:
            x = []
            y = []
            for repo, info in repo_test_changes_counts_in_order:
                if repo not in neural_network_mrr.keys():
                    continue
                if model_mode.value not in neural_network_mrr[repo].keys():
                    continue
                if not len(neural_network_mrr[repo][model_mode.value]):
                    continue
                if selection_mode not in neural_network_mrr[repo][model_mode.value].keys():
                    continue
                if not len(neural_network_mrr[repo][model_mode.value][selection_mode]):
                    continue
                if "merged" not in neural_network_mrr[repo][model_mode.value][selection_mode].keys():
                    continue
                if vote_type not in neural_network_mrr[repo][model_mode.value][selection_mode]["merged"].keys():
                    continue
                if repo == "mediawiki/core":
                    continue
                x.append(info["changes_count"])
                y.append(neural_network_mrr[repo][model_mode.value][selection_mode]["merged"][vote_type])
            if not len(x):
                continue
            create_and_save_graph(
                x, y, "MRR score",
                "MRR scores for " + vote_type + ", model type " + model_mode.value + ", selection mode " + selection_mode + " without mediawiki/core",
                'neural-network-mrr-' + vote_type + '-model-mode-' + model_mode.value + '-selection-mode-' + selection_mode + '-no-core.png'
            )
            # Add mediawiki/core for next graph
            # TODO: Remove the continue statement when mediawiki/core has results.
            continue
            x.append(repo_test_changes_counts["mediawiki/core"]["changes_count"])
            y.append(neural_network_mrr["mediawiki/core"]["merged"][vote_type])
            create_and_save_graph(
                x, y, "MRR score",
                "MRR scores for " + vote_type + ", model type " + model_mode.value + ", selection mode " + selection_mode,
                'neural-network-mrr-' + vote_type + '-model-mode-' + model_mode.value + '-selection-mode-' + selection_mode + '.png'
            )