import itertools
import json
import logging
import pickle
import re
import numpy
import requests
import seaborn as sns
from matplotlib import pyplot as plt
from pathvalidate import sanitize_filename
from sklearn.preprocessing import StandardScaler
import pandas
import time
import urllib.parse
from sklearn.metrics import accuracy_score, confusion_matrix
from sklearn.model_selection import train_test_split
from sklearn.neural_network import MLPClassifier
import common
from comment_votes_and_members_of_repos_to_data_frame import preprocess_into_pandas_data_frame
from data_collection import git_blame
from recommender import Recommendations
from common import get_test_data_for_repo



def add_change_specific_attributes_to_data_frame(repository: str, change_info: dict, data_frame: pandas.DataFrame) -> pandas.DataFrame:
    data_frame = data_frame.copy(True)
    time_period_to_key = {y: y.replace(' ', '_') + "_lines_count" for y in common.TimePeriods.DATE_RANGES}
    # print(change_info)
    # Get the files modified (added, changed or deleted) by the change
    # TODO: Merge with rule based recommender code if possible to reduce duplication
    for name in itertools.chain.from_iterable([
        [y + x for y in common.TimePeriods.DATE_RANGES] for x in
        [" author git blame percentage", " reviewer git blame percentage"]
    ]):
        data_frame[name] = 0
    # print(data_frame.columns.array)
    if total_delta_over_all_files != 0:
        for file, info in information_about_change_including_git_blame_stats_in_head.items():
            logging.debug(info)
            time_period_to_key = {y: y.replace(' ', '_') + "_lines_count" for y in common.TimePeriods.DATE_RANGES}
            author_sums = {}
            for time_period, name in time_period_to_key.items():
                author_sums[time_period] = sum([x[name] for x in info['blame_stats']['authors'].values()])
            committer_sums = {}
            for time_period, name in time_period_to_key.items():
                committer_sums[time_period] = sum([x[name] for x in info['blame_stats']['committers'].values()])
            for author_email, author_info in info['blame_stats']['authors'].items():
                if author_info['name'][0] not in data_frame.index.values:
                    data_frame.loc[author_info['name'][0], :] = 0
                # print(author_info)
                for time_period, name in {y: y + " author git blame percentage" for y in
                                          common.TimePeriods.DATE_RANGES}.items():
                    if not author_sums[time_period]:
                        continue
                    data_frame.at[author_info['name'][0], name] += (author_info[time_period_to_key[time_period]] /
                                                                    author_sums[time_period]) * (info[
                                                                                                     'size_delta'] / total_delta_over_all_files)
            for committer_email, committer_info in info['blame_stats']['committers'].items():
                if committer_info['name'][0] not in data_frame.index.values:
                    data_frame.loc[committer_info['name'][0], :] = 0
                for time_period, name in {y: y + " reviewer git blame percentage" for y in
                                          common.TimePeriods.DATE_RANGES}.items():
                    if not committer_sums[time_period]:
                        continue
                    data_frame.at[committer_info['name'][0], name] += (committer_info[time_period_to_key[time_period]] /
                                                                       committer_sums[time_period]) * (info[
                                                                                                           'size_delta'] / total_delta_over_all_files)
    return data_frame