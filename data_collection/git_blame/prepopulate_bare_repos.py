import json
import logging
import time
from argparse import ArgumentParser

import common
from data_collection.git_blame import get_bare_repo

if __name__ == "__main__":
    logging.basicConfig(
        filename=common.path_relative_to_root("logs/prepopulate_bare_repos.log.txt"),
        level=logging.DEBUG
    )
    argument_parser = ArgumentParser(
        description="Generates file counts for provided repositories")
    argument_parser.add_argument('repositories', nargs='*', help="The repositories to file count")
    arguments = argument_parser.parse_args()
    if not len(arguments.repositories):
        repos_and_associated_members = json.load(open(
            common.path_relative_to_root("data_collection/raw_data/members_of_mediawiki_repos.json")
        ))
        repositories = repos_and_associated_members['groups_for_repository'].keys()
    else:
        repositories = arguments.repositories
    for number_processed, repo in enumerate(repositories):
        try:
            print("Processed", number_processed, "repos out of", str(len(repositories)) + ". Currently processing", repo)
            logging.info("Processed " + str(number_processed) + " repos. Currently processing " + repo)
            get_bare_repo(repo, True)
            time.sleep(1)
        except BaseException as e:
            logging.exception("Failed to download" + repo, exc_info=e)
            pass