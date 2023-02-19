import pickle
import string
import itertools
import requests

from . import common

def generate_reviewers_list( repositories ):
    members_of_groups = []
    try:
        for repository_batch in itertools(repositories):
            # Batch repos by 100s
            members_of_groups.append(get_reviewer_data_for_gerrit_repo(repository))
    finally:
        pickle.dump( members_of_groups, open( "raw_data/members_of_groups_data.dump", "w" ) )

def get_reviewer_data_for_gerrit_repo( repository: string ):
    return requests.get( common.gerrit_api_url_prefix + "access/?project=" + repository + "/members" )