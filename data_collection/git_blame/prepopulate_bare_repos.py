import json
import logging
import time
import common
from data_collection.git_blame import get_bare_repo

if __name__ == "__main__":
    logging.basicConfig(
        filename=common.path_relative_to_root("logs/prepopulate_bare_repos.log.txt"),
        level=logging.DEBUG
    )
    repos_and_associated_members = json.load(open(
        common.path_relative_to_root("data_collection/raw_data/members_of_mediawiki_repos.json")
    ))
    for number_processed, repo in enumerate(repos_and_associated_members['groups_for_repository'].keys()):
        try:
            print("Processed", number_processed, "repos out of", str(len(repos_and_associated_members['groups_for_repository'])) + ". Currently processing", repo)
            logging.info("Processed " + str(number_processed) + " repos. Currently processing " + repo)
            get_bare_repo(repo)
            if number_processed >= 604: # Temp for DEBUG
                time.sleep(1)
        except BaseException as e:
            logging.exception("Failed to download" + repo, exc_info=e)
            pass