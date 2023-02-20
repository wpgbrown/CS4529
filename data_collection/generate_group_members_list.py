import json
import time
import more_itertools
import requests
from data_collection import common


def generate_reviewers_list( repositories ):
    members_of_groups = {}
    try:
        for batch_id, repository_batch in enumerate(more_itertools.chunked(repositories, 25)):
            print("Batch", batch_id)
            # Batch repos by 25 for request
            request_url = common.gerrit_api_url_prefix + "access/?project=" + repository_batch[0]
            for repository in repository_batch[1:]:
                request_url += "&project=" + repository
            members_of_groups.update(json.loads(requests.get(request_url, auth=common.secrets.gerrit_http_credentials()).text.replace(")]}'", '')))
            time.sleep(1)
    finally:
        json.dump( members_of_groups, open( "raw_data/members_of_groups_data.json", "w" ) )

def get_reviewer_data_for_extensions():
    generate_reviewers_list([ "mediawiki/extensions/" + extension for extension in common.extensions_list ])

get_reviewer_data_for_extensions()