"""
Generates a JSON list of groups for further processing by
calling the API and then saving this list to a file.

TODO: Unused?
"""

import requests
import common

with open("raw_data/groups_list.json", "w") as f:
    f.write(requests.get(common.gerrit_api_url_prefix + "groups/", auth=common.secrets.gerrit_http_credentials()).text.replace(")]}'", ''))
