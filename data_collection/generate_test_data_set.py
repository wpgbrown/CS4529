import json
import time
import requests
from data_collection import common
from data_collection.generate_elastic_search_query import ElasticSearchQueryBuilder, \
    ElasticSearchAggregationGroupBuilder, ElasticSearchAggregationBuilder


def generate_test_data_set_for_repository( repository, cutoff_time ):
    elastic_search_query_builder = ElasticSearchQueryBuilder()\
        .match_all()\
        .repository(repository)\
        .in_range(cutoff_time, time.time_ns() // 1_000)\
        .exclude_bots()\
        .aggregation(ElasticSearchAggregationBuilder(2).terms('author_name', 5000, {"1": "desc"}))\
        .aggregation(ElasticSearchAggregationGroupBuilder().aggregation(
            ElasticSearchAggregationBuilder(3).sum('is_gerrit_approval')
        ))
    print(elastic_search_query_builder.get_json())
    exit()
    response = requests.get(
        common.gerrit_search_url,
        headers=common.elasticsearch_request_headers,
        data=elastic_search_query_builder.get_json()
    )
    response_data = json.loads(response.text)
    print(response_data)

generate_test_data_set_for_repository( "mediawiki/extensions/CheckUser", 1653064312571 )