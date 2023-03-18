import datetime
import json
import urllib.parse
import requests
import time
from dateutil.relativedelta import relativedelta
from data_collection import common
import logging

logging.basicConfig(filename="logs_for_test_data_generation.txt", level=logging.DEBUG)

def filter_information_for_changes(changes: list) -> dict:
    filtered_changes = {}
    for change in changes:
        try:
            filtered_changes[change['id']] = {
                'change_id': change['change_id'],
                'branch': change['branch'],
                'reviewers': {},
                'code_review_votes': []
            }
            if 'Code-Review' in change['labels'] and 'all' in change['labels']['Code-Review']:
                for code_review_vote in change['labels']['Code-Review']['all']:
                    if 'tags' in code_review_vote.keys() and 'SERVICE_USER' in code_review_vote['tags']:
                        # Filter out bots by filtering out "service users" who should only be bots
                        continue
                    filtered_changes[change['id']]['code_review_votes'].append(code_review_vote)
            for reviewer_type in change['reviewers']:
                filtered_changes[change['id']]['reviewers'][reviewer_type] = []
                for reviewer in change['reviewers'][reviewer_type]:
                    # Filter out bots by filtering out "service users" who should only be bots
                    if 'tags' not in reviewer.keys() or 'SERVICE_USER' not in reviewer['tags']:
                        filtered_changes[change['id']]['reviewers'][reviewer_type].append(reviewer)
        except BaseException as e:
            print("Error:", repr(e))
            logging.error("Error thrown when filtering data: ", repr(e))
    return filtered_changes

def generate_test_data_set_for_repo(repository: str, cutoff_time: str = None):
    test_data = {"merged": [], "abandoned": [], "open": []}
    # Merged changes
    request_url = common.gerrit_api_url_prefix + "changes/?o=DETAILED_LABELS&o=DETAILED_ACCOUNTS&q=status:merged+-is:wip+repo:" + repository
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
    request_url = common.gerrit_api_url_prefix + "changes/?o=DETAILED_LABELS&o=DETAILED_ACCOUNTS&q=status:open+-label:Code-Review=0+-is:wip+repo:" + repository
    if cutoff_time is not None:
        request_url += "+after:" + urllib.parse.quote('"') + cutoff_time + urllib.parse.quote('"')
    logging.debug("Request made for open changes: " + request_url)
    test_data["open"] = filter_information_for_changes(json.loads(common.remove_gerrit_api_json_response_prefix(
        requests.get(request_url, auth=common.secrets.gerrit_http_credentials()).text
    )))
    # Abandoned changes - cannot use "mergedafter" as abandoned changes are never merged.
    request_url = common.gerrit_api_url_prefix + "changes/?o=DETAILED_LABELS&o=DETAILED_ACCOUNTS&q=status:abandoned+-is:wip+repo:" + repository
    if cutoff_time is not None:
        request_url += "+after:" + urllib.parse.quote('"') + cutoff_time + urllib.parse.quote('"')
    logging.debug("Request made for abandoned changes: " + request_url)
    test_data["abandoned"] = filter_information_for_changes(json.loads(common.remove_gerrit_api_json_response_prefix(
        requests.get(request_url, auth=common.secrets.gerrit_http_credentials()).text
    )))
    return test_data

test_data = {"has changes from last 30 days": {}, "has changes from last 3 months": {}, "has changes from last year": {}, "has changes from last 3 years": {}, "has changes from all time": {}}
try:
    repos = list(json.load(open(common.path_relative_to_root("raw_data/mediawiki_repos.json"), "r")).keys())
    for number_processed, repo in enumerate(repos):
        print("Processing", repo + ". Done", number_processed, "out of", len(repos))
        logging.info("Processing " + repo)
        for name, time_unit in {"has changes from last 30 days": relativedelta(days=30), "has changes from last 3 months": relativedelta(months=3), "has changes from last year": relativedelta(years=1), "has changes from last 3 years": relativedelta(years=3), "has changes from all time": None}.items():
            logging.debug("Trying " + name)
            # Rate limiting
            time.sleep(0.5)
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
            test_data[name][repo] = response
            # We have the testing data now, so break early
            logging.debug("Successful with " + name)
            break
        time.sleep(1)
finally:
    json.dump(test_data, open(common.path_relative_to_root("raw_data/test_data_set.json"), "w"))