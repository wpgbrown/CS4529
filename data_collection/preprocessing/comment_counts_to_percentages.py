import json
import logging
import common

logging.basicConfig(filename="logs_for_preprocess_comment_counts_to_percentages.txt", level=logging.DEBUG)

comments_per_repo = json.load(open(common.path_relative_to_root("data_collection/raw_data/comments_by_author_for_repo.json"), 'r'))

percentage_representation = {}

for repo, data_for_repo in comments_per_repo.items():
    percentage_representation[repo] = {}
    for period, data_for_period in data_for_repo.items():
        total = 0
        percentage_representation[repo][period] = {}
        # Tally total of each type of vote
        for reviewer, data_for_author_of_comment in data_for_period.items():
            percentage_representation[repo][period][reviewer] = data_for_author_of_comment["Gerrit comment actions count"]
            total += data_for_author_of_comment["Gerrit comment actions count"]
        # Divide value for each reviewer by the total to get a percentage
        for reviewer in data_for_period.keys():
            percentage_representation[repo][period][reviewer] /= total

json.dump(percentage_representation, open(common.path_relative_to_root("data_collection/raw_data/comment_counts_using_percentages_per_repo.json"), "w"))