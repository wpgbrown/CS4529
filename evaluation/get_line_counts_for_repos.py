"""
Script used to get the line counts for the repositories specified in the arguments.
Used for the evaluation chapter of the report.
"""
import json
from argparse import ArgumentParser
import common
from data_collection.git_blame import get_repo

argument_parser = ArgumentParser(
            description="Generates file counts for provided repositories")
argument_parser.add_argument('repositories', nargs='+', help="The repositories to file count")
arguments = argument_parser.parse_args()

repository_file_counts = {}

for repository in arguments.repositories:
    # Get the repo (not bare repo) and perform ls-files to get the number of files
    #  in the repo.
    git_repo = get_repo(repository)
    repository_file_counts[repository] = len(git_repo.git.ls_files())

# Export data to JSON file
json.dump(repository_file_counts, open(common.path_relative_to_root("data_collection/raw_data/repository_file_counts.json"), 'w'))