import json
import logging
import os
import urllib.parse
import time
from collections.abc import Iterable
from functools import lru_cache
from json import JSONDecodeError
from typing import Union

import ijson
import requests
from data_collection.generate_elastic_search_query import ElasticSearchQueryBuilder
from cs4529_secrets import Secrets

# Hide urllib3's logs for "info" and "debug" type as these are unlikely to be useful when inspecting the logs
logging.getLogger("urllib3").setLevel(logging.WARNING)

root_path = os.path.dirname(__file__)

extensions_list = [line.strip() for line in open(os.path.join(root_path,
                                                              "data_collection/raw_data/extensions_list.txt"), "r").readlines()]
extensions_repository_list = [ "mediawiki/extensions/" + extension for extension in extensions_list ]

group_exclude_list = ['2bc47fcadf4e44ec9a1a73bcfa06232554f47ce2', 'cc37d98e3a4301744a0c0a9249173ae170696072', 'd3fd0fc1835b11637da792ad2db82231dd8f73cb']

email_exclude_list = ["tools.libraryupgrader@tools.wmflabs.org"]

secrets = Secrets()

gerrit_url_prefix = 'https://gerrit.wikimedia.org/r/'

gerrit_api_url_prefix = gerrit_url_prefix + 'a/'

elasticsearch_request_headers = {'kbn-xsrf': 'true', 'content-type': 'application/json'}
gerrit_search_url = 'https://wikimedia.biterg.io/data/gerrit/_search'
git_search_url = 'https://wikimedia.biterg.io/data/git/_search'
phabricator_search_url = 'https://wikimedia.biterg.io/data/phabricator/_search'

def perform_elastic_search_request(search_query: Union[str, ElasticSearchQueryBuilder]) -> dict:
    if isinstance(search_query, ElasticSearchQueryBuilder):
        search_query = search_query.get_json()
    logging.debug("Performing elastic search query: " + search_query)
    response = requests.get(
        gerrit_search_url,
        headers=elasticsearch_request_headers,
        data=search_query
    )
    logging.debug("Response: " + response.text)
    try:
        response = json.loads(response.text)
    except JSONDecodeError:
        logging.error("Elastic search response not valid JSON.")
        return {'error': True}
    if not isinstance(response, dict) or 'error' in response.keys():
        # Invalid response or query errored out - return as an error
        logging.error("Elastic search query errored.")
        return {'error': True}
    if 'timed_out' in response.keys() and response['timed_out']:
        # Log as skipped
        logging.warning("Elastic search query timed out.")
        return {'timed_out': True}
    return response

def remove_gerrit_api_json_response_prefix( text_content: str ):
    return text_content.replace(")]}'", "", 1).strip()

def path_relative_to_root(relative_path):
    return os.path.join( root_path, relative_path )

@lru_cache(maxsize=32)
def get_main_branch_for_repository(repository: str):
    # Rate-limiting API queries
    time.sleep(0.5)
    request_url = gerrit_api_url_prefix + 'projects/' + urllib.parse.quote(repository, safe='') + '/HEAD'
    logging.debug("Request made for repo head: " + request_url)
    return json.loads(remove_gerrit_api_json_response_prefix(
        requests.get(request_url, auth=secrets.gerrit_http_credentials()).text
    ))

class TimePeriods(Iterable):
    ALL_TIME = 'all time'
    LAST_YEAR = 'last year'
    LAST_3_MONTHS = 'last three months'
    LAST_MONTH = 'last month'
    DATE_RANGES = [ALL_TIME, LAST_YEAR, LAST_3_MONTHS, LAST_MONTH]

    def __iter__(self):
        return iter(self.DATE_RANGES)

@lru_cache(maxsize=5)
def get_test_data_for_repo(repository: str) -> dict[str, dict]:
    # TODO: Update to not use the copied file
    with open(path_relative_to_root('data_collection/raw_data/test_data_set.json'), 'rb') as f:
        for item in ijson.items(f, repository):
            return item