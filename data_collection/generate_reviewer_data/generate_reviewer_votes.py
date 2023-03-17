import json
import time
import logging
from typing import AnyStr, Union
from data_collection import common
from dateutil.relativedelta import relativedelta
import datetime
from data_collection.common import perform_elastic_search_request
from data_collection.generate_elastic_search_query import ElasticSearchQueryBuilder, \
    ElasticSearchAggregationGroupBuilder, ElasticSearchAggregationBuilder, FiltersItemBuilder

logging.basicConfig(filename="logs_for_generate_author_votes.txt", level=logging.DEBUG)

def generate_votes_for_repository(repository: str, cutoff_time: int = None, filter: Union[AnyStr, list, None] = None):
    elastic_search_query_builder = ElasticSearchQueryBuilder() \
        .match_all() \
        .repository(repository) \
        .exclude_bots() \
        .aggregation(ElasticSearchAggregationBuilder(2).terms('author_name', 5000, {"1": "desc"}).aggregation(
            ElasticSearchAggregationGroupBuilder().aggregations(
                ElasticSearchAggregationBuilder(1).sum('is_gerrit_approval'),
                ElasticSearchAggregationBuilder(3).sum_bucket('3-bucket>_count'),
                ElasticSearchAggregationBuilder(4).sum_bucket('4-bucket>_count'),
                ElasticSearchAggregationBuilder(5).sum_bucket('5-bucket>_count'),
                ElasticSearchAggregationBuilder(6).sum_bucket('6-bucket>_count'),
                ElasticSearchAggregationBuilder('3-bucket').filters(
                    FiltersItemBuilder().query_string('-2 code review votes', "approval_value:\"-2\"", "*", True)),
                ElasticSearchAggregationBuilder('4-bucket').filters(
                    FiltersItemBuilder().query_string('-1 code review votes', "approval_value:\"-1\"", "*", True)),
                ElasticSearchAggregationBuilder('5-bucket').filters(
                    FiltersItemBuilder().query_string('1 code review votes', "approval_value:\"1\"", "*", True)),
                ElasticSearchAggregationBuilder('6-bucket').filters(
                    FiltersItemBuilder().query_string('2 code review votes', "approval_value:\"2\"", "*", True))
            )
        )
    )
    if filter is not None:
        if isinstance(filter, str):
            filter = [ filter ]
        elastic_search_query_builder.must_match_phrase('author_name', filter)
    if cutoff_time is not None:
        elastic_search_query_builder.in_range(cutoff_time, time.time_ns() // 1_000)
    response = perform_elastic_search_request(elastic_search_query_builder)
    parsed_response = {}
    for bucket in response['aggregations']['2']['buckets']:
        reviewer = bucket['key']
        parsed_response[reviewer] = {}
        parsed_response[reviewer]['Gerrit approval actions count'] = bucket['1']['value']
        for code_review_bucket_number in range(3, 7):
            code_review_bucket_number = str(code_review_bucket_number)
            code_review_bucket = bucket[code_review_bucket_number]
            name = list(bucket[code_review_bucket_number + '-bucket']['buckets'].keys())[0]
            parsed_response[reviewer][name] = code_review_bucket['value']
    return parsed_response


author_vote_count_for_repo = {}
try:
    repos_and_associated_members = json.load(open(common.path_relative_to_root("raw_data/members_of_mediawiki_repos.json")))
    for number_processed, (repo, associated_groups) in enumerate(repos_and_associated_members['groups_for_repository'].items()):
        author_vote_count_for_repo[repo] = {}
        try:
            print("Processing", repo + ". Completed", number_processed, "out of", len(repos_and_associated_members['groups_for_repository']))
            logging.info("Processing " + repo)
            group_member_names = []
            for group_uuid, group_name in associated_groups.items():
                if group_uuid in common.group_exclude_list:
                    continue
                group_member_names.extend(map(lambda author_info: author_info['name'], repos_and_associated_members['members_in_group'][group_uuid]))
            # De-duplicate members because they can be in more than one group
            group_member_names = list(set(group_member_names))
            logging.debug("First trying all time")
            author_vote_count_for_repo[repo].update({
                'all': generate_votes_for_repository(repo, filter=group_member_names)
            })
            logging.debug("Trying from last year")
            one_year_ago = datetime.datetime.now() - relativedelta(years=1)
            author_vote_count_for_repo[repo].update({
                'last year': generate_votes_for_repository(repo, filter=group_member_names, cutoff_time=int(time.mktime(one_year_ago.timetuple()) * 1_000))
            })
            logging.debug("Trying from last 3 months")
            three_months_ago = datetime.datetime.now() - relativedelta(months=3)
            author_vote_count_for_repo[repo].update({
                'last 3 months': generate_votes_for_repository(repo, filter=group_member_names, cutoff_time=int(time.mktime(three_months_ago.timetuple()) * 1_000))
            })
            logging.debug("Trying from last 30 days")
            thirty_days_ago = datetime.datetime.now() - relativedelta(days=30)
            author_vote_count_for_repo[repo].update({
                'last 30 days': generate_votes_for_repository(repo, filter=group_member_names, cutoff_time=int(time.mktime(thirty_days_ago.timetuple()) * 1_000))
            })
            # Crude rate-limiting - 1 second should be enough to avoid issues
            time.sleep(1)
        except BaseException as e:
            print("Failed for ", repo)
            logging.error('Error thrown when processing ' + repo + '. Error: ' + str(repr(e)))
finally:
    json.dump(author_vote_count_for_repo, open(common.path_relative_to_root("raw_data/reviewer_votes_for_repos.json"), "w"))