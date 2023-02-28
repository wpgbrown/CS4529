import json
import time
import more_itertools
import requests
from data_collection import common


def generate_reviewers_list( repositories, output_file_name ):
    members_of_groups = {}
    try:
        for batch_id, repository_batch in enumerate(more_itertools.chunked(repositories, 25)):
            print("Batch", batch_id)
            # Batch repos by 25 for request
            request_url = common.gerrit_api_url_prefix + "access/?project=" + repository_batch[0]
            for repository in repository_batch[1:]:
                request_url += "&project=" + repository
            members_of_groups.update(json.loads(common.remove_gerrit_api_json_response_prefix(requests.get(request_url, auth=common.secrets.gerrit_http_credentials()).text)))
            print("Batch done. Total item count:", len(members_of_groups))
            time.sleep(1)
    finally:
        json.dump( members_of_groups, open( output_file_name, "w" ) )

# Generate for extensions

#generate_reviewers_list(common.extensions_repository_list, "raw_data/groups_with_access_to_extensions.json")

# Generate for mediawiki/* excluding extensions
mediawiki_repos = json.load(open("raw_data/mediawiki_repos.json", "r"))
mediawiki_repos = list(mediawiki_repos.keys())
# Filter out extensions - already processed and got above.
mediawiki_repos = [x for x in mediawiki_repos if not x.startswith('mediawiki/extensions/')]
generate_reviewers_list(mediawiki_repos, "raw_data/groups_with_access_to_all_other_repos.json")