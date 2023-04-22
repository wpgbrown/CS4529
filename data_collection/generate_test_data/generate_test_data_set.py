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
import sys

if __name__ == "__main__":
    logging.basicConfig(
        filename=common.path_relative_to_root("logs/generate_test_data_set.log.txt"),
        level=logging.DEBUG
    )

def filter_information_for_changes(changes: list) -> dict:
    filtered_changes = {}
    for change in changes:
        if "_more_changes" in change:
            logging.warning("Too many changes according to API")
        try:
            filtered_changes[change['id']] = {
                'change_id': change['change_id'],
                'branch': change['branch'],
                'reviewers': {},
                'code_review_votes': []
            }
            if 'owner' in change:
                filtered_changes[change['id']]['owner'] = change['owner']
                if 'status' in filtered_changes[change['id']]['owner']:
                    del filtered_changes[change['id']]['owner']['status']
            if 'tracking_ids' in change:
                filtered_changes[change['id']]['tracking_ids'] = change['tracking_ids']
            if 'current_revision' in change and change['current_revision'] in change['revisions']:
                filtered_changes[change['id']].update({
                    'files': change['revisions'][change['current_revision']]['files']
                })
            if 'total_comment_count' in change:
                filtered_changes[change['id']]['comment_count'] = change['total_comment_count']
            if 'unresolved_comment_count' in change and change['unresolved_comment_count'] != 0:
                filtered_changes[change['id']]['unresolved_comment_count'] = change['unresolved_comment_count']
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
                    filtered_changes[change['id']]['code_review_votes'].append(code_review_vote)
            for reviewer_type in change['reviewers']:
                filtered_changes[change['id']]['reviewers'][reviewer_type] = []
                for reviewer in change['reviewers'][reviewer_type]:
                    # Filter out bots by filtering out "service users" who should only be bots
                    if 'tags' not in reviewer.keys() or 'SERVICE_USER' not in reviewer['tags']:
                        # Filter out unused "status" text.
                        if 'status' in reviewer:
                            del reviewer['status']
                        filtered_changes[change['id']]['reviewers'][reviewer_type].append(reviewer)
        except BaseException as e:
            print("Error:", repr(e))
            logging.error("Error thrown when filtering data: " + str(repr(e)))
    return filtered_changes

def generate_test_data_set_for_repo(repository: str, cutoff_time: str = None):
    test_data = {"merged": [], "abandoned": [], "open": []}
    # Merged changes
    # TODO: Move URL generation to function as much is duplicated
    request_url = common.gerrit_api_url_prefix + "changes/?o=SKIP_DIFFSTAT&o=DETAILED_LABELS&o=DETAILED_ACCOUNTS&o=CURRENT_REVISION&o=CURRENT_FILES&o=TRACKING_IDS&q=status:merged+-is:wip+repo:" + repository
    if cutoff_time is not None:
        request_url += "+mergedafter:" + urllib.parse.quote('"') + cutoff_time + urllib.parse.quote('"')
    logging.debug("Request made for merged changes: " + request_url)
    test_data["merged"] = filter_information_for_changes(json.loads(common.remove_gerrit_api_json_response_prefix(
        requests.get(request_url, auth=common.secrets.gerrit_http_credentials()).text
    )))
    if len(test_data["merged"]) < 10 and cutoff_time is not None:
        logging.debug("Returning early because merged count too small.")
        # Tell the caller to use a larger time period or all time.
        return None
    # Open changes
    request_url = common.gerrit_api_url_prefix + "changes/?o=SKIP_DIFFSTAT&o=DETAILED_LABELS&o=DETAILED_ACCOUNTS&o=CURRENT_REVISION&o=CURRENT_FILES&o=TRACKING_IDS&q=status:open+-label:Code-Review=0+-is:wip+repo:" + repository
    if cutoff_time is not None:
        request_url += "+after:" + urllib.parse.quote('"') + cutoff_time + urllib.parse.quote('"')
    logging.debug("Request made for open changes: " + request_url)
    test_data["open"] = filter_information_for_changes(json.loads(common.remove_gerrit_api_json_response_prefix(
        requests.get(request_url, auth=common.secrets.gerrit_http_credentials()).text
    )))
    # Abandoned changes - cannot use "mergedafter" as abandoned changes are never merged.
    request_url = common.gerrit_api_url_prefix + "changes/?o=SKIP_DIFFSTAT&o=DETAILED_LABELS&o=DETAILED_ACCOUNTS&o=CURRENT_REVISION&o=CURRENT_FILES&o=TRACKING_IDS&q=status:abandoned+-is:wip+repo:" + repository
    if cutoff_time is not None:
        request_url += "+after:" + urllib.parse.quote('"') + cutoff_time + urllib.parse.quote('"')
    logging.debug("Request made for abandoned changes: " + request_url)
    test_data["abandoned"] = filter_information_for_changes(json.loads(common.remove_gerrit_api_json_response_prefix(
        requests.get(request_url, auth=common.secrets.gerrit_http_credentials()).text
    )))
    return test_data

# Start from https://stackoverflow.com/a/45143995 (but modified slightly)
class StreamArray(list):
    """
    Converts a generator into a list object that can be json serialisable
    while still retaining the iterative nature of a generator.

    IE. It converts it to a list without having to exhaust the generator
    and keep it's contents in memory.
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
    test_data = {}
    for number_processed, repo in enumerate(repositories):
        try:
            print("Processing", repo + ". Done", number_processed, "out of", len(repos))
            logging.info("Processing " + repo)
            for name, time_unit in {TimePeriods.LAST_MONTH: relativedelta(month=1),
                                    TimePeriods.LAST_3_MONTHS: relativedelta(months=3),
                                    TimePeriods.LAST_YEAR: relativedelta(years=1), TimePeriods.ALL_TIME: None}.items():
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
            yield {repo: test_data}
        except BaseException as e:
            print("Error:", repr(e))
            logging.error("Error thrown when generating data: " + str(repr(e)))

repos = list(json.load(open(common.path_relative_to_root("data_collection/raw_data/mediawiki_repos.json"), "r")).keys())
with open(common.path_relative_to_root("data_collection/raw_data/test_data_set.json"), "w") as f:
    for chunk in json.JSONEncoder().iterencode(StreamArray(repos, generate_test_data_for_repos)):
        f.write(chunk)