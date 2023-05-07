import sys
import os
import logging
import argparse
from requests import HTTPError
from recommender import Recommendations, WeightingsBase, get_members_of_repo, get_reviewer_data, \
    get_comment_data, RecommenderImplementation

# Add parent directory to the path incase it's not already there
sys.path.insert(1, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import common

#DEBUG
class RuleBasedWeightings(WeightingsBase):
    def __init__(self):
        super().__init__(common.path_relative_to_root("recommender/rule_based_recommender_weightings.json"))
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

class RuleBasedImplementation(RecommenderImplementation):
    def __init__(self, repository: str):
        super().__init__(repository)
        self.weightings = RuleBasedWeightings()

    def recommend_using_change_info(self, change_info: dict):
        # Initialise the recommendations list
        recommendations = Recommendations()
        # Get the files modified (added, changed or deleted) by the change
        git_blame_stats = self.get_change_git_blame_info(change_info)
        for email, names in git_blame_stats['names'].items():
            reviewer = recommendations.get_reviewer_by_email_or_create_new(email)
            for name in names:
                reviewer.names.add(name)
        for git_blame_key in ["authors", "committers"]:
            for line_count_key, weighting in self.weightings.lines_count[git_blame_key].items():
                line_count_key = line_count_key.replace(' ', '_') + '_lines_count'
                for author_email, percentage in git_blame_stats[git_blame_key][line_count_key].items():
                    reviewer = recommendations.get_reviewer_by_email_or_create_new(author_email)
                    reviewer.add_score(percentage, weighting)
        # Get previous reviewers for changes
        reviewer_votes_for_current_repo = get_reviewer_data()[self.repository]
        logging.debug("Reviewer votes: " + str(reviewer_votes_for_current_repo))
        for vote_weighting_key, vote_weightings in self.weightings.votes.items():
            for key, weighting in vote_weightings.items():
                for reviewer_name, comment_percentage in reviewer_votes_for_current_repo[key].items():
                    reviewer = recommendations.get_reviewer_by_name_or_create_new(reviewer_name)
                    reviewer.add_score(comment_percentage[vote_weighting_key], weighting)
        del reviewer_votes_for_current_repo
        # Get authors of previous comments
        comments_for_current_repo = get_comment_data()[self.repository]
        logging.debug("Comments: " + str(comments_for_current_repo))
        for key, weighting in self.weightings.comments.items():
            for reviewer_name, comment_percentage in comments_for_current_repo[key].items():
                reviewer = recommendations.get_reviewer_by_name_or_create_new(reviewer_name)
                reviewer.add_score(comment_percentage, weighting)
        del comments_for_current_repo
        # Initialise list based on who has rights to merge for the repository
        users_with_rights_to_merge = get_members_of_repo(self.repository)
        logging.debug("users with right to merge: " + str(users_with_rights_to_merge))
        for user in users_with_rights_to_merge:
            reviewer = None
            if 'email' in user and user['email']:
                # Lookup the reviewer by their email if an email is specified.
                reviewer = recommendations.get_reviewer_by_email_or_create_new(user['email'])
                # Add the names in the user dictionary to the reviewer
                for username_key in ['user', 'display_name', 'username']:
                    if username_key in user and user[username_key]:
                        reviewer.names.add(user[username_key])
            else:
                # If no email is associated with the user dictionary, then try using the names
                for username_key in ['user', 'display_name', 'username']:
                    if username_key in user and user[username_key]:
                        reviewer = recommendations.get_reviewer_by_name_or_create_new(user[username_key])
                        # Add the names in the user dictionary to the reviewer
                        for username_key_2 in ['user', 'display_name', 'username']:
                            if username_key_2 in user and user[username_key_2]:
                                reviewer.names.add(user[username_key_2])
            if reviewer is None:
                # If a user can merge but has never interacted with the repository, then recommending them
                #  would not make sense. Therefore, skip these users.
                continue
            reviewer.has_rights_to_merge = True
        for reviewer in filter(lambda x: x.has_rights_to_merge is not True, recommendations.recommendations):
            reviewer.has_rights_to_merge = False
        return recommendations

if __name__ == '__main__':
    logging.basicConfig(filename=common.path_relative_to_root("logs/rule_based_recommender.log.txt"),
                        level=logging.DEBUG)
    argument_parser = argparse.ArgumentParser(description="A rule based implementation of a tool that recommends reviewers for the MediaWiki project")
    argument_parser.add_argument('change_id', nargs='+', help="The change ID(s) of the changes you want to get recommended reviewers for")
    argument_parser.add_argument('--repository', nargs='+', help="The repository for these changes. Specifying one repository applies to all changes. Multiple repositories apply to each change in order.", required=True)
    argument_parser.add_argument('--branch', nargs='+', help="The branch these change IDs are on (default is the main branch). Specifying one branch applies to all changes. Multiple branches apply to each change in order.", default=[], required=False)
    argument_parser.add_argument('--stats', action='store_true', help="Show stats about the recommendations.")
    change_ids_with_repo_and_branch = []
    command_line_arguments = None
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
        command_line_arguments = argument_parser.parse_args()
        change_ids = command_line_arguments.change_id
        repositories = command_line_arguments.repository
        branches = command_line_arguments.branch
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
            recommended_reviewers = RuleBasedImplementation(change["repository"]).recommend_using_change_id(change['change_id'], change["branch"])
            logging.debug("Recommendations: " + str(recommended_reviewers))
            top_10_recommendations = recommended_reviewers.top_n(10)
            for recommendation in top_10_recommendations:
                print(recommendation)
            if command_line_arguments and command_line_arguments.stats:
                print("Recommendation stats for change", change['change_id'])
                print("Users recommended:", len(top_10_recommendations))
                print("Users recommended with rights to merge:", len(list(filter(lambda x: x.has_rights_to_merge, top_10_recommendations))))
        except HTTPError as e:
            print("Recommendations for change", change["change_id"], "failed with HTTP status code", str(e.response.status_code) + ". Check that this is correct and try again later.")