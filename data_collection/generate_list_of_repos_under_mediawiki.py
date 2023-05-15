import json
import logging
import urllib.parse

import requests
import common


def generate_list_of_repos(output_file_name, prefix: str = ''):
    """
    Generates a list of repositories that start with a prefix.

    If the prefix ends with a '/' the repository with the name after
    that slash is removed is also added.

    :param output_file_name: The file to output the json result to
    :param prefix: The prefix to filter using
    :return:
    """
    repository_list = {}
    try:
        # Make the request from the Gerrit API
        request_url = common.gerrit_api_url_prefix + "projects/?p=" + urllib.parse.quote(prefix, safe='')
        logging.debug(request_url)
        repository_list.update(json.loads(common.remove_gerrit_api_json_response_prefix(
            requests.get(request_url, auth=common.secrets.gerrit_http_credentials()).text)
        ))
        # If ends with a slash, try for repo without the slash as well.
        if prefix.endswith('/'):
            request_url = common.gerrit_api_url_prefix + "projects/" + urllib.parse.quote(prefix.rstrip('/'), safe='')
            repository_list[prefix.rstrip('/')] = json.loads(
                common.remove_gerrit_api_json_response_prefix(
                    requests.get(request_url, auth=common.secrets.gerrit_http_credentials()).text)
            )
    finally:
        # Save the list to a JSON file.
        json.dump(repository_list, open(output_file_name, "w"))

# Generate data
generate_list_of_repos("raw_data/mediawiki_repos.json", 'mediawiki/')