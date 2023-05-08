import argparse
import logging
import os
import pickle
import random
import sys
from enum import Enum
from functools import lru_cache
from typing import Tuple, Union, List, Any

from requests import HTTPError
from sklearn.exceptions import NotFittedError
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler

import common
from recommender import RecommenderImplementation, Recommendations, get_members_of_repo
from recommender.neural_network_recommender import MLPClassifierImplementationBase


class ModelMode(Enum):
    GENERIC = "generic"
    REPO_SPECIFIC = "repo-specific"
    OPEN = "open"
    ABANDONED = "abandoned"
    MERGED = "merged"
    DEFAULT = "generic"

class SelectionMode(Enum):
    RANDOM = "random"
    SEMI_RANDOM = "semi-random"
    IN_ORDER = "in-order"

class MLPClassifierImplementation(RecommenderImplementation, MLPClassifierImplementationBase):
    def __init__(self, repository: str, model_type: ModelMode, time_period: str, selection_mode: Union[str, SelectionMode], approved_to_voted: int = 3):
        super().__init__(repository)
        match model_type:
            case ModelMode.REPO_SPECIFIC:
                model_name = common.get_sanitised_filename(repository)
            case ModelMode.OPEN:
                model_name = common.get_sanitised_filename(repository) + "_open"
            case ModelMode.ABANDONED:
                model_name = common.get_sanitised_filename(repository) + "_abandoned"
            case ModelMode.MERGED:
                model_name = common.get_sanitised_filename(repository) + "_merged"
            case _:
                model_name = model_type.value
        self.approved_model = self.load_model(model_name + "_approved")
        """The model for predicting who would approve a given change"""
        self.approved_scaler = self.load_scaler(model_name + "_approved")
        """The scaler used to scale input data before using it to predict with the approved model"""
        self.voted_model = self.load_model(model_name + "_voted")
        """The model for predicting who would vote on a given change"""
        self.voted_scaler = self.load_scaler(model_name + "_voted")
        """The scaler used to scale input data before using it to predict with the voted model"""
        self.base_data_frame = self.preprocess_into_pandas_data_frame(repository)[time_period]
        """The pandas data frame that is used as the starting point for changes on this repository. Change specific data frames add extra columns."""
        self.time_period = time_period
        """Time period to select the data from."""
        if isinstance(selection_mode, str):
            try:
                selection_mode = SelectionMode(selection_mode.strip().lower())
            except ValueError:
                raise ValueError("Invalid selection mode provided. Must be one of 'random', 'semi-random' or 'in-order'.")
        self.selection_mode = selection_mode
        """What method to use to select the recommendations to return after the users have been classified."""
        self._approved_to_voted = approved_to_voted
        """How many users who are predicted to approve should be recommended to every one user who will only vote but not approve."""

    @classmethod
    @lru_cache(maxsize=5)
    def load_model(cls, name: str) -> MLPClassifier:
        if not os.path.exists(cls.get_model_path(name)):
            raise Exception("Model with this name does not exist. Try training it first.")
        return pickle.load(open(cls.get_model_path(name), 'rb'))

    @staticmethod
    @lru_cache(maxsize=20)
    def get_model_path(name) -> str:
        return common.path_relative_to_root("recommender/neural_network_recommender/models/" + common.sanitize_filename(name) + "_clf.pickle")

    @classmethod
    @lru_cache(maxsize=5)
    def load_scaler(cls, name: str) -> StandardScaler:
        if not os.path.exists(cls.get_scaler_path(name)):
            raise Exception("Scaler with this name does not exist. Try training it first.")
        return pickle.load(open(cls.get_scaler_path(name), 'rb'))

    @staticmethod
    @lru_cache(maxsize=20)
    def get_scaler_path(name: str) -> str:
        return common.path_relative_to_root("recommender/neural_network_recommender/scalers/" + common.sanitize_filename(name) + "_scaler.pickle")

    @classmethod
    def load_model_and_associated_scaler(cls, name: str) -> Tuple[MLPClassifier, StandardScaler]:
        return cls.load_model(name), cls.load_scaler(name)

    def recommend_using_change_info(self, change_info: dict) -> Recommendations:
        change_specific_data_frame = self.add_change_specific_attributes_to_data_frame(self.repository, change_info, self.base_data_frame)
        # Replace NaNs with 0s
        change_specific_data_frame = change_specific_data_frame.fillna(0)
        # Scale the data frame data
        voted_X = change_specific_data_frame.copy(deep=True)
        approved_X = change_specific_data_frame.copy(deep=True)
        voted_X[voted_X.columns] = self.voted_scaler.transform(voted_X[voted_X.columns])
        approved_X[approved_X.columns] = self.approved_scaler.transform(approved_X[approved_X.columns])
        try:
            predicted_approvers = [approved_X.index.values[i] for i, y in enumerate(self.approved_model.predict(voted_X)) if y]
            predicted_voters = [voted_X.index.values[i] for i, y in enumerate(self.voted_model.predict(approved_X)) if y]
        except NotFittedError as e:
            logging.error("Model not fitted.", exc_info=e)
            raise e
        predicted_voters_but_not_approvers = list(set(predicted_voters).difference(predicted_approvers))
        # Get the owner of the change (if noted in the change_info) and exclude this user
        #  as they can't review their own patch
        owner = change_info['owner']
        owner_names = set()
        owner_emails = set()
        if 'name' in owner and owner['name']:
            owner_names.add(owner['name'])
        if 'username' in owner and owner['username']:
            owner_names.add(owner['username'])
        if 'display_name' in owner and owner['display_name']:
            owner_names.add(owner['display_name'])
        for name in owner_names:
            name = common.convert_name_to_index_format(name)
            if name in common.username_to_email_map.keys():
                owner_emails.add(common.username_to_email_map[name])
        if 'email' in owner and owner['email']:
            owner_emails.add(owner['email'])
        # Initialise the recommendations list
        recommendations = Recommendations(exclude_emails=list(owner_emails), exclude_names=list(owner_names))
        if self.selection_mode == SelectionMode.RANDOM:
            # Select recommendation order among the users who have been predicted to approve or vote
            #  based on randomly shuffling those lists and scoring them with highest being the first and lowest
            #  the last in the randomly shuffled list
            random.shuffle(predicted_approvers)
            random.shuffle(predicted_voters_but_not_approvers)
        elif self.selection_mode != SelectionMode.IN_ORDER:
            # For the semi-random and also used as the default.
            #
            # Similar to the random shuffle but limits the distance travelled by this
            #  shuffle to a pre-defined amount. Means top-rated users are kept
            # top-rated without always choosing the most top-rated users.
            def distance_limited_shuffle_sort(list: List[Any], distance_limit: int = 5) -> None:
                start = 0
                end = distance_limit
                if len(list) < end:
                    random.shuffle(list)
                    return
                while len(list) > end:
                    # Split up into chunks of size distance_limit and shuffle these
                    list_chunk = list[start:end]
                    random.shuffle(list_chunk)
                    list[start:end] = list_chunk
                    start = end
                    end += distance_limit
                # Shuffle the last part of the list
                last_chunk = list[start:]
                random.shuffle(last_chunk)
                list[start:] = last_chunk
            distance_limited_shuffle_sort(predicted_approvers)
            distance_limited_shuffle_sort(predicted_voters_but_not_approvers)
        # Add all the predicted users to the recommendations list
        for user in predicted_approvers:
            recommendations.get_reviewer_by_name_or_create_new(user)
        for user in predicted_voters_but_not_approvers:
            recommendations.get_reviewer_by_name_or_create_new(user)
        # Mark the users who can approve changes in this repository
        users_with_rights_to_merge = get_members_of_repo(self.repository)
        logging.debug("users with right to merge: " + str(users_with_rights_to_merge))
        for user in users_with_rights_to_merge:
            reviewer = None
            if 'email' in user and user['email']:
                # Lookup the reviewer by their email if an email is specified.
                reviewer = recommendations.get_reviewer_by_email(user['email'])
                if reviewer is not None:
                    # Add the names in the user dictionary to the reviewer
                    for username_key in ['user', 'display_name', 'username']:
                        if username_key in user and user[username_key]:
                            reviewer.names.add(user[username_key])
            if reviewer is None:
                # If no user can be found by the email, then try using the names
                for username_key in ['user', 'display_name', 'username']:
                    if username_key in user and user[username_key]:
                        reviewer = recommendations.get_reviewer_by_name(user[username_key])
                        if reviewer is None:
                            continue
                        # Add the names in the user dictionary to the reviewer
                        for username_key_2 in ['user', 'display_name', 'username']:
                            if username_key_2 in user and user[username_key_2]:
                                reviewer.names.add(user[username_key_2])
                        # Add the email if an email is defined
                        if 'email' in user and user['email']:
                            reviewer.emails.add(user['email'])
            if reviewer is None:
                continue
            reviewer.has_rights_to_merge = True
        for reviewer in filter(lambda x: x.has_rights_to_merge is not True, recommendations.recommendations):
            reviewer.has_rights_to_merge = False
        # Score the reviewers based on their position in the list
        i = 0
        j = 0
        combined_voter_and_approver_lists = []
        while len(predicted_approvers) != i or len(predicted_voters_but_not_approvers) != j:
            if len(predicted_approvers) == i or (
                    self._approved_to_voted and len(combined_voter_and_approver_lists) and
                    len(combined_voter_and_approver_lists) % (self._approved_to_voted + 1) == 0):
                # Add a voter who isn't predicted to approve every N where N is self._approved_to_voted.
                # When all approvers are added then add all the voters.
                # If self._approved_to_voted is 0 all approvers are added first.
                combined_voter_and_approver_lists.append(predicted_voters_but_not_approvers[j])
                j += 1
            else:
                combined_voter_and_approver_lists.append(predicted_approvers[i])
                i += 1
        for score, user in enumerate(reversed(combined_voter_and_approver_lists)):
            reviewer = recommendations.get_reviewer_by_name(user)
            if reviewer is not None and not reviewer.score:
                # Assign the score to the user if they are not excluded from the results
                #  and don't already have a score.
                reviewer.score = score
        return recommendations


