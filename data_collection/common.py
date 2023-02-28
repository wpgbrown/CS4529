import json
from typing import Union

import requests

from data_collection.generate_elastic_search_query import ElasticSearchQueryBuilder
from secrets import Secrets

extensions_list = [ line.strip() for line in open("../extensions_list.txt", "r").readlines() ]
extensions_repository_list = [ "mediawiki/extensions/" + extension for extension in extensions_list ]

secrets = Secrets()

gerrit_api_url_prefix = 'https://gerrit.wikimedia.org/r/a/'

elasticsearch_request_headers = {'kbn-xsrf': 'true', 'content-type': 'application/json'}
gerrit_search_url = 'https://wikimedia.biterg.io/data/gerrit/_search'
git_search_url = 'https://wikimedia.biterg.io/data/git/_search'
phabricator_search_url = 'https://wikimedia.biterg.io/data/phabricator/_search'

def perform_elastic_search_request(search_query: Union[str, ElasticSearchQueryBuilder]):
    if isinstance(search_query, ElasticSearchQueryBuilder):
        search_query = search_query.get_json()
    response = requests.get(
        gerrit_search_url,
        headers=elasticsearch_request_headers,
        data=search_query
    )
    return json.loads(response.text)

def remove_gerrit_api_json_response_prefix( text_content: str ):
    return text_content.replace(")]}'", "", 1).strip()