"""
Choose repositories used for the evaluation by randomly selecting the repositories
from the repositories that are under the median change count and above the median change count.
This list is then stored for future reference.
"""
import json
import random
import statistics

import common

repos_and_associated_members = json.load(open(
    common.path_relative_to_root("data_collection/raw_data/members_of_mediawiki_repos.json")
))

repos_selected = []

# Tally number of changes in each repo in the test data set
test_data_change_counts_per_repo = {}
for time_period in common.TimePeriods:
    time_period = time_period.value
    test_data_change_counts_per_repo[time_period] = {}

for number_processed, repository in enumerate(repos_and_associated_members['groups_for_repository'].keys()):
    print("Tallying", repository)
    # Get the test data for the repository to check that the repository could be used
    #  for the evaluation
    test_data = common.get_test_data_for_repo(repository)
    if test_data is None:
        # If the test data is not available, then skip this repository
        continue
    time_period = test_data[0]
    test_data = test_data[1]
    test_data_change_counts_per_repo[time_period][repository] = 0
    for status, sub_test_data in test_data.items():
        test_data_change_counts_per_repo[time_period][repository] += len(sub_test_data)


# Choose repos from each time period based on their counts choosing 10 repositories from
#  those which have change counts under the median and 10 that have change counts over the median
for time_period in common.TimePeriods:
    time_period = time_period.value
    print("Checking", time_period)
    if not len(test_data_change_counts_per_repo[time_period]):
        continue
    median_count_for_time_period = statistics.median(test_data_change_counts_per_repo[time_period].values())
    # Randomly select 5 from below median count
    repos_selected.extend(random.sample(
        [repo for repo, count in test_data_change_counts_per_repo[time_period].items() if count < median_count_for_time_period],
        10))
    # Randomly select 5 from above median count
    repos_selected.extend(random.sample(
        [repo for repo, count in test_data_change_counts_per_repo[time_period].items() if count > median_count_for_time_period],
        10))

# Export this to a JSON file.
json.dump(repos_selected, open(common.path_relative_to_root("data_collection/raw_data/repos_selected_for_evaluation.json"), 'w'))