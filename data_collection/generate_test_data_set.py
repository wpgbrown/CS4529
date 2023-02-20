import json
import time
import requests
from data_collection import common
from data_collection.generate_elastic_search_query import ElasticSearchQueryBuilder


def generate_test_data_set_for_repository( repository, cutoff_time ):
    elastic_search_query_builder = ElasticSearchQueryBuilder()\
        .match_all()\
        .repository(repository)\
        .in_range(cutoff_time, time.time_ns() // 1_000)\
        .exclude_bots().
    response = requests.get(
        common.gerrit_search_url,
        headers=common.elasticsearch_request_headers,
        data=.get_json()
    )
    response_data = json.loads(response.text)
    print(response_data)

generate_test_data_set_for_repository( "mediawiki/extensions/CheckUser", 1653064312571 )