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
from recommender import Recommendations, RecommendedReviewer, WeightingsBase, get_members_of_repo

# Add parent directory to the path incase it's not already there
sys.path.insert(1, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import common

#DEBUG
class SimpleWeightings(WeightingsBase):
    def __init__(self):
        super().__init__(common.path_relative_to_root("recommender/simple_recommender_weightings.json"))
        # -- Parse the weightings JSON file --
        # Line counts
        self.lines_count = {
            'authors': {},
            'committers': {}
        }
        if 'git blame' in self._weightings:
            if 'authors' in self._weightings['git blame'] and 'lines count' in self._weightings['git blame']['authors']:
                self.lines_count['authors'] = self._weightings['git blame']['authors']['lines count']
            if 'committers' in self._weightings['git blame'] and 'lines count' in self._weightings['git blame']['committers']:
                self.lines_count['committers'] = self._weightings['git blame']['committers']['lines count']
        # Votes
        self.votes = {}
        if 'votes' in self._weightings:
            self.votes = self._weightings['votes']
        # Comments
        self.comments = {}
        if 'comments' in self._weightings:
            self.comments = self._weightings['comments']


weightings = SimpleWeightings()

if __name__ == "__main__":
    logging.basicConfig(filename=common.path_relative_to_root("logs/simple_recommender.log.txt"), level=logging.DEBUG)

@lru_cache(maxsize=1)
def get_reviewer_data():
    percentage_list = common.path_relative_to_root('data_collection/raw_data/reviewer_vote_percentages_for_repos.json')
    if not os.path.exists(percentage_list):
        comment_counts_to_percentages.convert_data_to_percentages()
    return json.load(open(percentage_list, 'r'))

@lru_cache(maxsize=1)
def get_comment_data():
    percentage_list = common.path_relative_to_root('data_collection/raw_data/comment_count_percentages_by_author_for_repo.json')
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
    logging.debug("Returned change info: " + str(change_info))
    # Update repository and branch to the values found in the metadata as these are cleaner
    #  even if they have been provided by the caller.
    repository = change_info['project']
    branch = change_info['branch']
    # Initialise the recommendations list
    recommendations = Recommendations()
    # Get the files modified (added, changed or deleted) by the change
    latest_revision_sha = list(change_info['revisions'].keys())[0]
    information_about_change_including_git_blame_stats_in_head = {}
    for filename, info in change_info['revisions'][latest_revision_sha]['files'].items():
        # Add deleted and changed files to files modified from the base
        info: dict
        if 'status' not in info.keys():
            # File just modified (not created, moved or deleted), so other authors can likely help
            information_about_change_including_git_blame_stats_in_head[filename] = info
            information_about_change_including_git_blame_stats_in_head[filename].update(
                {'blame_stats': git_blame.git_blame_stats_for_head_of_branch(filename, repository, branch)}
            )
        else:
            match info['status']:
                case 'D' | 'W':
                    # File was either deleted or substantially re-written.
                    # While this means none of or very little of the code
                    #  already present will be kept if this is merged, said
                    #  authors and committers are likely to provide some
                    #  useful thoughts on this.
                    information_about_change_including_git_blame_stats_in_head[filename] = info
                    information_about_change_including_git_blame_stats_in_head[filename].update(
                        {'blame_stats': git_blame.git_blame_stats_for_head_of_branch(filename, repository, branch)}
                    )
                case 'R' | 'C':
                    # File renamed or copied. The authors/committers of the file that was renamed
                    #  or the file that was copied likely have understanding about whether a rename
                    #  or copy would make sense here.
                    # TODO: Test with a change that has a copied file.
                    information_about_change_including_git_blame_stats_in_head[filename] = info
                    information_about_change_including_git_blame_stats_in_head[filename].update(
                        {'blame_stats': git_blame.git_blame_stats_for_head_of_branch(info['old_path'], repository, branch)}
                    )
    logging.debug("Git blame files from base: " + str(information_about_change_including_git_blame_stats_in_head))
    total_delta_over_all_files = sum([info['size_delta'] for info in information_about_change_including_git_blame_stats_in_head.values()])
    for file, info in information_about_change_including_git_blame_stats_in_head.items():
        logging.debug(info)
        for author_email, author_info in info['blame_stats']['authors'].items():
            reviewer = recommendations.get_reviewer_by_email_or_create_new(author_email)
            for name in author_info['name']:
                reviewer.names.add(name)
            for key, weighting in weightings.lines_count['authors'].items():
                reviewer.add_score(author_info[key.replace(' ', '_') + '_lines_count'], info['size_delta'] / total_delta_over_all_files, weighting)
        for committer_email, committer_info in info['blame_stats']['committers'].items():
            reviewer = recommendations.get_reviewer_by_email_or_create_new(committer_email)
            for name in committer_info['name']:
                reviewer.names.add(name)
            for key, weighting in weightings.lines_count['committers'].items():
                reviewer.add_score(committer_info[key.replace(' ', '_') + '_lines_count'], info['size_delta'] / total_delta_over_all_files, weighting)
    # TODO: Use users with +2 to match usernames to emails. Current system doesn't handle variations in usernames well.
    del information_about_change_including_git_blame_stats_in_head
    # Get previous reviewers for changes
    reviewer_votes_for_current_repo = get_reviewer_data()[repository]
    logging.debug("Reviewer votes: " + str(reviewer_votes_for_current_repo))
    for vote_weighting_key, vote_weightings in weightings.votes.items():
        # Translate key into format used by the script
        # TODO: Remove this by updating the definitions in the script that makes this?
        match vote_weighting_key:
            case 'Total votes':
                vote_weighting_key = 'Gerrit approval actions count'
            case '+1 code review votes':
                vote_weighting_key = "1 code review votes"
            case '+2 code review votes':
                vote_weighting_key = "2 code review votes"
        for key, weighting in vote_weightings.items():
            # TODO: Remove this by updating the definitions in the script that makes this
            match key:
                case weightings.LAST_MONTH:
                    key = "last 30 days"
                case weightings.LAST_3_MONTHS:
                    key = "last 3 months"
                case weightings.ALL_TIME:
                    key = "all"
            for reviewer_name, comment_percentage in reviewer_votes_for_current_repo[key].items():
                reviewer = recommendations.get_reviewer_by_name_or_create_new(reviewer_name)
                reviewer.add_score(comment_percentage[vote_weighting_key], weighting)
    del reviewer_votes_for_current_repo
    # Get authors of previous comments
    comments_for_current_repo = get_comment_data()[repository]
    logging.debug("Comments: " + str(comments_for_current_repo))
    for key, weighting in weightings.comments.items():
        # TODO: Remove this by updating the definitions in the script that makes this
        match key:
            case weightings.LAST_MONTH:
                key = "last 30 days"
            case weightings.LAST_3_MONTHS:
                key = "last 3 months"
            case weightings.ALL_TIME:
                key = "all"
        for reviewer_name, comment_percentage in comments_for_current_repo[key].items():
            reviewer = recommendations.get_reviewer_by_name_or_create_new(reviewer_name)
            reviewer.add_score(comment_percentage, weighting)
    del comments_for_current_repo
    # TODO: Filter list for users with +2?
    # Initialise list based on who has rights to merge for the repository
    users_with_rights_to_merge = get_members_of_repo(repository)
    logging.debug("users with right to merge: " + str(users_with_rights_to_merge))
    for user in users_with_rights_to_merge:
        if 'email' in user and user['email']:
            reviewer = recommendations.get_reviewer_by_email_or_create_new(user['email'])
        elif 'name' in user and user['name']:
            reviewer = recommendations.get_reviewer_by_name_or_create_new(user['name'])
        elif 'username' in user and user['username']:
            reviewer = recommendations.get_reviewer_by_name_or_create_new(user['username'])
        elif 'display_name' in user and user['display_name']:
            reviewer = recommendations.get_reviewer_by_name_or_create_new(user['display_name'])
        else:
            continue
        if 'name' in user and user['name']:
            reviewer.names.add(user['name'])
        if 'username' in user and user['username']:
            reviewer.names.add(user['username'])
        if 'display_name' in user and user['display_name']:
            reviewer.names.add(user['display_name'])
        reviewer.has_rights_to_merge = True
    for reviewer in filter(lambda x: x.has_rights_to_merge is not True, recommendations.recommendations):
        reviewer.has_rights_to_merge = False
    return recommendations

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
    logging.info("Recommending with the following inputs: " + str(change_ids_with_repo_and_branch))
    for change in change_ids_with_repo_and_branch:
        try:
            recommended_reviewers = recommend_reviewers_for_patch(change['change_id'], change["repository"], change["branch"])
            logging.debug("Recommendations: " + str(recommended_reviewers))
            for recommendation in recommended_reviewers.ordered_by_score():
                print(recommendation)
        except HTTPError as e:
            print("Recommendations for change", change["change_id"], "failed with HTTP status code", str(e.response.status_code) + ". Check that this is correct and try again later.")