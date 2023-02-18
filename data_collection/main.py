import json
import pickle
import time
import numpy
import requests as requests
import pandas
import requests
import glob
import xml.etree.ElementTree as ET
import matplotlib.pyplot as plt
from scipy.stats import pearsonr, ttest_ind

elasticsearch_request_headers = {'kbn-xsrf': 'true', 'content-type': 'application/json'}
gerrit_search_url = 'https://wikimedia.biterg.io/data/gerrit/_search'
git_search_url = 'https://wikimedia.biterg.io/data/git/_search'
phabricator_search_url = 'https://wikimedia.biterg.io/data/phabricator/_search'