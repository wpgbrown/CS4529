import datetime
import json
import urllib.parse
from typing import List

import requests
import time
from dateutil.relativedelta import relativedelta
import common
import logging
from common import TimePeriods

if __name__ == "__main__":
    logging.basicConfig(
        filename=common.path_relative_to_root("logs/generate_test_data_set.log.txt"),
        level=logging.DEBUG
    )

def filter_information_for_changes(changes: list) -> dict:
    """
    Filter the information for each change returned by the Gerrit changes API
    for information that is wanted for the training and testing data set.

    :param changes: The list of raw changes data returned from the Gerrit changes API
    """
    filtered_changes = {}
    for change in changes:
        if "_more_changes" in change:
            # Log this as it means only some of the changes were collected for the training and testing data
            #  set where more could have been got.
            logging.warning("Too many changes according to API")
        try:
            # Collect the associated change ID and branch
            new_filtered_change = {
                'change_id': change['change_id'],
                'branch': change['branch'],
                'reviewers': {},
                'code_review_votes': []
            }
            # Collect the owner of the change to allowing filtering
            #  out the owner when making recommendations.
            if 'owner' in change:
                new_filtered_change['owner'] = change['owner']
                if 'tags' in change['owner'] and 'SERVICE_USER' in change['owner']['tags']:
                    # Skip changes owned by bots (i.e. created by bots)
                    continue
                if 'status' in new_filtered_change['owner']:
                    del new_filtered_change['owner']['status']
            # Collect any tracking IDs, such as Phabricator ticket IDs
            if 'tracking_ids' in change:
                new_filtered_change['tracking_ids'] = change['tracking_ids']
            # Collect the files modified in the change
            #  and if specified the SHAs for the parent commits.
            if 'current_revision' in change:
                if change['current_revision'] in change['revisions']:
                    new_filtered_change.update({
                        'files': change['revisions'][change['current_revision']]['files']
                    })
                new_filtered_change['current_revision'] = change['current_revision']
                if 'commit' in change['revisions'][change['current_revision']]:
                    new_filtered_change['parent_shas'] = [x['commit'] for x in change['revisions'][change['current_revision']]['commit']['parents']]
            # Collect the total comment count on the change and number of unresolved comments
            if 'total_comment_count' in change:
                new_filtered_change['comment_count'] = change['total_comment_count']
            if 'unresolved_comment_count' in change and change['unresolved_comment_count'] != 0:
                new_filtered_change['unresolved_comment_count'] = change['unresolved_comment_count']
            # Collate and collect code review votes
            if 'Code-Review' in change['labels'] and 'all' in change['labels']['Code-Review']:
                for code_review_vote in change['labels']['Code-Review']['all']:
                    if 'tags' in code_review_vote.keys() and 'SERVICE_USER' in code_review_vote['tags']:
                        # Filter out bots by filtering out "service users" who should only be bots
                        continue
                    # Filter out unused data
                    if 'status' in code_review_vote:
                        del code_review_vote['status']
                    if 'permitted_voting_range' in code_review_vote:
                        del code_review_vote['permitted_voting_range']
                    new_filtered_change['code_review_votes'].append(code_review_vote)
            # Collate and collect the reviewers on the change (different to code review votes, as
            #  some reviewers may not have voted and therefore won't appear in that list).
            for reviewer_type in change['reviewers']:
                new_filtered_change['reviewers'][reviewer_type] = []
                for reviewer in change['reviewers'][reviewer_type]:
                    # Filter out bots by filtering out "service users" who should only be bots
                    if 'tags' not in reviewer.keys() or 'SERVICE_USER' not in reviewer['tags']:
                        # Filter out unused "status" text.
                        if 'status' in reviewer:
                            del reviewer['status']
                        new_filtered_change['reviewers'][reviewer_type].append(reviewer)
            filtered_changes[change['id']] = new_filtered_change
        except BaseException as e:
            # Catch random errors, log them and then continue to prevent early exiting
            #  in this long-running script.
            print("Error:", repr(e))
            logging.error("Error thrown when filtering data: " + str(repr(e)))
    return filtered_changes

def base_test_data_request_url(repository: str) -> str:
    return common.gerrit_api_url_prefix + "changes/?o=SKIP_DIFFSTAT&o=DETAILED_LABELS&o=DETAILED_ACCOUNTS&o=CURRENT_REVISION&o=CURRENT_FILES&o=TRACKING_IDS&o=CURRENT_COMMIT&q=-is:wip+repo:" + repository

