import json
from typing import List

from scipy.stats import linregress
import numpy
from matplotlib import pyplot

import common
from evaluation import KValues

repo_test_changes_counts = json.load(open(common.path_relative_to_root("data_collection/raw_data/repository_test_data_counts.json"), 'r'))
repo_test_changes_counts_in_order = [(k, v) for k, v in repo_test_changes_counts.items()]
repo_test_changes_counts_in_order = sorted(repo_test_changes_counts_in_order, key=lambda x: x[1]["changes_count"])

rule_based_results = json.load(open("rule_based_recommender.json", 'r'))
rule_based_top_k = rule_based_results['top-k']
rule_based_mrr = rule_based_results['mrr']

associated_line_of_best_fit_stats = {}

def create_and_save_graph(x, y, ylabel, title, filename, line_label = None) -> List:
    if line_label is None:
        # Use ylabel for line_label if line_label is None
        line_label = ylabel
    pyplot.close()
    pyplot.figure()
    pyplot.plot(x, y, label=line_label)
    p = numpy.poly1d(numpy.polyfit(x, y, 1))
    pyplot.plot(x, p(x), label="Line of best fit", linestyle="dashdot")
    pyplot.legend()
    pyplot.title(title)
    pyplot.ylabel(ylabel)
    pyplot.xlabel("Changes count")
    pyplot.savefig('graphs/' + common.get_sanitised_filename(filename))
    line_of_best_fit_stats = linregress(x, y)
    associated_line_of_best_fit_stats[title] = [line_of_best_fit_stats.slope, line_of_best_fit_stats.rvalue, line_of_best_fit_stats.pvalue]
    return associated_line_of_best_fit_stats[title]

for vote_type in ["approved", "voted"]:
    for top_k_value in KValues.ALL_VALUES:
        x = []
        y = []
        for repo, info in repo_test_changes_counts_in_order:
            if repo not in rule_based_top_k.keys():
                continue
            if "merged" not in rule_based_top_k[repo].keys():
                continue
            if repo == "mediawiki/core":
                continue
            x.append(info["changes_count"])
            y.append(rule_based_top_k[repo]["merged"][vote_type][str(top_k_value)])
        create_and_save_graph(
            x, y, "Top-k score",
            "Top-k scores for " + vote_type + " and k of " + str(top_k_value) + " without mediawiki/core",
            'rule-based-top-k-' + vote_type + '-k-' + str(top_k_value) + '-no-core.png',
            line_label="Top-k score for k = " + str(top_k_value)
        )
        # Add mediawiki/core for next graph
        x.append(repo_test_changes_counts["mediawiki/core"]["changes_count"])
        y.append(rule_based_top_k["mediawiki/core"]["merged"][vote_type][str(top_k_value)])
        create_and_save_graph(
            x, y, "Top-k score",
            "Top-k scores for " + vote_type + " and k of " + str(top_k_value),
            'rule-based-top-k-' + vote_type + '-k-' + str(top_k_value) + '.png',
            line_label="Top-k score for k = " + str(top_k_value)
        )

for vote_type in ["approved", "voted"]:
    x = []
    y = []
    for repo, info in repo_test_changes_counts_in_order:
        if repo not in rule_based_mrr.keys():
            continue
        if "merged" not in rule_based_mrr[repo].keys():
            continue
        if repo == "mediawiki/core":
            continue
        x.append(info["changes_count"])
        y.append(rule_based_mrr[repo]["merged"][vote_type])
    create_and_save_graph(
        x, y, "MRR score",
        "MRR scores for " + vote_type + " without mediawiki/core",
        'rule-based-mrr-' + vote_type + '-no-core.png'
    )
    # Add mediawiki/core for next graph
    x.append(repo_test_changes_counts["mediawiki/core"]["changes_count"])
    y.append(rule_based_mrr["mediawiki/core"]["merged"][vote_type])
    create_and_save_graph(
        x, y, "MRR score",
        "MRR scores for " + vote_type,
        'rule-based-mrr-' + vote_type + '.png'
    )

json.dump(associated_line_of_best_fit_stats, open('rule_based_line_of_best_fit_stats.json', 'w'))