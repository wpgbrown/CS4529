import requests

from . import common

with open("groups_list.json", "w") as f:
    f.write( requests.get( common.gerrit_api_url_prefix + "groups", auth=common.secrets.gerrit_http_credentials ).json() )