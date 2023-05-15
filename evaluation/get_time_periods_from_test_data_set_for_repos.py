"""
Script used to get the number of changes for each repository in the training and testing data set.
Used for the evaluation chapter of the report.
"""
import json
from argparse import ArgumentParser
import common

argument_parser = ArgumentParser(
            description="Outputs the time period and number of changes in the test and training set used for repositories provided in the command line arguments")
argument_parser.add_argument('repositories', nargs='+', help="The repositories")
arguments = argument_parser.parse_args()

repository_test_data_changes_count = {}

for repository in arguments.repositories:
    # Get the changes count for each repository and store the associated
    #  time period too.
    print("Repository", repository, end=': ')
    test_data = common.get_test_data_for_repo(repository)
    if test_data is None:
        print("0 from undefined time period.")
        continue
    changes_count = 0
    for changes in test_data[1].values():
        changes_count += len(changes)
    print(changes_count, "from", test_data[0])
    repository_test_data_changes_count[repository] = {
        "time_period": test_data[0],
        "changes_count": changes_count
    }

# Save to JSON
json.dump(repository_test_data_changes_count, open(common.path_relative_to_root("data_collection/raw_data/repository_test_data_counts.json"), 'w'))