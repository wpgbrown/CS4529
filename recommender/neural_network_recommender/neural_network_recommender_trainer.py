import argparse
import json
import logging
import os
import pickle
from typing import List, Union, Tuple
import pandas
from imblearn.under_sampling import RandomUnderSampler, ClusterCentroids
from pandas import Series
from sklearn.exceptions import NotFittedError
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score, confusion_matrix
from sklearn.model_selection import train_test_split
from sklearn.neural_network import MLPClassifier
import common
from comment_votes_and_members_of_repos_to_data_frame import preprocess_into_pandas_data_frame
from common import get_test_data_for_repo
from recommender.neural_network_recommender import add_change_specific_attributes_to_data_frame
from recommender.neural_network_recommender.neural_network_recommender import ModelMode, MLPClassifierImplementation
import warnings

warnings.filterwarnings("ignore")

class ModelScalerAndData:
    def __init__(self, model: MLPClassifier, scaler: StandardScaler, name):
        self.name = name
        self.model = model
        self.scaler = scaler
        # self.voted_under_sampler = RandomUnderSampler(random_state=0)
        # self.approved_under_sampler = RandomUnderSampler(random_state=0)
        self.voted_under_sampler = ClusterCentroids()
        self.approved_under_sampler = ClusterCentroids()
        self.X_train = []
        self.under_sampled_approved_X_train = []
        self.under_sampled_approved_train = []
        self.under_sampled_voted_X_train = []
        self.under_sampled_voted_train = []
        self.approved_train = []
        self.voted_train = []
        self.X_test = []
        self.approved_test = []
        self.voted_test = []
        self.scaler_has_been_trained = True

