import json
import logging
import common

logging.basicConfig(filename="preprocess_reviewer_votes_to_percentages.txt", level=logging.DEBUG)

reviewer_votes = json.load(open(common.path_relative_to_root("data_collection/raw_data/reviewer_votes_for_repos.json"), 'r'))

percentage_representation = {}

totals = {
    "Gerrit approval actions count": 0,
    "-2 code review votes": 0,
    "-1 code review votes": 0,
    "1 code review votes": 0,
    "2 code review votes": 0
}

for repo, data_for_repo in reviewer_votes.items():
    for period, data_for_period in data_for_repo.items():
        for data_for_reviewer in data_for_period.values():
            total