def generate_test_data_set_for_repo(repository: str, cutoff_time: str = None):
    test_data = {"merged": [], "abandoned": [], "open": []}
    # Collect merged changes
    request_url = base_test_data_request_url(repository) + "+status:merged"
    if cutoff_time is not None:
        request_url += "+mergedafter:" + urllib.parse.quote('"') + cutoff_time + urllib.parse.quote('"')
    logging.debug("Request made for merged changes: " + request_url)
    test_data["merged"] = filter_information_for_changes(json.loads(common.remove_gerrit_api_json_response_prefix(
        requests.get(request_url, auth=common.secrets.gerrit_http_credentials()).text
    )))
    if len(test_data["merged"]) < 10 and cutoff_time is not None:
        # If the merged changes count is under 10, then tell the caller
        #  to use a bigger time period by returning None.
        logging.debug("Returning early because merged count too small.")
        return None
    # Open changes with code review votes
    request_url = base_test_data_request_url(repository) + "+status:open+-label:Code-Review=0"
    if cutoff_time is not None:
        request_url += "+after:" + urllib.parse.quote('"') + cutoff_time + urllib.parse.quote('"')
    logging.debug("Request made for open changes: " + request_url)
    test_data["open"] = filter_information_for_changes(json.loads(common.remove_gerrit_api_json_response_prefix(
        requests.get(request_url, auth=common.secrets.gerrit_http_credentials()).text
    )))
    # Abandoned changes with code review votes - cannot use "mergedafter" as abandoned changes are never merged.
    request_url = base_test_data_request_url(repository) + "+status:abandoned+-label:Code-Review=0"
    if cutoff_time is not None:
        request_url += "+after:" + urllib.parse.quote('"') + cutoff_time + urllib.parse.quote('"')
    logging.debug("Request made for abandoned changes: " + request_url)
    test_data["abandoned"] = filter_information_for_changes(json.loads(common.remove_gerrit_api_json_response_prefix(
        requests.get(request_url, auth=common.secrets.gerrit_http_credentials()).text
    )))
    return test_data

# The following code is a modified version of the code detailed at https://stackoverflow.com/a/45143995
#  which was created by Werner Smit.
class StreamArray(list):
    """
    Converts a generator into a list object that can be json serialisable
    while still retaining the iterative nature of a generator.
    """
    def __init__(self, repositories, generator):
        super().__init__()
        self.generator = generator
        self._repositories = repositories
        self._len = 1

    def __iter__(self):
        self._len = 0
        for item in self.generator(self._repositories):
            yield item
            self._len += 1

    def __len__(self):
        return self._len
# End from https://stackoverflow.com/a/45143995

def generate_test_data_for_repos(repositories: List[str]):
    """
    Create and yield the training and testing data set for the list of repositories provided.

    :param repositories: The repositories to collect this data set for.
    """
    for number_processed, repo in enumerate(repositories):
        test_data = {}
        try:
            print("Processing", repo + ". Done", number_processed, "out of", len(repos))
            logging.info("Processing " + repo)
            for name, time_unit in {TimePeriods.LAST_MONTH.value: relativedelta(month=1),
                                    TimePeriods.LAST_3_MONTHS.value: relativedelta(months=3),
                                    TimePeriods.LAST_YEAR.value: relativedelta(years=1),
                                    TimePeriods.ALL_TIME.value: None}.items():
                # Try to get the training and testing data set from the smallest time period
                #  while still ensuring at least 10 merged changes.
                logging.debug("Trying " + name)
                # Rate limiting
                time.sleep(2)
                if time_unit is not None:
                    time_unit = datetime.datetime.now() - time_unit
                    time_unit = time_unit.strftime("%Y-%m-%d %H:%M:%S")
                response = generate_test_data_set_for_repo(repo, time_unit)
                if response is None and time_unit is not None:
                    # If the cutoff didn't generate enough results to use for testing,
                    #  then instead try a larger time period unless the time unit was
                    #  for all time
                    logging.debug("Skipped " + name)
                    continue
                test_data[name] = response
                # We have the testing data now, so break early
                logging.debug("Successful with " + name)
                break
            time.sleep(3)
            # Yield the training and testing data. Collecting as a dictionary of items
            #  and then returning at once would be an inefficient use of memory.
            yield {repo: test_data}
        except BaseException as e:
            if isinstance(e, GeneratorExit):
                raise e
            print("Error:", repr(e))
            logging.error("Error thrown when generating data: " + str(repr(e)))

repos = list(json.load(open(common.path_relative_to_root("data_collection/raw_data/mediawiki_repos.json"), "r")).keys())
with open(common.path_relative_to_root("data_collection/raw_data/test_data_set.json"), "w") as f:
    # Load the training and testing data set for the repositories one-by-one and then save it
    #  to the data set JSON file in chunks to avoid running out of memory.
    for chunk in json.JSONEncoder().iterencode(StreamArray(repos, generate_test_data_for_repos)):
        f.write(chunk)