class MLPClassifierTrainer:
    def __init__(self, modes: List[ModelMode], train_existing_models: bool = True):
        self._modes = modes
        self._train_existing_models = train_existing_models
        self._data_scaled = False
        if train_existing_models:
            # "generic" models
            self._generic_approved = ModelScalerAndData(*MLPClassifierImplementation.load_model_and_associated_scaler("generic_approved"))
            self._generic_voted = ModelScalerAndData(*MLPClassifierImplementation.load_model_and_associated_scaler("generic_voted"))
        else:
            # "generic" models
            self._generic_approved = self._create_new_model("generic_approved")
            self._generic_voted = self._create_new_model("generic_voted")
        # "repo-specific" models - loaded on the fly
        self._repo_specific_approved = {}
        self._repo_specific_voted = {}
        # "open", "abandoned" and "merged" models - loaded on the fly
        self._open_voted = {}
        self._abandoned_voted = {}
        self._merged_voted = {}
        self._open_approved = {}
        self._abandoned_approved = {}
        self._merged_approved = {}

    def _get_model_dictionaries(self, model_type: ModelMode) -> Tuple[Union[dict[str, ModelScalerAndData], ModelScalerAndData], Union[dict[str, ModelScalerAndData], ModelScalerAndData]]:
        match model_type:
            case ModelMode.GENERIC:
                return self._generic_approved, self._generic_voted
            case ModelMode.REPO_SPECIFIC:
                return self._repo_specific_approved, self._repo_specific_voted
            case ModelMode.OPEN:
                return self._open_approved, self._open_voted
            case ModelMode.ABANDONED:
                return self._abandoned_approved, self._abandoned_voted
            case ModelMode.MERGED:
                return self._merged_approved, self._merged_voted

    @staticmethod
    def _create_new_model(name: str, max_iter=300) -> ModelScalerAndData:
        new_model = ModelScalerAndData(MLPClassifier(max_iter=max_iter, hidden_layer_sizes=(500,250,100,50)), StandardScaler(), name)
        new_model.scaler_has_been_trained = False
        return new_model

    def _add_data(self, repository: str, status: str, data_frame: pandas.DataFrame, training_data: bool) -> None:
        if self._data_scaled:
            raise Exception("Data has already been used to train or test. Cannot add more data as existing data has been scaled. Save the model and load it again to add more testing/training data.")
        # Convert status to ModelMode enum
        status = ModelMode(status)
        # Load models (if needed) and then add the data
        if ModelMode.GENERIC in self._modes:
            self._add_data_to_model(self._generic_approved, data_frame, training_data)
            self._add_data_to_model(self._generic_voted, data_frame, training_data)
        if ModelMode.REPO_SPECIFIC in self._modes:
            self._add_data_to_model_dictionary(self._repo_specific_approved, repository, "_approved", data_frame, training_data)
            self._add_data_to_model_dictionary(self._repo_specific_voted, repository, "_voted", data_frame, training_data)
        match status:
            case ModelMode.OPEN:
                if ModelMode.OPEN in self._modes:
                    self._add_data_to_model_dictionary(self._open_approved, repository, "_%s_approved" % ModelMode.OPEN.value, data_frame,
                                                       training_data)
                    self._add_data_to_model_dictionary(self._open_voted, repository, "_%s_voted" % ModelMode.OPEN.value, data_frame,
                                                       training_data)
            case ModelMode.MERGED:
                if ModelMode.MERGED in self._modes:
                    self._add_data_to_model_dictionary(self._merged_approved, repository, "_%s_approved" % ModelMode.MERGED.value,
                                                       data_frame, training_data)
                    self._add_data_to_model_dictionary(self._merged_voted, repository, "_%s_voted" % ModelMode.MERGED.value, data_frame,
                                                       training_data)
            case ModelMode.ABANDONED:
                if ModelMode.ABANDONED in self._modes:
                    self._add_data_to_model_dictionary(self._abandoned_approved, repository, "_%s_approved" % ModelMode.ABANDONED.value,
                                                       data_frame, training_data)
                    self._add_data_to_model_dictionary(self._abandoned_voted, repository, "_%s_voted" % ModelMode.ABANDONED.value,
                                                       data_frame, training_data)

    def add_training_data(self, repository: str, status: str, data_frame: pandas.DataFrame) -> "MLPClassifierTrainer":
        self._add_data(repository, status, data_frame, True)
        return self

    def add_testing_data(self, repository: str, status: str, data_frame: pandas.DataFrame) -> "MLPClassifierTrainer":
        self._add_data(repository, status, data_frame, False)
        return self

    def _add_data_to_model_dictionary(self, dictionary: dict, repository: str, appendix: str, data_frame: pandas.DataFrame, training_data: bool) -> None:
        # Load the model if it is not already loaded
        if repository and repository not in dictionary.keys():
            if self._train_existing_models and os.path.exists(MLPClassifierImplementation.get_model_path(common.get_sanitised_filename(repository) + appendix)):
                loaded_model = MLPClassifierImplementation.load_model_and_associated_scaler(
                    common.get_sanitised_filename(repository) + appendix
                )
                dictionary[repository] = ModelScalerAndData(loaded_model[0], loaded_model[1],
                                                            common.get_sanitised_filename(repository) + appendix)
            else:
                dictionary[repository] = self._create_new_model(common.get_sanitised_filename(repository) + appendix)
        # Add the model
        self._add_data_to_model(dictionary[repository], data_frame, training_data)

    def _add_data_to_model(self, model: ModelScalerAndData, data_frame: pandas.DataFrame, training_data: bool):
        data_frame = data_frame.fillna(0)
        if training_data:
            model.X_train.append(data_frame.iloc[:, :-2])
            model.approved_train.append(data_frame.loc[:, "Actually approved"].replace({0: False}))
            model.voted_train.append(data_frame.loc[:, "Actually voted"].replace({0: False}))
        else:
            model.X_test.append(data_frame.iloc[:, :-2])
            model.approved_test.append(data_frame.loc[:, "Actually approved"].replace({0: False}))
            model.voted_test.append(data_frame.loc[:, "Actually voted"].replace({0: False}))

    def perform_training(self) -> "MLPClassifierTrainer":
        self._scale_data()
        logging.debug("Training")
        for mode in ModelMode:
            if mode not in self._modes:
                continue
            for models, target in zip(self._get_model_dictionaries(mode), ["approved", "voted"]):
                if isinstance(models, ModelScalerAndData):
                    # Handle "generic" with only one model for approved and one for voted.
                    models = {'generic': models}
                for model in models.values():
                    # Train the model using the training data
                    if target == "approved":
                        for X, approved in zip(model.under_sampled_approved_X_train,
                                               model.under_sampled_approved_train):
                            model.model.fit(X, approved)
                    else:
                        for X, voted in zip(model.under_sampled_voted_X_train,
                                               model.under_sampled_voted_train):
                            model.model.fit(X, voted)
        return self

    def perform_testing(self) -> dict:
        self._scale_data()
        logging.debug("Testing")
        return_dict = {}
        for mode in ModelMode:
            if mode not in self._modes:
                continue
            for models, target in zip(self._get_model_dictionaries(mode), ["approved", "voted"]):
                if isinstance(models, ModelScalerAndData):
                    # Handle "generic" with only one model for approved and one for voted.
                    models = {'generic': models}
                for model in models.values():
                    # Train the model using the training data
                    for i, X in enumerate(model.X_test):
                        if target == "approved":
                            # TODO: Combine the test results. Currently being overwritten
                            try:
                                approved_prediction = model.model.predict(X)
                                if True in approved_prediction:
                                    print("Yay!")
                                return_dict[model.name] = {
                                    'accuracy score': accuracy_score(model.approved_test[i], approved_prediction),
                                    'confusion matrix': confusion_matrix(model.approved_test[i], approved_prediction)
                                }
                            except NotFittedError:
                                # TODO: Represent that there is no result for this model
                                continue
                        else:
                            # TODO: Combine the test results. Currently being overwritten
                            try:
                                voted_prediction = model.model.predict(X)
                                if True in voted_prediction:
                                    print("Yay!")
                                return_dict[model.name] = {
                                    'accuracy score': accuracy_score(model.voted_test[i], voted_prediction),
                                    'confusion matrix': confusion_matrix(model.voted_test[i], voted_prediction)
                                }
                            except NotFittedError:
                                # TODO: Represent that there is no result for this model
                                continue
                        logging.debug("Model testing results for " + model.name + ": " + str(return_dict[model.name]))
        return return_dict

    def _scale_data(self) -> None:
        logging.debug("Scaling data")
        self._data_scaled = True
        for mode in ModelMode:
            if mode not in self._modes:
                continue
            for models in self._get_model_dictionaries(mode):
                if isinstance(models, ModelScalerAndData):
                    # Handle "generic" with only one model for approved and one for voted.
                    models = {'generic': models}
                for model in models.values():
                    # If not training existing models, train the scaler
                    if not model.scaler_has_been_trained:
                        for X in model.X_train:
                            model.scaler.fit(X)
                        model.scaler_has_been_trained = True
                    for i, [X, approved, voted] in enumerate(zip(model.X_train, model.approved_train, model.voted_train)):
                        model.X_train[i][X.columns] = model.scaler.transform(X[X.columns])
                        # Under-sample the training data to reduce bias towards not recommending
                        approved: Series
                        if True in approved.values and False in approved.values:
                            under_sampled_approved = model.approved_under_sampler.fit_resample(X, approved)
                            model.under_sampled_approved_X_train.append(under_sampled_approved[0])
                            model.under_sampled_approved_train.append(under_sampled_approved[1])
                        if True in voted.values and False in voted.values:
                            under_sampled_voted = model.approved_under_sampler.fit_resample(X, voted)
                            model.under_sampled_voted_X_train.append(under_sampled_voted[0])
                            model.under_sampled_voted_train.append(under_sampled_voted[1])
                    for i, X in enumerate(model.X_test):
                        model.X_test[i][X.columns] = model.scaler.transform(X[X.columns])

    def save_models(self) -> None:
        for mode in ModelMode:
            for models in self._get_model_dictionaries(mode):
                if isinstance(models, ModelScalerAndData):
                    # Handle "generic" model which only has one approved and one voted model
                    models = {'generic': models}
                for model in models.values():
                    self._save_model(model)

    @staticmethod
    def _save_model(model_scaler_and_data: ModelScalerAndData) -> None:
        # Save model and scaler separately
        pickle.dump(model_scaler_and_data.model, open(MLPClassifierImplementation.get_model_path(model_scaler_and_data.name), 'wb'))
        pickle.dump(model_scaler_and_data.scaler, open(MLPClassifierImplementation.get_scaler_path(model_scaler_and_data.name), 'wb'))

