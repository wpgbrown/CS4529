import json
import logging

import common
from data_collection.git_blame import get_bare_repo

logging.basicConfig(filename="logs_for_prepopulate_bare_repos.txt", level=logging.DEBUG)

if __name__ == "__main__":
    repos_and_associated_members = json.load(open(
        common.path_relative_to_root("data_collection/raw_data/members_of_mediawiki_repos.json")))
    for number_processed, repo in enumerate(repos_and_associated_members['groups_for_repository'].keys()):
        print("Processed", number_processed, "repos out of", len(repos_and_associated_members['groups_for_repository']))
        logging.info("Processed " + str(number_processed) + " repos")
        get_bare_repo(repo)