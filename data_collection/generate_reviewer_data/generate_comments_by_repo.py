import json
import time
import logging
import common
from dateutil.relativedelta import relativedelta
import datetime
from common import perform_elastic_search_request
from data_collection.generate_elastic_search_query import ElasticSearchQueryBuilder, \
    ElasticSearchAggregationGroupBuilder, ElasticSearchAggregationBuilder

logging.basicConfig(filename="logs_for_generate_comments_by_repo.txt", level=logging.DEBUG)

def generate_comment_stats_for_repository(repository: str, cutoff_time: int = None):
    elastic_search_query_builder = ElasticSearchQueryBuilder() \
        .match_all() \
        .repository(repository) \
        .exclude_bots() \
        .aggregation(ElasticSearchAggregationBuilder(2).terms('author_name', 5000, {"1": "desc"}).aggregation(
            ElasticSearchAggregationGroupBuilder().aggregations(
                ElasticSearchAggregationBuilder(1).sum('is_gerrit_comment')
            )
        )
    )
    if cutoff_time is not None:
        elastic_search_query_builder.in_range(cutoff_time, time.time_ns() // 1_000)
    response = perform_elastic_search_request(elastic_search_query_builder)
    parsed_response = {}
    for bucket in response['aggregations']['2']['buckets']:
        reviewer = bucket['key']
        parsed_response[reviewer] = {}
        parsed_response[reviewer]['Gerrit comment actions count'] = bucket['1']['value']
    return parsed_response


comments_by_users_for_each_repo = {}
try:
    repos_and_associated_members = json.load(open(
        common.path_relative_to_root("data_collection/raw_data/members_of_mediawiki_repos.json")))
    for number_processed, repo in enumerate(repos_and_associated_members['groups_for_repository'].keys()):
        comments_by_users_for_each_repo[repo] = {}
        try:
            print("Processing", repo + ". Completed", number_processed, "out of", len(repos_and_associated_members['groups_for_repository']))
            logging.info("Processing " + repo)
            logging.debug("First trying all time")
            comments_by_users_for_each_repo[repo].update({
                'all': generate_comment_stats_for_repository(repo)
            })
            logging.debug("Trying from last year")
            one_year_ago = datetime.datetime.now() - relativedelta(years=1)
            comments_by_users_for_each_repo[repo].update({
                'last year': generate_comment_stats_for_repository(repo, cutoff_time=int(time.mktime(one_year_ago.timetuple()) * 1_000))
            })
            logging.debug("Trying from last 3 months")
            three_months_ago = datetime.datetime.now() - relativedelta(months=3)
            comments_by_users_for_each_repo[repo].update({
                'last 3 months': generate_comment_stats_for_repository(repo, cutoff_time=int(time.mktime(three_months_ago.timetuple()) * 1_000))
            })
            logging.debug("Trying from last 30 days")
            thirty_days_ago = datetime.datetime.now() - relativedelta(days=30)
            comments_by_users_for_each_repo[repo].update({
                'last 30 days': generate_comment_stats_for_repository(repo, cutoff_time=int(time.mktime(thirty_days_ago.timetuple()) * 1_000))
            })
            # Crude rate-limiting - 1 second should be enough to avoid issues
            time.sleep(1)
        except BaseException as e:
            print("Failed for ", repo)
            logging.error('Error thrown when processing ' + repo + '. Error: ' + str(repr(e)))
finally:
    json.dump(comments_by_users_for_each_repo, open(
        common.path_relative_to_root("data_collection/raw_data/comments_by_author_for_repo.json"), "w"))