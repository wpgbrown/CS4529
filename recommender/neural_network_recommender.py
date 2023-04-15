import pandas
import numpy
import re
from sklearn import metrics, preprocessing
import common

print(pandas.read_json(common.path_relative_to_root("data_collection/raw_data/reviewer_vote_percentages_for_repos.json")))