import sys
import os
import logging
import requests
import json
import argparse
import urllib.parse
import time
from functools import lru_cache
from requests import HTTPError
from data_collection import git_blame
from data_collection.preprocessing import reviewer_votes_to_percentages, comment_counts_to_percentages

# Add parent directory to the path incase it's not already there
sys.path.insert(1, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import common

if __name__ == "__main__":
    logging.basicConfig(filename=common.path_relative_to_root("logs/simple_recommender.log.txt"), level=logging.DEBUG)

@lru_cache()
def get_reviewer_data():
    percentage_list = common.path_relative_to_root('data_collection/raw_data/comment_count_percentages_by_author_for_repo.json')
    if not os.path.exists(percentage_list):
        comment_counts_to_percentages.convert_data_to_percentages()
    return json.load(open(percentage_list, 'r'))

@lru_cache()
def get_comment_data():
    percentage_list = common.path_relative_to_root('data_collection/raw_data/reviewer_vote_percentages_for_repos.json')
    if not os.path.exists(percentage_list):
        reviewer_votes_to_percentages.convert_data_to_percentages()
    return json.load(open(percentage_list, 'r'))

def recommend_reviewers_for_patch(change_id: str, repository: str = '', branch: str = ''):
    """
    Recommends reviewers for a given patch identified by the change ID, repository and branch.

    :param change_id: Change ID for the patch
    :param repository: Repository the change is on (default is generate from change ID info)
    :param branch: Branch that the change is on (default is generate from change ID info)
    :return: The recommended reviewers
    :raises HTTPError: If information provided does not match a change or multiple patches match (use parameters repository and branch to avoid this)
    """
    # Rate-limiting
    time.sleep(1)
    # Get information about the latest revision
    change_id_for_request = change_id
    if '~' not in change_id_for_request:
        if repository.strip():
            if branch.strip():
                change_id_for_request = branch + '~' + change_id_for_request
            change_id_for_request = repository + '~' + change_id_for_request
    change_id_for_request = urllib.parse.quote(change_id_for_request, safe='')
    request_url = common.gerrit_api_url_prefix + 'changes/' + change_id_for_request + '?o=CURRENT_REVISION&o=CURRENT_FILES&o=COMMIT_FOOTERS&o=TRACKING_IDS'
    logging.debug("Request made for change info: " + request_url)
    response = requests.get(request_url, auth=common.secrets.gerrit_http_credentials())
    # Needed in case the user provides an unrecognised change ID, repository or branch.
    response.raise_for_status()
    change_info = json.loads(common.remove_gerrit_api_json_response_prefix(response.text))
    # Debug
    print(change_info)
    # Update repository and branch to the values found in the metadata as these are cleaner
    #  even if they have been provided by the caller.
    repository = change_info['project']
    branch = change_info['branch']
    # Get the files modified (added, changed or deleted) by the change
    latest_revision_sha = list(change_info['revisions'].keys())[0]
    files_modified_in_head_blame_stats = {}
    for filename, info in change_info['revisions'][latest_revision_sha]['files'].items():
        # Add deleted and changed files to files modified from the base
        info: dict
        if 'status' not in info.keys():
            # File just modified (not created, moved or deleted), so other authors can likely help
            files_modified_in_head_blame_stats[filename] = \
                git_blame.git_blame_stats_for_head_of_branch(filename, repository, branch)
        else:
            match info['status']:
                case 'D' | 'W':
                    # File was either deleted or substantially re-written.
                    # While this means none of or very little of the code
                    #  already present will be kept if this is merged, said
                    #  authors and committers are likely to provide some
                    #  useful thoughts on this.
                    files_modified_in_head_blame_stats[filename] = info.update(
                        {'blame_stats': git_blame.git_blame_stats_for_head_of_branch(filename, repository, branch)}
                    )
                case 'R' | 'C':
                    # File renamed or copied. The authors/committers of the file that was renamed
                    #  or the file that was copied likely have understanding about whether a rename
                    #  or copy would make sense here.
                    # TODO: Test with a change that has a copied file.
                    files_modified_in_head_blame_stats[filename] = info.update(
                        {'blame_stats': git_blame.git_blame_stats_for_head_of_branch(info['old_path'], repository, branch)}
                    )
    logging.debug("Git blame files from base: " + str(files_modified_in_head_blame_stats))
    # Get previous reviewers for changes
    reviewer_votes_for_repo = get_reviewer_data()[repository]
    logging.debug("Reviewer votes: " + str(reviewer_votes_for_repo))
    # Get authors of previous comments
    comments_for_repo = get_comment_data()[repository]
    logging.debug("Comments: " + str(reviewer_votes_for_repo))
    return ["Dreamy Jazz"]

if __name__ == '__main__':
    argument_parser = argparse.ArgumentParser(description="A simple implementation of a tool that recommends reviewers for the MediaWiki project")
    argument_parser.add_argument('change_id', nargs='+', help="The change ID(s) of the changes you want to get recommended reviewers for")
    argument_parser.add_argument('--repository', nargs='+', help="The repository for these changes. Specifying one repository applies to all changes. Multiple repositories apply to each change in order.", required=True)
    argument_parser.add_argument('--branch', nargs='+', help="The branch these change IDs are on (default is the main branch). Specifying one branch applies to all changes. Multiple branches apply to each change in order.", default=[], required=False)
    change_ids_with_repo_and_branch = []
    if not len(sys.argv) > 1:
        # Ask for the user's input
        while True:
            try:
                change_id = input("Please enter your change ID (Nothing to start processing): ")
                if not len(change_id):
                    break
                repository = input("Please enter the repository for this change ID: ")
                branch = input("Please enter the branch or ref for the branch for this change ID (Enter for default for the HEAD): ")
                if not len(branch.strip()):
                    branch = common.get_main_branch_for_repository(repository)
                change_ids_with_repo_and_branch.append({'change_id': change_id, 'repository': repository, 'branch': branch})
            except KeyboardInterrupt:
                pass
    else:
        arguments = argument_parser.parse_args()
        change_ids = arguments.change_id
        repositories = arguments.repository
        branches = arguments.branch
        if len(repositories) != 1 and len(repositories) != len(change_ids):
            argument_parser.error("If specifying multiple repositories the same number of change IDs must be provided")
        if len(branches) > 1 and len(branches) != len(change_ids):
            argument_parser.error("If specifying multiple branches the same number of change IDs must be provided.")
        if len(repositories) != 1 and 1 < len(branches) != len(repositories):
            argument_parser.error("If specifying multiple repositories the same number of branches must be specified.")
        if 1 < len(branches) != len(repositories) > 1:
            argument_parser.error("If specifying multiple branches the same number of repositories must be specified.")
        for index, change_id in enumerate(change_ids):
            change_dictionary = {'change_id': change_id}
            if len(repositories) == 1:
                change_dictionary['repository'] = repositories[0]
            else:
                change_dictionary['repository'] = repositories[index]
            if len(branches) == 1:
                change_dictionary['branch'] = repositories[0]
            elif len(branches) == 0:
                change_dictionary['branch'] = common.get_main_branch_for_repository(change_dictionary['repository'])
            else:
                change_dictionary['branch'] = repositories[index]
            change_ids_with_repo_and_branch.append(change_dictionary)
    # Debug
    print(change_ids_with_repo_and_branch)
    for change in change_ids_with_repo_and_branch:
        try:
            recommended_reviewers = recommend_reviewers_for_patch(change['change_id'], change["repository"], change["branch"])
        except HTTPError as e:
            print("Recommendations for change", change["change_id"], "failed with HTTP status code", str(e.response.status_code) + ". Check that this is correct and try again later.")