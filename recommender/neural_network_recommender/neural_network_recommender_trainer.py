"""
Trains the models used in the neural network impementation.
"""
import argparse
import json
import logging
import os
import pickle
from typing import List, Union, Tuple

import numpy
import pandas
from imblearn.under_sampling import ClusterCentroids
from pandas import Series
from sklearn.exceptions import NotFittedError
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score, confusion_matrix
from sklearn.model_selection import train_test_split
from sklearn.neural_network import MLPClassifier
import common
from common import get_test_data_for_repo
from recommender.neural_network_recommender import MLPClassifierImplementationBase
from recommender.neural_network_recommender.neural_network_recommender import ModelMode, MLPClassifierImplementation
import warnings

warnings.filterwarnings("ignore")

# This code is taken from https://stackoverflow.com/a/57915246
#  which was written by Jie Yang
class NpEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, numpy.integer):
            return int(obj)
        if isinstance(obj, numpy.floating):
            return float(obj)
        if isinstance(obj, numpy.ndarray):
            return obj.tolist()
        return super(NpEncoder, self).default(obj)
# End from https://stackoverflow.com/a/57915246

class ModelScalerAndData:
    """
    A class that is used to store the model, associated scaler and data.
    This keeps the associated data together in a format that can be easily inspected
    and also allows type hints to specify this class as the type for an argument.
    """
    def __init__(self, model: MLPClassifier, scaler: StandardScaler, name):
        self.name = name
        """Name of the model"""
        self.model = model
        """MLP classifier model object"""
        self.scaler = scaler
        """Scaler associated with the model"""
        self.voted_under_sampler = ClusterCentroids()
        """Under-sampler for predicting voters"""
        self.approved_under_sampler = ClusterCentroids()
        """Under-sampler for predicting approvers"""
        self.X_train = []
        """The input features used for training"""
        self.under_sampled_approved_X_train = []
        """Under sampled X_train for predicting approvers"""
        self.under_sampled_approved_train = []
        """Under sampled actual classification values associated with under_sampled_approved_X_train."""
        self.under_sampled_voted_X_train = []
        """Under sampled X_train for predicting voters"""
        self.under_sampled_voted_train = []
        """Under sampled actual classification values associated with under_sampled_voted_X_train."""
        self.approved_train = []
        """Whether a user approved the change. Associated value is in X_train at the same index."""
        self.voted_train = []
        """Whether a user voted on the change. Associated value is in X_train at the same index."""
        self.X_test = []
        """Input features used for testing"""
        self.X_test_scaled = []
        """The scaled version of X_test"""
        self.approved_test = []
        """Actual approver classifications associated with X_test"""
        self.voted_test = []
        """Actual voter classifications associated with X_test"""
        self.scaler_has_been_trained = True
        """Whether the scaler has been trained."""

