import argparse
import logging
import os
import pickle
import sys
from enum import Enum
from functools import lru_cache
from typing import Tuple

from requests import HTTPError
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler

import common
from recommender import RecommenderImplementation, Recommendations
from recommender.neural_network_recommender import preprocess_into_pandas_data_frame, \
    add_change_specific_attributes_to_data_frame


class ModelMode(Enum):
    GENERIC = "generic"
    REPO_SPECIFIC = "repo-specific"
    OPEN = "open"
    ABANDONED = "abandoned"
    MERGED = "merged"
    DEFAULT = "generic"

    @classmethod
    def _missing_(cls, value):
        # TODO: Partly from https://docs.python.org/3/library/enum.html#enum.Enum._missing_
        if value is not isinstance(value, str):
            return None
        value: str
        value = value.lower()
        for member in cls:
            if member.value == value:
                return member
        return None

class MLPClassifierImplementation(RecommenderImplementation):
    def __init__(self, repository: str, model_type: ModelMode, time_period: str):
        super().__init__(repository)
        if model_type == ModelMode.GENERIC:
            self.approved_model = self.load_model("generic_approved_clf.pickle")
            self.voted_model = self.load_model("generic_voted_clf.pickle")
            self.scaler = self.load_scaler()
        elif model_type == ModelMode.REPO_SPECIFIC:
            self.approved_model = self.load_model(common.get_sanitised_filename(repository) + "_approved_clf.pickle")
            self.voted_model = self.load_model(common.get_sanitised_filename(repository) + "_voted_clf.pickle")
        # TODO: Handle abandoned / open / merged models.
        self.base_data_frame = preprocess_into_pandas_data_frame(repository)[time_period]
        self.time_period = time_period

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
        change_specific_data_frame = add_change_specific_attributes_to_data_frame(self.repository, change_info, self.base_data_frame)
        predicted_approvers = [x for x in enumerate(self.approved_model.predict(change_specific_data_frame.iloc[:])) if x[1]]
        predicted_voters = [x for x in enumerate(self.voted_model.predict(change_specific_data_frame.iloc[:])) if x[1]]
        print(predicted_approvers)
        print(predicted_voters)
        recommendations = Recommendations()
        # TODO: Complete
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
    else:
        command_line_arguments = argument_parser.parse_args()
        change_ids = command_line_arguments.change_id
        repositories = command_line_arguments.repository
        branches = command_line_arguments.branch
        model_type = command_line_arguments.model_type
        time_period = command_line_arguments.time_period
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
            recommended_reviewers = MLPClassifierImplementation(change["repository"], ModelMode(model_type), time_period).recommend_using_change_id(change['change_id'], change["branch"])
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