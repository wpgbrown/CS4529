import json
import time
import requests
from data_collection import common
from data_collection.generate_elastic_search_query import ElasticSearchQueryBuilder, \
    ElasticSearchAggregationGroupBuilder, ElasticSearchAggregationBuilder, FiltersItemBuilder


def generate_test_data_set_for_repository( repository, cutoff_time ):
    elastic_search_query_builder = ElasticSearchQueryBuilder()\
        .match_all()\
        .repository(repository)\
        .in_range(cutoff_time, time.time_ns() // 1_000)\
        .exclude_bots()\
        .aggregation(
            ElasticSearchAggregationBuilder(2).terms('author_name', 5000, {"1": "desc"}).aggregation(
                ElasticSearchAggregationGroupBuilder().aggregations(
                    ElasticSearchAggregationBuilder(1).sum('is_gerrit_approval'),
                    ElasticSearchAggregationBuilder(3).sum_bucket('3-bucket>_count'),
                    ElasticSearchAggregationBuilder(4).sum_bucket('4-bucket>_count'),
                    ElasticSearchAggregationBuilder(5).sum_bucket('5-bucket>_count'),
                    ElasticSearchAggregationBuilder(6).sum_bucket('6-bucket>_count'),
                    ElasticSearchAggregationBuilder('3-bucket').filters(
                        FiltersItemBuilder().query_string('-2 code review vote', "approval_value:\"-2\"", "*", True)),
                    ElasticSearchAggregationBuilder('4-bucket').filters(
                        FiltersItemBuilder().query_string('-1 code review vote', "approval_value:\"-1\"", "*", True)),
                    ElasticSearchAggregationBuilder('5-bucket').filters(
                        FiltersItemBuilder().query_string('1 code review vote', "approval_value:\"1\"", "*", True)),
                    ElasticSearchAggregationBuilder('6-bucket').filters(
                        FiltersItemBuilder().query_string('2 code review vote', "approval_value:\"2\"", "*", True))
                )
            )
        )
    print(elastic_search_query_builder.get_pretty_json())
    response = requests.get(
        common.gerrit_search_url,
        headers=common.elasticsearch_request_headers,
        data=elastic_search_query_builder.get_json()
    )
    response_data = json.loads(response.text)
    print(response_data)
    print(json.dumps(response_data, indent=2))

generate_test_data_set_for_repository( "mediawiki/extensions/CheckUser", 1653064312571 )