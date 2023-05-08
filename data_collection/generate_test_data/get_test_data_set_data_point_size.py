import json

import common

count = 0

repos = list(json.load(open(common.path_relative_to_root("data_collection/raw_data/mediawiki_repos.json"), "r")).keys())
for repo in repos:
    test_data = common.get_test_data_for_repo(repo)
    if test_data is None:
        continue
    for changes in (test_data[1]).values():
        count += len(changes)
print(count)