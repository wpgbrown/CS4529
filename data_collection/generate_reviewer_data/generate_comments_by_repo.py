import json
import time
import logging
import common
from dateutil.relativedelta import relativedelta
import datetime
from data_collection.generate_elastic_search_query import ElasticSearchQueryBuilder, \
    ElasticSearchAggregationGroupBuilder, ElasticSearchAggregationBuilder, perform_elastic_search_request

if __name__ == "__main__":
    logging.basicConfig(
        filename=common.path_relative_to_root("logs/generate_comments_by_repo.log.txt"),
        level=logging.DEBUG
    )

def generate_comment_stats_for_repository(repository: str, cutoff_time: int = None) -> dict:
    """
    Generate the comment data for each user for a specified repository and cutoff_time, and then
     return the result to the caller.

    :param repository: The repository to generate the comment stats for
    :param cutoff_time: The timestamp for the end of the period that data is to be collected for.
        None for no time range.
    :return: The comment data stats.
    """
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

# Store the generated comment stats to be saved as a JSON file later
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
            # Get data for all time
            comments_by_users_for_each_repo[repo].update({
                common.TimePeriods.ALL_TIME.value: generate_comment_stats_for_repository(repo)
            })
            logging.debug("Trying from last year")
            # Get data from the last year
            one_year_ago = datetime.datetime.now() - relativedelta(years=1)
            comments_by_users_for_each_repo[repo].update({
                common.TimePeriods.LAST_YEAR.value: generate_comment_stats_for_repository(repo, cutoff_time=int(time.mktime(one_year_ago.timetuple()) * 1_000))
            })
            logging.debug("Trying from last 3 months")
            # Get data from the three months
            three_months_ago = datetime.datetime.now() - relativedelta(months=3)
            comments_by_users_for_each_repo[repo].update({
                common.TimePeriods.LAST_3_MONTHS.value: generate_comment_stats_for_repository(repo, cutoff_time=int(time.mktime(three_months_ago.timetuple()) * 1_000))
            })
            logging.debug("Trying from last 30 days")
            # Get data from the last month
            thirty_days_ago = datetime.datetime.now() - relativedelta(days=30)
            comments_by_users_for_each_repo[repo].update({
                common.TimePeriods.LAST_MONTH.value: generate_comment_stats_for_repository(repo, cutoff_time=int(time.mktime(thirty_days_ago.timetuple()) * 1_000))
            })
            # Crude rate-limiting - 1 second should be enough to avoid issues
            time.sleep(1)
        except BaseException as e:
            print("Failed for ", repo)
            logging.error('Error thrown when processing ' + repo + '. Error: ' + str(repr(e)))
finally:
    # Save the results, even if the generation failed for any reason. Partial results would be useful
    #  in knowing where the issue was.
    json.dump(comments_by_users_for_each_repo, open(
        common.path_relative_to_root("data_collection/raw_data/comments_by_author_for_repo.json"), "w"))