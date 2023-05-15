"""
File of common functions and code used throughout the project code.
"""
import json
import logging
import os
import re
import urllib.parse
import time
from enum import Enum
from functools import lru_cache
import ijson
import requests
from pathvalidate import sanitize_filename
from cs4529_secrets import Secrets

# Hide urllib3's logs for "info" and "debug" type as these are unlikely
#  to be useful when inspecting the logs
logging.getLogger("urllib3").setLevel(logging.WARNING)

root_path = os.path.dirname(__file__)

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

extensions_list = [
    line.strip() for line in open(
        os.path.join(root_path, "data_collection/raw_data/extensions_list.txt"), "r"
    ).readlines()
]
extensions_repository_list = [ "mediawiki/extensions/" + extension for extension in extensions_list ]

group_exclude_list = ['2bc47fcadf4e44ec9a1a73bcfa06232554f47ce2', 'cc37d98e3a4301744a0c0a9249173ae170696072', 'd3fd0fc1835b11637da792ad2db82231dd8f73cb']

email_exclude_list = ["tools.libraryupgrader@tools.wmflabs.org", "l10n-bot@translatewiki.net"]

email_exclude_list = [convert_email_to_index_format(name) for name in email_exclude_list]

username_exclude_list = ["Libraryupgrader", "TrainBranchBot", "gerrit2", "Gerrit Code Review", "[BOT] Gerrit Code Review", "[BOT] Gerrit Patch Uploader"]

username_exclude_list = [convert_name_to_index_format(name) for name in username_exclude_list]

username_to_email_map = {
    'Anais Gueyte': 'agueyte@wikimedia.org',
    'MarcoAurelio': 'maurelio@toolforge.org',
    'Sam Reed': 'reedy@wikimedia.org',
    'Thalia Chan': 'thalia.e.chan@googlemail.com',
    'Thiemo Kreuz': 'thiemo.kreuz@wikimedia.de',
    'Stephanie Tran': 'stran@wikimedia.org',
    'Tsepo Thoabala': 'tthoabala@wikimedia.org',
    'Dbarratt': 'david@davidwbarratt.com',
    'Kunal Mehta': 'legoktm@debian.org',
    'Andre Klapper': ' aklapper@wikimedia.org'
}

username_to_email_map = {convert_name_to_index_format(name): email for name, email in username_to_email_map.items()}

secrets = Secrets()

gerrit_url_prefix = 'https://gerrit.wikimedia.org/r/'

gerrit_api_url_prefix = gerrit_url_prefix + 'a/'

def remove_gerrit_api_json_response_prefix(text_content: str) -> str:
    """
    Remove the ")]}'" characters from the Gerrit API response which is added
    to help CRSF attacks.
    """
    return text_content.replace(")]}'", "", 1).strip()

def path_relative_to_root(relative_path):
    """
    Create the absolute path for a path that is relative to the root directory.
    """
    return os.path.join(root_path, relative_path)

@lru_cache(maxsize=32)
def get_main_branch_for_repository(repository: str):
    """
    Asks the Gerrit API for the main branch for the given repository. This is usually "master", but can be "main".

    :param repository: The repository to get the main branch for.
    """
    # Rate-limiting API queries
    time.sleep(0.5)
    request_url = gerrit_api_url_prefix + 'projects/' + urllib.parse.quote(repository, safe='') + '/HEAD'
    logging.debug("Request made for repo head: " + request_url)
    return json.loads(remove_gerrit_api_json_response_prefix(
        requests.get(request_url, auth=secrets.gerrit_http_credentials()).text
    ))

def get_sanitised_filename(filename: str) -> str:
    """
    Gets a filename that is sanitised such that it is a valid filename
    and does not include a directory seperator.
    """
    return sanitize_filename(re.sub(r'/', '-', filename))

class TimePeriods(Enum):
    """
    The possible time periods used when the data can be collected from different time periods.
    """
    ALL_TIME = 'all time'
    LAST_YEAR = 'last year'
    LAST_3_MONTHS = 'last three months'
    LAST_MONTH = 'last month'

@lru_cache(maxsize=5)
def get_test_data_for_repo(repository: str) -> tuple:
    """
    Load the training and testing data set for a given repository. This method
    does not load the full training and testing data set into memory to get the
    training and testing data set for this repository.

    This is done using ijson's kvitems method that iteratively reads the JSON file.

    :param repository: The repository to load the testing and training data set for.
    """
    with open(path_relative_to_root('data_collection/raw_data/test_data_set.json'), 'rb') as f:
        for item in ijson.kvitems(f, 'item.' + repository):
            # Should only be one item with the repository name, so return this.
            return item
