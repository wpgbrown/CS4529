"""
Converts the comment count data collected into a percentage form
where each author's comment counts are divided by the sum of the comment
counts from all users.
"""
import json
import logging
import common

def convert_data_to_percentages():
    """
    Convert the comment data to percentages by reading the JSON file for the comment data
    and then saving a JSON file with the percentage representations.
    """
    comments_per_repo = json.load(
        open(common.path_relative_to_root("data_collection/raw_data/comments_by_author_for_repo.json"), 'r'))
    percentage_representation = {}
    for repo, data_for_repo in comments_per_repo.items():
        # Perform this separately for each repo in the comment count data set.
        percentage_representation[repo] = {}
        for period, data_for_period in data_for_repo.items():
            total = 0
            percentage_representation[repo][period] = {}
            # Tally comment counts
            for reviewer, data_for_author_of_comment in data_for_period.items():
                percentage_representation[repo][period][reviewer] = data_for_author_of_comment["Gerrit comment actions count"]
                total += data_for_author_of_comment["Gerrit comment actions count"]
            # Divide value for each reviewer by the total to get a percentage
            for reviewer in data_for_period.keys():
                percentage_representation[repo][period][reviewer] /= total
    json.dump(percentage_representation, open(common.path_relative_to_root("data_collection/raw_data/comment_count_percentages_by_author_for_repo.json"), "w"))

if __name__ == "__main__":
    logging.basicConfig(
        filename=common.path_relative_to_root("logs/comment_counts_to_percentages.log.txt"),
        level=logging.DEBUG
    )
    convert_data_to_percentages()