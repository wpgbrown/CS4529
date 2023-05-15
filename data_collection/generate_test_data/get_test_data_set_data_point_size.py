"""
Generates the number of changes in the training and testing data set by loading it and then
counting values.
"""
import json

import common

count = 0

repos = list(json.load(open(common.path_relative_to_root("data_collection/raw_data/mediawiki_repos.json"), "r")).keys())
for repo in repos:
    # Load and then count the data for each repository one by one
    #  as loading the entire data set would use a lot of memory.
    test_data = common.get_test_data_for_repo(repo)
    if test_data is None:
        continue
    for changes in (test_data[1]).values():
        count += len(changes)

# Print the count out. Used as a script to only generate a number for the report, so this doesn't need
#  a better output method.
print(count)