class MLPClassifierTrainer(MLPClassifierImplementationBase):
    """
    This class is used to train the models and scalers that produce recommendations
    for the neural network implementation.
    """
    def __init__(self, modes: List[ModelMode], train_existing_models: bool = True):
        self._modes = modes
        self._train_existing_models = train_existing_models
        self._data_scaled = False
        if train_existing_models:
            # "generic" models
            self._generic_approved = self.load_model("generic_approved")
            self._generic_voted = self.load_model("generic_voted")
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
        """
        Return the model dictionaries associated with the given ModelMode.
        """
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
        """
        Create a ModelScalerAndData object for a new model
        """
        new_model = ModelScalerAndData(MLPClassifier(max_iter=max_iter, hidden_layer_sizes=(500,250,100,50)), StandardScaler(), name)
        new_model.scaler_has_been_trained = False
        return new_model

    def _add_data(self, repository: str, status: str, data_frame: pandas.DataFrame, training_data: bool) -> None:
        """
        Add training or testing data for use in training or testing.

        :param repository: The repository this training/testing data is on
        :param status: The status of the change associated with this training/testing data item
        :param data_frame: The DataFrame for this training/testing data item
        :param training_data: True if this is training data. False is this is testing data.
        """
        if self._data_scaled:
            # If the data has been scaled, then more data cannot be added.
            raise Exception("Data has already been used to train or test. Cannot add more data as existing data has been scaled. Save the model and load it again to add more testing/training data.")
        # Convert status to ModelMode enum
        status = ModelMode(status)
        # Load models (if needed) and then add the data to each of the ModelScalerAndData objects that exist.
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
        """
        Add training data to be used when training the models.

        :param repository: The repository this change is on
        :param status: The status of the change
        :param data_frame: The DataFrame for this change
        """
        self._add_data(repository, status, data_frame, True)
        return self

    def add_testing_data(self, repository: str, status: str, data_frame: pandas.DataFrame) -> "MLPClassifierTrainer":
        """
        Add testing data to be used when testing the models.

        :param repository: The repository this change is on
        :param status: The status of the change
        :param data_frame: The DataFrame for this change
        """
        self._add_data(repository, status, data_frame, False)
        return self

    @staticmethod
    def load_model(name: str) -> ModelScalerAndData:
        """
        Load the model with the given name from the disk.
        """
        loaded_model = MLPClassifierImplementation.load_model_and_associated_scaler(name)
        return ModelScalerAndData(loaded_model[0], loaded_model[1], name)

    def _add_data_to_model_dictionary(self, dictionary: dict, repository: str, appendix: str,
                                      data_frame: pandas.DataFrame, training_data: bool) -> None:
        # Load the model if it is not already loaded
        if repository and repository not in dictionary.keys():
            if self._train_existing_models and os.path.exists(MLPClassifierImplementation.get_model_path(common.get_sanitised_filename(repository) + appendix)):
                dictionary[repository] = self.load_model(common.get_sanitised_filename(repository) + appendix)
            else:
                dictionary[repository] = self._create_new_model(common.get_sanitised_filename(repository) + appendix)
        # Add the model
        self._add_data_to_model(dictionary[repository], data_frame, training_data)

    def _add_data_to_model(self, model: ModelScalerAndData, data_frame: pandas.DataFrame,
                           training_data: bool) -> None:
        # Replace NaN values with zeros.
        data_frame = data_frame.fillna(0)
        # If this is training data add to the training data list, otherwise add to the testing data list.
        if training_data:
            model.X_train.append(data_frame.iloc[:, :-2])
            model.approved_train.append(data_frame.loc[:, "Actually approved"].replace({0: False}))
            model.voted_train.append(data_frame.loc[:, "Actually voted"].replace({0: False}))
        else:
            model.X_test.append(data_frame.iloc[:, :-2])
            model.approved_test.append(data_frame.loc[:, "Actually approved"].replace({0: False}))
            model.voted_test.append(data_frame.loc[:, "Actually voted"].replace({0: False}))

    def perform_training(self) -> "MLPClassifierTrainer":
        """
        Train the models using the data added for the training via ::add_training_data.
        """
        # First scale the data
        self._scale_data()
        logging.debug("Training")
        for mode in ModelMode:
            if mode not in self._modes:
                continue
            for models, target in zip(self._get_model_dictionaries(mode), ["approved", "voted"]):
                # For each model that is being trained, use the changes added to be used for training
                #  to train the models.
                if isinstance(models, ModelScalerAndData):
                    # Handle "generic" with only one model for approved and one for voted.
                    models = {'generic': models}
                for model in models.values():
                    # Train the model using the training data
                    if target == "approved":
                        for X, approved in zip(model.under_sampled_approved_X_train,
                                               model.under_sampled_approved_train):
                            try:
                                model.model.fit(X, approved)
                            except ValueError as e:
                                logging.error("Training failed for one data point for model " + model.name, exc_info=e)
                    else:
                        for X, voted in zip(model.under_sampled_voted_X_train,
                                               model.under_sampled_voted_train):
                            try:
                                model.model.fit(X, voted)
                            except ValueError as e:
                                logging.error("Training failed for one data point for model " + model.name, exc_info=e)
        return self

    def perform_testing(self) -> dict:
        """
        Perform testing on the trained models using the data added for the testing via ::add_testing_data.
        """
        # First check that the data is scaled (if the models are loaded instead of being trained, then the data
        #  could be unscaled).
        self._scale_data()
        logging.debug("Testing")
        return_dict = {}
        for mode in ModelMode:
            if mode not in self._modes:
                continue
            for models, target in zip(self._get_model_dictionaries(mode), ["approved", "voted"]):
                # Generate an accuracy score and confusion matrix for each change for each model.
                #  Then get the average, min, max, 10th percentile and 90th percentile for the
                #  accuracy scores and each value in the confusion matrix per model.
                if isinstance(models, ModelScalerAndData):
                    # Handle "generic" with only one model for approved and one for voted.
                    models = {'generic': models}
                for model in models.values():
                    return_dict[model.name] = {
                        'accuracy_score': {
                            'average': None,
                            'min': None,
                            'max': None,
                            '10th-percentile': None,
                            '90th-percentile': None,
                            '_all_scores': []
                        },
                        'confusion_matrix': {
                            'true-positive': {
                                'average': None,
                                'min': None,
                                'max': None,
                                '10th-percentile': None,
                                '90th-percentile': None,
                                '_all_scores': []
                            },
                            'false-positive': {
                                'average': None,
                                'min': None,
                                'max': None,
                                '10th-percentile': None,
                                '90th-percentile': None,
                                '_all_scores': []
                            },
                            'false-negative': {
                                'average': None,
                                'min': None,
                                'max': None,
                                '10th-percentile': None,
                                '90th-percentile': None,
                                '_all_scores': []
                            },
                            'true-negative': {
                                'average': None,
                                'min': None,
                                'max': None,
                                '10th-percentile': None,
                                '90th-percentile': None,
                                '_all_scores': []
                            },
                        }
                    }
                    try:
                        # Train the model using the training data
                        def test_model(model: ModelScalerAndData, targets: list):
                            """
                            Helper method used to test the model given in the associated
                            ModelScalerAndData object.
                            """
                            for i, X in enumerate(model.X_test_scaled):
                                # Average the accuracy score
                                try:
                                    # Get the prediction for the testing data
                                    prediction = model.model.predict(X)
                                    # Compare this prediction against the actual values to get the accuracy
                                    #  score and confusion matrix. Add these to a list of all the scores which
                                    #  will be grouped into min, max, average, 10th percentile and 90th percentile
                                    #  later on in min_max_average_and_percentiles() below.
                                    accuracy_score_for_change = accuracy_score(targets[i], prediction)
                                    return_dict[model.name]['accuracy_score']['_all_scores'].append(accuracy_score_for_change)
                                    confusion_matrix_for_change = confusion_matrix(targets[i], prediction).ravel()
                                    tn, fp, fn, tp = [0] * 4
                                    match len(confusion_matrix_for_change):
                                        case 1:
                                            tn = confusion_matrix_for_change[0]
                                        case 2:
                                            tn, fp = confusion_matrix_for_change
                                        case 3:
                                            tn, fp, fn = confusion_matrix_for_change
                                        case 4:
                                            tn, fp, fn, tp = confusion_matrix_for_change
                                    return_dict[model.name]['confusion_matrix']['true-negative']['_all_scores'].append(tn)
                                    return_dict[model.name]['confusion_matrix']['true-positive']['_all_scores'].append(tp)
                                    return_dict[model.name]['confusion_matrix']['false-negative']['_all_scores'].append(fn)
                                    return_dict[model.name]['confusion_matrix']['false-positive']['_all_scores'].append(fp)
                                except NotFittedError:
                                    return
                                except ValueError as e:
                                    logging.error("Error when testing " + model.name + ". Skipping this change.", exc_info=e)
                            def min_max_average_and_percentiles(result_dictionary: dict):
                                """
                                Using the result dictionary for a model provided in the first argument,
                                make the min, max, average, 10th percentile and 90th percentile. Then clear
                                the all scores list.
                                """
                                # min
                                if not len(result_dictionary['_all_scores']):
                                    return
                                result_dictionary['min'] = min(result_dictionary['_all_scores'])
                                # max
                                result_dictionary['max'] = max(result_dictionary['_all_scores'])
                                # Average
                                result_dictionary['average'] = sum(result_dictionary['_all_scores'])
                                result_dictionary['average'] = result_dictionary['average'] / len(result_dictionary['_all_scores'])
                                # 10% and 90% percentiles
                                result_dictionary['10th-percentile'] = numpy.percentile(
                                    result_dictionary['_all_scores'], 10, method='closest_observation')
                                result_dictionary['90th-percentile'] = numpy.percentile(
                                    result_dictionary['_all_scores'], 90, method='closest_observation')
                                del result_dictionary['_all_scores']
                            # Create min, max, average and 10% percentile values for accuracy
                            min_max_average_and_percentiles(return_dict[model.name]['accuracy_score'])
                            # Do the same as above for the confusion matrix
                            for confusion_matrix_element_dict in return_dict[model.name]['confusion_matrix'].values():
                                min_max_average_and_percentiles(confusion_matrix_element_dict)
                            logging.debug("Model testing results for " + model.name + ": " + str(return_dict[model.name]))
                        if target == "approved":
                            test_model(model, model.approved_test)
                        else:
                            test_model(model, model.voted_test)
                    except BaseException as e:
                        # Catch errors in testing so that partial results can be returned.
                        logging.error("Error in testing model " + model.name, exc_info=e)
        return return_dict

    def _scale_data(self) -> None:
        """
        Scale the training and testing data. Scaling is skipped if this method has
        already been called, as the data will have been scaled.
        """
        logging.debug("Scaling data")
        if self._data_scaled:
            return
        self._data_scaled = True
        for mode in ModelMode:
            if mode not in self._modes:
                continue
            for models in self._get_model_dictionaries(mode):
                # Scale the data for each of the models.
                if isinstance(models, ModelScalerAndData):
                    # Handle "generic" with only one model for approved and one for voted.
                    models = {'generic': models}
                for model in models.values():
                    try:
                        # If not training existing models, train the scaler
                        if not model.scaler_has_been_trained:
                            for X in model.X_train:
                                model.scaler.fit(X)
                            model.scaler_has_been_trained = True
                        for X, approved, voted in zip(model.X_train, model.approved_train, model.voted_train):
                            # Scale the data - In models trained for the report, this try block is commented
                            #  out to fix an issue as discussed in section 4.2.3.
                            try:
                                X[X.columns] = model.scaler.transform(X[X.columns])
                            except ValueError as e:
                                logging.error(
                                    "Transform failed for " + model.name + " on one training data item. This has been skipped.",
                                    exc_info=e)
                                continue
                            # Under-sample the training data to reduce bias towards not recommending
                            approved: Series
                            if True in approved.values and False in approved.values:
                                under_sampled_approved_X, under_sampled_approved = model.approved_under_sampler.fit_resample(X, approved)
                                model.under_sampled_approved_X_train.append(under_sampled_approved_X)
                                model.under_sampled_approved_train.append(under_sampled_approved)
                            if True in voted.values and False in voted.values:
                                under_sampled_voted_X, under_sampled_voted = model.voted_under_sampler.fit_resample(X, voted)
                                model.under_sampled_voted_X_train.append(under_sampled_voted_X)
                                model.under_sampled_voted_train.append(under_sampled_voted)
                        for X in model.X_test:
                            # Scale the data - In models trained for the report, the scaling of the data is commented
                            #  out to fix the issue as discussed in section 4.2.3.
                            try:
                                X[X.columns] = model.scaler.transform(X[X.columns])
                                model.X_test_scaled.append(X)
                            except ValueError:
                                logging.error("Transform failed for " + model.name + " on one testing data item. This has been skipped.")
                                continue
                    except BaseException as e:
                        logging.error("Error in scaling data for model " + model.name, exc_info=e)

    def save_models(self) -> None:
        """
        Save the models by pickling them to a file.
        """
        for mode in ModelMode:
            for models in self._get_model_dictionaries(mode):
                # Save each model and associated scaler in a separate file to allow loading only
                #  the required models when using them to recommend.
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

    def get_training_and_testing_change_specific_data_frame(self, repository: str, change_info: dict,
                                                            base_data_frame_for_repo: pandas.DataFrame) -> pandas.DataFrame:
        """
        Generate a pandas DataFrame that is used to train or test the models. The result of
        this is typically passed to ::add_training_data or ::add_testing_data.

        :param repository: The repository the change is on
        :param change_info: The change information dictionary associated with the change
        :param base_data_frame_for_repo: The DataFrame for the repository as generated by
         ::preprocess_into_pandas_data_frame()
        """
        change_specific_data_frame = self.add_change_specific_attributes_to_data_frame(repository,
                                                                                  change_info,
                                                                                  base_data_frame_for_repo)
        # Store lowercase representation to actual case used for indexing purposes
        index_names_to_name = {common.convert_name_to_index_format(x): x for x in change_specific_data_frame.index.values}
        # Add columns for whether the users actually voted or approved in the DataFrame
        change_specific_data_frame["Actually voted"] = False
        change_specific_data_frame["Actually approved"] = False
        # Go through the code review votes in the change
        for vote in change_info['code_review_votes']:
            def is_name_in_data_frame(key_for_name_in_vote: str) -> Union[str, bool]:
                """
                Helper function that returns a Truthy value if the value for the key specified
                in the first parameter inside the vote dictionary exists as a name in the DataFrame.
                Returns False otherwise.
                """
                if key_for_name_in_vote in vote:
                    index_name = common.convert_name_to_index_format(vote[key_for_name_in_vote])
                    if index_name in index_names_to_name.keys():
                        return index_names_to_name[index_name]
                return False
            # Try to find associated data_frame row
            name = is_name_in_data_frame('name')
            if not name:
                name = is_name_in_data_frame('display_name')
                if not name:
                    name = is_name_in_data_frame('username')
                    if not name:
                        # No matching name found in the data frame. Add the name under the key 'name' to the data frame.
                        change_specific_data_frame.loc[vote['name'], :] = 0
                        index_names_to_name.update({common.convert_name_to_index_format(vote['name']): vote['name']})
            change_specific_data_frame.at[vote['name'], "Actually voted"] = True
            if vote['value'] == 2:
                # Was an approval vote
                change_specific_data_frame.at[vote['name'], "Actually approved"] = True
        return change_specific_data_frame