if __name__ == '__main__':
    argument_parser = argparse.ArgumentParser(description="A Multi-layer Perceptron classifier implementation of a tool that recommends reviewers for the MediaWiki project")
    # TODO: Deduplicate from rule_based_recommender.py where possible?
    # TODO: Allow use of either repo-specific or generic?
    # TODO: Cause training if no model exists?
    argument_parser.add_argument('change_id', nargs='+', help="The change ID(s) of the changes you want to get recommended reviewers for")
    argument_parser.add_argument('--repository', nargs='+', help="The repository for these changes. Specifying one repository applies to all changes. Multiple repositories apply to each change in order.", required=True)
    argument_parser.add_argument('--branch', nargs='+', help="The branch these change IDs are on (default is the main branch). Specifying one branch applies to all changes. Multiple branches apply to each change in order.", default=[], required=False)
    argument_parser.add_argument('--stats', action='store_true', help="Show stats about the recommendations.")
    argument_parser.add_argument('--model-type', choices=["repo-specific", "generic", "open", "abandoned", "merged"], default="generic", help="What model to use. The models selectable here have been trained over varying amounts of the testing data.")
    argument_parser.add_argument('--time-period', choices=common.TimePeriods.DATE_RANGES, help="What time period should data be selected from to make recommendations", default=common.TimePeriods.ALL_TIME)
    argument_parser.add_argument('--selection-mode', choices=["random", "semi-random", "in-order"], help="How to choose the users classified as predicted to vote or approve the change.", default="in-order", required=False)
    argument_parser.add_argument('--no-of-predicted-approvers-to-one-voter', type=int, help="How many predicted approved should be recommended to one predicted voter. 0 for recommendations prioritise all predicted approvers over voters.", default=3, required=False)
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
        while True:
            print("Model type options:\n* Generic: Trained on all repositories\n* Repo-specific: Trained on the repo the change is on\n* Open: Trained on open changes from the repo the change is on\n* Abandoned: Trained on abandoned changes from the repo the change is on\n* Merged: Trained on merged changes from the repo the change is on")
            model_type = input("Please enter the model type to be used:").strip().lower()
            if not model_type:
                # Use "generic" by default
                model_type = "generic"
            if model_type in ["repo-specific", "generic", "open", "abandoned", "merged"]:
                break
            print("Invalid model type. Please try again.")
        while True:
            print("Time period options:", ', '.join(common.TimePeriods.DATE_RANGES[:-1]), 'and', common.TimePeriods.DATE_RANGES[-1])
            time_period = input("Please enter the model type to be used:").strip().lower()
            if time_period in common.TimePeriods.DATE_RANGES:
                break
            print("Invalid time period. Please try again.")
        while True:
            print("Selection mode options:\n * in-order - No shuffling applied\n * random - Recommendations fully shuffled\n * semi-random - Recommendations shuffled but user cannot change more than 5 positions from their pre-shuffled state.")
            selection_mode = input("Please enter the selection mode to be used:").strip().lower()
            try:
                selection_mode = SelectionMode(selection_mode)
                break
            except ValueError:
                print("Invalid selection mode. Please try again.")
        # TODO: Add no-of-predicted-approvers-to-one-voter input?
        no_of_predicted_approvers_to_one_voter = 3
    else:
        command_line_arguments = argument_parser.parse_args()
        change_ids = command_line_arguments.change_id
        repositories = command_line_arguments.repository
        branches = command_line_arguments.branch
        model_type = command_line_arguments.model_type
        time_period = command_line_arguments.time_period
        selection_mode = command_line_arguments.selection_mode
        no_of_predicted_approvers_to_one_voter = command_line_arguments.no_of_predicted_approvers_to_one_voter
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
            recommended_reviewers = MLPClassifierImplementation(change["repository"], ModelMode(model_type), time_period, selection_mode, no_of_predicted_approvers_to_one_voter).recommend_using_change_id(change['change_id'], change["branch"])
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