if __name__ == "__main__":
    logging.basicConfig(filename=common.path_relative_to_root("logs/neural_network_recommender_logs.log.txt"),
                        level=logging.DEBUG)
    argument_parser = argparse.ArgumentParser(
        description="The training script for the MLP classifier based recommender")
    argument_parser.add_argument('repositories', nargs='*', help="The repositories to train on. None for all repositories.")
    argument_parser.add_argument(
        '--exclude-repo-specific-model', action='store_true', help="Exclude the repo specific models from evaluation"
    )
    argument_parser.add_argument(
        '--exclude-generic-model', action='store_true', help="Exclude the generic models from evaluation"
    )
    argument_parser.add_argument(
        '--exclude-open-model', action='store_true', help="Exclude the open change model made for each repo from evaluation"
    )
    argument_parser.add_argument(
        '--exclude-merged-model', action='store_true', help="Exclude the merged change model made for each repo from evaluation"
    )
    argument_parser.add_argument(
        '--exclude-abandoned-model', action='store_true', help="Exclude the abandoned change model made for each repo from evaluation"
    )
    argument_parser.add_argument(
        '--train-existing-models', action='store_true',
        help="Train the existing models if they exist instead of creating new ones"
    )
    command_line_arguments = argument_parser.parse_args()
    repositories = command_line_arguments.repositories
    models_to_train = []
    if not command_line_arguments.exclude_repo_specific_model:
        models_to_train.append(ModelMode.REPO_SPECIFIC)
    if not command_line_arguments.exclude_generic_model:
        models_to_train.append(ModelMode.GENERIC)
    if not command_line_arguments.exclude_open_model:
        models_to_train.append(ModelMode.OPEN)
    if not command_line_arguments.exclude_merged_model:
        models_to_train.append(ModelMode.MERGED)
    if not command_line_arguments.exclude_abandoned_model:
        models_to_train.append(ModelMode.ABANDONED)
    if not models_to_train:
        argument_parser.error("At least one model must not be excluded.")
    MLP_trainer = MLPClassifierTrainer(models_to_train, command_line_arguments.train_existing_models)
    repos_and_associated_members = json.load(open(
        common.path_relative_to_root("data_collection/raw_data/members_of_mediawiki_repos.json")
    ))
    def get_training_and_testing_change_specific_data_frame(repository: str, change_info: dict, base_data_frame_for_repo: pandas.DataFrame):
        change_specific_data_frame = add_change_specific_attributes_to_data_frame(repository,
                                                                                  change_info,
                                                                                  base_data_frame_for_repo)
        # Store lowercase representation to actual case used for indexing purposes
        lower_case_names = {x.lower(): x for x in change_specific_data_frame.index.values}
        # Add whether they actually voted
        change_specific_data_frame["Actually voted"] = False
        change_specific_data_frame["Actually approved"] = False
        # Check if voted
        for vote in change_info['code_review_votes']:
            name = None
            # Try to find associated data_frame row
            if 'name' in vote and vote['name'].lower() in lower_case_names:
                name = lower_case_names[vote['name'].lower()]
            elif 'display_name' in vote and vote['display_name'].lower() in lower_case_names:
                name = lower_case_names[vote['display_name'].lower()]
            elif 'username' in vote and vote['username'].lower() in lower_case_names:
                name = lower_case_names[vote['username'].lower()]
            if name is None:
                # No matching name found. Add it to the array.
                # TODO: Is this the right thing to do? Should a continue be used instead
                change_specific_data_frame.loc[vote['name'], :] = 0
            change_specific_data_frame.at[vote['name'], "Actually voted"] = True
            if vote['value'] == 2:
                # Was an approval vote
                change_specific_data_frame.at[vote['name'], "Actually approved"] = True
        return change_specific_data_frame
    for number_processed, repository in enumerate(repos_and_associated_members['groups_for_repository'].keys()):
        if repositories and repository not in repositories:
            continue
        try:
            test_data = get_test_data_for_repo(repository)
            if test_data is None:
                continue
            logging.debug("Processing " + repository + " which is " + str(number_processed + 1) + "out of" +
                  str(len(repos_and_associated_members['groups_for_repository'].keys())))
            print("Processing", repository)
            time_period = test_data[0]
            test_data = test_data[1]
            base_data_frame_for_repo = preprocess_into_pandas_data_frame(repository)[time_period]
            for status, sub_test_data in test_data.items():
                try:
                    logging.debug("Status: " + status)
                    for change_id in sub_test_data.keys():
                        sub_test_data[change_id]["id"] = change_id
                    sub_test_data = list(sub_test_data.values())
                    if len(sub_test_data) <= 1:
                        continue
                    train, test = train_test_split(sub_test_data)
                    train = list(train)
                    test = list(test)
                    for i, change_info in enumerate(train):
                        print("Collating training data", i, "out of", len(train))
                        logging.info("Collating training data " + str(i) + " out of " + str(len(train)))
                        MLP_trainer.add_training_data(
                            repository, status, get_training_and_testing_change_specific_data_frame(
                                repository, change_info, base_data_frame_for_repo
                            )
                        )
                    for i, change_info in enumerate(test):
                        print("Collating test data", i, "out of", len(test))
                        logging.info("Collating test data " + str(i) + " out of " + str(len(train)))
                        MLP_trainer.add_testing_data(
                            repository, status, get_training_and_testing_change_specific_data_frame(
                                repository, change_info, base_data_frame_for_repo
                            )
                        )
                except BaseException as e:
                    if isinstance(e, KeyboardInterrupt):
                        raise e
                    logging.error("Error", exc_info=e)
                    pass
        except KeyboardInterrupt:
            break
        except BaseException:
            pass
    print("Training....")
    MLP_trainer.perform_training()
    print("Testing....")
    print(MLP_trainer.perform_testing())
    MLP_trainer.save_models()