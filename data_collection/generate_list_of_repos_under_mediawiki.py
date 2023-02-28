import json
import time
import urllib.parse

import requests
from data_collection import common

def generate_list_of_repos( output_file_name, prefix: str = '' ):
    repository_list = {}
    try:
        request_url = common.gerrit_api_url_prefix + "projects/?p=" + urllib.parse.quote(prefix, safe='')
        print(request_url)
        repository_list.update(json.loads(
            common.remove_gerrit_api_json_response_prefix(requests.get(request_url, auth=common.secrets.gerrit_http_credentials()).text)
        ))
        print(repository_list)
    finally:
        json.dump( repository_list, open( output_file_name, "w" ) )

# Generate data
generate_list_of_repos("raw_data/mediawiki_repos.json", 'mediawiki/')