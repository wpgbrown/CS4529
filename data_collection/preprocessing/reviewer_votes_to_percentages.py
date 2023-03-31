import json
import logging
import common

logging.basicConfig(filename="logs_for_preprocess_reviewer_votes_to_percentages.txt", level=logging.DEBUG)

reviewer_votes = json.load(open(common.path_relative_to_root("data_collection/raw_data/reviewer_votes_for_repos.json"), 'r'))

percentage_representation = {}

vote_types = {
    "Gerrit approval actions count": 0,
    "-2 code review votes": 0,
    "-1 code review votes": 0,
    "1 code review votes": 0,
    "2 code review votes": 0
}

for repo, data_for_repo in reviewer_votes.items():
    percentage_representation[repo] = {}
    for period, data_for_period in data_for_repo.items():
        totals = vote_types
        percentage_representation[repo][period] = {}
        # Tally total of each type of vote
        for reviewer, data_for_reviewer in data_for_period.items():
            percentage_representation[repo][period][reviewer] = data_for_reviewer
            for vote_type in vote_types.keys():
                totals[vote_type] += data_for_reviewer[vote_type]
        # Divide value for each reviewer by the total to get a percentage
        for reviewer in data_for_period.keys():
            for vote_type in vote_types.keys():
                percentage_representation[repo][period][reviewer][vote_type] /= totals[vote_type]

json.dump(percentage_representation, open(common.path_relative_to_root("data_collection/raw_data/reviewer_vote_percentages_for_repos.json"), "w"))