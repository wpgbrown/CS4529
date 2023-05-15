import json
import time
import more_itertools
import requests
import common


def generate_groups_with_access_for_repository(repositories, output_file_name):
    """
    Generate a list of groups that have access for repository in the "repositories"
    parameter.

    :param repositories: Groups to get members for
    :param output_file_name: What the filename for the JSON output should be.
    """
    groups_with_access_to_repository = {}
    try:
        # Batch repos by 25 to ensure the URL limit is not reached and provide some rate limiting.
        for batch_id, repository_batch in enumerate(more_itertools.chunked(repositories, 25)):
            print("Batch", batch_id)
            request_url = common.gerrit_api_url_prefix + "access/?project=" + repository_batch[0]
            for repository in repository_batch[1:]:
                request_url += "&project=" + repository
            # Make the request and add the returned data to the dictionary to save as JSON
            groups_with_access_to_repository.update(json.loads(common.remove_gerrit_api_json_response_prefix(
                requests.get(request_url, auth=common.secrets.gerrit_http_credentials()).text
            )))
            print("Batch done. Total item count:", len(groups_with_access_to_repository))
            # Rate limiting
            time.sleep(1)
    finally:
        json.dump(groups_with_access_to_repository, open(output_file_name, "w"))

# Generate for extensions
generate_groups_with_access_for_repository(common.extensions_repository_list, common.path_relative_to_root("data_collection/raw_data/groups_with_access_to_extensions.json"))

# Generate for mediawiki/* excluding extensions
mediawiki_repos = json.load(open(common.path_relative_to_root("data_collection/raw_data/mediawiki_repos.json"), "r"))
mediawiki_repos = list(mediawiki_repos.keys())
# Filter out extensions - already processed and got above.
mediawiki_repos = [x for x in mediawiki_repos if not x.startswith('mediawiki/extensions/')]
generate_groups_with_access_for_repository(mediawiki_repos, common.path_relative_to_root("data_collection/raw_data/groups_with_access_to_all_other_repos.json"))