import json
import time
import logging
from typing import AnyStr, Union
import common
from dateutil.relativedelta import relativedelta
import datetime
from data_collection.generate_elastic_search_query import ElasticSearchQueryBuilder, \
    ElasticSearchAggregationGroupBuilder, ElasticSearchAggregationBuilder, FiltersItemBuilder, \
    perform_elastic_search_request

if __name__ == "__main__":
    logging.basicConfig(
        filename=common.path_relative_to_root("logs/generate_reviewer_votes.log.txt"),
        level=logging.DEBUG
    )

def generate_votes_for_repository(repository: str, cutoff_time: int = None, filter: Union[AnyStr, list, None] = None) -> dict:
    """
    Generate the code review data for the specified repository and return it.

    :param repository: The repository to collect data for
    :param cutoff_time: The end of the time period to collect data from (which starts from the current time). None for
     no time period limiting
    :param filter: Filter results only for the user(s) specified in this argument
    """
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
    repos_and_associated_members = json.load(open(
        common.path_relative_to_root("data_collection/raw_data/members_of_mediawiki_repos.json")))
    for number_processed, (repo, associated_groups) in enumerate(repos_and_associated_members['groups_for_repository'].items()):
        author_vote_count_for_repo[repo] = {}
        try:
            print("Processing", repo + ". Completed", number_processed, "out of", len(repos_and_associated_members['groups_for_repository']))
            logging.info("Processing " + repo)
            # Collect from all time
            logging.debug("First trying all time")
            author_vote_count_for_repo[repo].update({
                common.TimePeriods.ALL_TIME.value: generate_votes_for_repository(repo) #, filter=group_member_names)
            })
            # Collect from the last year
            logging.debug("Trying from last year")
            one_year_ago = datetime.datetime.now() - relativedelta(years=1)
            author_vote_count_for_repo[repo].update({
                common.TimePeriods.LAST_YEAR.value: generate_votes_for_repository(repo, cutoff_time=int(time.mktime(one_year_ago.timetuple()) * 1_000))
            })
            # Collect from the last three months
            logging.debug("Trying from last 3 months")
            three_months_ago = datetime.datetime.now() - relativedelta(months=3)
            author_vote_count_for_repo[repo].update({
                common.TimePeriods.LAST_3_MONTHS.value: generate_votes_for_repository(repo, cutoff_time=int(time.mktime(three_months_ago.timetuple()) * 1_000))
            })
            # Collect from the last month
            logging.debug("Trying from last 30 days")
            thirty_days_ago = datetime.datetime.now() - relativedelta(days=30)
            author_vote_count_for_repo[repo].update({
                common.TimePeriods.LAST_MONTH.value: generate_votes_for_repository(repo, cutoff_time=int(time.mktime(thirty_days_ago.timetuple()) * 1_000))
            })
            # Crude rate-limiting - 1 second should be enough to avoid issues
            time.sleep(1)
        except BaseException as e:
            print("Failed for ", repo)
            logging.error('Error thrown when processing ' + repo + '. Error: ' + str(repr(e)))
finally:
    # Finally save the collected JSON data,
    #  even if an exception occurred (and therefore only partial data was collected)
    json.dump(author_vote_count_for_repo, open(
        common.path_relative_to_root("data_collection/raw_data/reviewer_votes_for_repos.json"), "w"
    ))