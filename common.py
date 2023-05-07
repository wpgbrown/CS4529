import json
import logging
import os
import re
import urllib.parse
import time
from functools import lru_cache
from json import JSONDecodeError
from typing import Union
import ijson
import requests
from pathvalidate import sanitize_filename
from data_collection.generate_elastic_search_query import ElasticSearchQueryBuilder
from cs4529_secrets import Secrets

# Hide urllib3's logs for "info" and "debug" type as these are unlikely to be useful when inspecting the logs
logging.getLogger("urllib3").setLevel(logging.WARNING)

root_path = os.path.dirname(__file__)

extensions_list = [line.strip() for line in open(os.path.join(root_path,
                                                              "data_collection/raw_data/extensions_list.txt"), "r").readlines()]
extensions_repository_list = [ "mediawiki/extensions/" + extension for extension in extensions_list ]

group_exclude_list = ['2bc47fcadf4e44ec9a1a73bcfa06232554f47ce2', 'cc37d98e3a4301744a0c0a9249173ae170696072', 'd3fd0fc1835b11637da792ad2db82231dd8f73cb']

email_exclude_list = ["tools.libraryupgrader@tools.wmflabs.org", "l10n-bot@translatewiki.net"]

username_exclude_list = ["Libraryupgrader", "TrainBranchBot", "gerrit2", "Gerrit Code Review", "[BOT] Gerrit Code Review", "[BOT] Gerrit Patch Uploader"]

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

def remove_gerrit_api_json_response_prefix(text_content: str) -> str:
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

def get_sanitised_filename(filename: str) -> str:
    return sanitize_filename(re.sub(r'/', '-', filename))

def convert_name_to_index_format(name: str) -> str:
    """
    Strips whitespace, makes lowercase, replaces the following with spaces:
    * -
    * _

    :param name: The name / username
    :returns: Name in the format for the name index
    """
    return name.strip().lower().replace('-', ' ').replace('_', ' ')

def convert_email_to_index_format(email: str) -> str:
    """
    Strips whitespace and makes lowercase

    :param email: The email address
    :returns: Email in the format for the email index
    """
    return email.strip().lower()

class TimePeriods:
    ALL_TIME = 'all time'
    LAST_YEAR = 'last year'
    LAST_3_MONTHS = 'last three months'
    LAST_MONTH = 'last month'
    DATE_RANGES = [ALL_TIME, LAST_YEAR, LAST_3_MONTHS, LAST_MONTH]

@lru_cache(maxsize=5)
def get_test_data_for_repo(repository: str) -> tuple:
    # TODO: Update from the copy
    with open(path_relative_to_root('data_collection/raw_data/test_data_set.json'), 'rb') as f:
        for item in ijson.kvitems(f, 'item.' + repository):
            # Should only be one item with the repository name, so return this.
            return item