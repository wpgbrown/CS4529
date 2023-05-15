import json
import time
import requests
import common
import logging

if __name__ == "__main__":
    logging.basicConfig(
        filename=common.path_relative_to_root("logs/generate_members_of_groups.log.txt"),
        level=logging.DEBUG
    )

def generate_members_of_repository(repositories, output_file_name='', recursive=True, return_instead=False, check_only=None):
    """
    Generate members of given repositories based on their groups

    :param repositories: Data in groups_with_access_to_*.json files
    :type repositories: dict
    :param output_file_name: Where to put this data (encoded as json)
    :type output_file_name: str
    :param recursive: Whether members of parent groups should be included
    :type recursive: bool
    """
    members_in_group = {}
    groups_for_repository = {}
    try:
        to_process = repositories
        if check_only is not None:
            to_process = {check_only: to_process[check_only]}
        for processed_count, (repository, data) in enumerate(to_process.items()):
            if repository in groups_for_repository.keys():
                # A repository can be already processed if it was a parent of another already processed
                #  repository and recursive hasn't been set to False.
                continue
            logging.info("Processing " + repository + " with " + str(processed_count) + " processed out of " + str(len(to_process)))
            print("Processing", repository, "with", processed_count, "processed out of", len(to_process))
            groups_for_repository[repository] = {}
            logging.debug("Data for " + repository + ": " + str(data))
            for group_uuid, group_data in data['groups'].items():
                logging.info("Processing group: " + group_data['name'])
                groups_for_repository[repository].update({group_uuid: group_data['name']})
                members_in_group[group_uuid] = []
                request_url = common.gerrit_api_url_prefix + "groups/" + group_uuid + "/members/"
                logging.debug("Request made: " + request_url)
                try:
                    members_in_group[group_uuid].extend(
                        json.loads(common.remove_gerrit_api_json_response_prefix(
                            requests.get(request_url, auth=common.secrets.gerrit_http_credentials()).text
                        ))
                    )
                except json.decoder.JSONDecodeError:
                    # Notify about invalid JSON and just skip it
                    logging.warning("Invalid JSON detected in response for repository " + repository)
            if recursive:
                try:
                    inherits_from = data['inherits_from']['name']
                except KeyError:
                    inherits_from = ''
                if inherits_from.strip() != '' and inherits_from in repositories.keys():
                    if inherits_from not in groups_for_repository.keys():
                        logging.info("Needed to generate data for " + inherits_from)
                        # Climb the parent tree
                        inherits_from_result = generate_members_of_repository(repositories, check_only=inherits_from, return_instead=True)
                        groups_for_repository.update(inherits_from_result['groups_for_repository'])
                        members_in_group.update(inherits_from_result['members_in_group'])
                    # Add members which are members for the parent, as these will have access to this repo
                    groups_for_repository[repository].update(groups_for_repository[inherits_from])
            time.sleep(1)
    except BaseException as e:
        # Catch exceptions to prevent the script stopping when collecting the data
        #  which can take a while to complete (and thus stopping nearly all the way through
        #  would cause delay).
        logging.warning("Unexpected exception")
        logging.warning(type(e))
    finally:
        # Finally save the data to a JSON file.
        final_data = {'groups_for_repository': groups_for_repository, 'members_in_group': members_in_group}
        if return_instead:
            return final_data
        json.dump(final_data, open(output_file_name, "w"))

# Generate group member data for all mediawiki/*
group_data_per_repository = json.load(open(
    common.path_relative_to_root("data_collection/raw_data/groups_with_access_to_extensions.json")))
group_data_per_repository.update(json.load(open(
    common.path_relative_to_root("data_collection/raw_data/groups_with_access_to_all_other_repos.json"))))
generate_members_of_repository(group_data_per_repository, common.path_relative_to_root("data_collection/raw_data/members_of_mediawiki_repos.json"))