if __name__ == "__main__":
    # Only allows command line arguments, which are got via the argparse library.
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
    # Exclude models from training that have been excluded using command line flags.
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
    # Create the trainer object.
    MLP_trainer = MLPClassifierTrainer(models_to_train, command_line_arguments.train_existing_models)
    repos_and_associated_members = json.load(open(
        common.path_relative_to_root("data_collection/raw_data/members_of_mediawiki_repos.json")
    ))
    for number_processed, repository in enumerate(repos_and_associated_members['groups_for_repository'].keys()):
        if repositories and repository not in repositories:
            continue
        try:
            # For each repository get the test data associated with the repo and create the
            #  DataFrame for the repository.
            test_data = get_test_data_for_repo(repository)
            if test_data is None:
                continue
            logging.debug("Processing " + repository + " which is " + str(number_processed + 1) + "out of" +
                  str(len(repos_and_associated_members['groups_for_repository'].keys())))
            print("Processing", repository)
            time_period = test_data[0]
            test_data = test_data[1]
            base_data_frame_for_repo = MLP_trainer.preprocess_into_pandas_data_frame(repository)[time_period]
            for status, sub_test_data in test_data.items():
                try:
                    # For each status of change in the training/testing data, add these changes as training and testing
                    #  data if there is at least two changes.
                    logging.debug("Status: " + status)
                    for change_id in sub_test_data.keys():
                        sub_test_data[change_id]["id"] = change_id
                    sub_test_data = list(sub_test_data.values())
                    if len(sub_test_data) <= 1:
                        # Skip if only one or zero changes.
                        continue
                    # Split the training and testing data set randomly.
                    train, test = train_test_split(sub_test_data)
                    train = list(train)
                    test = list(test)
                    for i, change_info in enumerate(train):
                        # Add the training data
                        print("Collating training data", i+1, "out of", len(train))
                        logging.info("Collating training data " + str(i) + " out of " + str(len(train)))
                        MLP_trainer.add_training_data(
                            repository, status, MLP_trainer.get_training_and_testing_change_specific_data_frame(
                                repository, change_info, base_data_frame_for_repo
                            )
                        )
                    for i, change_info in enumerate(test):
                        # Add the testing data
                        print("Collating test data", i+1, "out of", len(test))
                        logging.info("Collating test data " + str(i) + " out of " + str(len(train)))
                        MLP_trainer.add_testing_data(
                            repository, status, MLP_trainer.get_training_and_testing_change_specific_data_frame(
                                repository, change_info, base_data_frame_for_repo
                            )
                        )
                except BaseException as e:
                    # If an uncaught exception is thrown which is anything other than a
                    #  KeyboardInterrupt, just skip this particular status of changes for this repository
                    # This is done so that failure a few changes doesn't cause the model training to need
                    #  to be restarted which could add hours of time needed to train the model.
                    if isinstance(e, KeyboardInterrupt):
                        raise e
                    # Log this error if it is not a KeyboardInterrupt
                    logging.error("Error", exc_info=e)
                    pass
        except KeyboardInterrupt:
            # Allow KeyboardInterrupt to stop adding testing/training changes and move to training/testing the models.
            break
        except BaseException as e:
            # If there is an uncaught exception (other than KeyboardInterrupt), then skip this repository
            #  and move to the next to prevent the script from ending hours into a run.
            logging.error("Error in processing repository " + repository + " not caught elsewhere.", exc_info=e)
            pass
    print("Training....")
    # Perform the training.
    MLP_trainer.perform_training()
    print("Testing....")
    # Perform the testing
    test_results = MLP_trainer.perform_testing()
    # Save the test results to a JSON file
    json.dump(test_results, open(common.path_relative_to_root("evaluation/results/neural_network_training_test_results.json"), 'w'), cls=NpEncoder)
    # Save the models to a pickle file
    MLP_trainer.save_models()