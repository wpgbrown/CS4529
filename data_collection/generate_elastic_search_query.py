"""
Generates and performs elastic search query requests to the Bitergia Analytics elastic search API
"""
import json
import logging
from abc import ABCMeta, abstractmethod
from json import JSONDecodeError
from typing import Union, List, Optional

import requests

elasticsearch_request_headers = {'kbn-xsrf': 'true', 'content-type': 'application/json'}
gerrit_search_url = 'https://wikimedia.biterg.io/data/gerrit/_search'

class ElasticSearchQueryBase(metaclass=ABCMeta):
    """
    Common methods to the elastic search query classes.
    """

    @abstractmethod
    def get_dict(self) -> dict:
        """
        Get the dictionary that is generated by this builder object
        """
        return NotImplemented

    def get_json(self, indent: Optional[int] = None) -> str:
        """
        Get the JSON equivalent of the dictionary generated by this builder object

        :param indent: Specify a non-zero positive integer to get a prettyfied version of the JSON
         as provided by json.dumps()
        """
        return json.dumps(self.get_dict(), indent=indent)

    def get_pretty_json(self):
        """
        Gets the JSON in a pretty form. Shortcut for get_json(indent=2).
        """
        return self.get_json(2)

class AggregationBuilderInterface(ElasticSearchQueryBase, metaclass=ABCMeta):
    """Base class for all aggregation related classes. Used to allow typehinting for any of these classes."""


"""
The methods that are used to make the queries are based on queries
used to make the interface panel at biterg.

The builder is made by William Brown
"""
class ElasticSearchQueryBuilder(ElasticSearchQueryBase):
    """
    Main elastic search query builder used to build the overall request parameters.
    Use ::get_json to get the format accepted by the elastic search API endpoint.
    """
    def __init__(self):
        self._aggs = {}
        self._must = []
        self._must_not = []
        self._filter = []
        self._should = []

    def must(self, must):
        self._must.append(must)
        return self

    def must_not(self, must_not):
        self._must_not.append(must_not)
        return self

    def filter(self, filter):
        self._filter.append(filter)
        return self

    def match_all(self):
        self.must({
            "match_all": {}
        })
        return self

    def in_range(self, start, end, field_name="grimoire_creation_date", time_format="epoch_millis"):
        """
        Filter the results in the time range specified by start and end.

        :param start: The start timestamp
        :param end: The end timestamp
        :field_name: The timestamp field name on the Bitergia Analytics system
        :time_format: The format used for the timestamps.
        """
        self.must({
            "range": {
                field_name: {
                    "gte": start,
                    "lte": end,
                    "format": time_format
                }
            }
        })
        return self

    def exclude_bots(self):
        """
        Exclude bots in the results returned by the query.
        """
        self.must_not({
            "match_phrase": {
                "author_bot": {
                    "query": True
                }
            }
        })
        return self

    def repository(self, repository_names: Union[str, List[str]]):
        """
        Filter the results to be from the repositories

        :param repository_names: The repositories that are to be applied as a filter to the results.
        """
        self.must_match_phrase("repository", repository_names)
        return self

    def must_match_phrase(self, field: str, values: Union[str, List[str]], minimum_to_match: int = 1):
        """
        Ensure that the field must have at minimum_to_match items that match in the values parameter

        :param field: The field name on Bitergia Analytics
        :param values: The values to compare to
        :param minimum_to_match: How many of the items in the values parameter should match for
         the must condition to pass
        """
        if not isinstance(values, list):
            self.must({
                "match_phrase": {
                    field: values
                }
            })
            return self
        conditions = []
        for value in values:
            conditions.append({
                "match_phrase": {
                    field: value
                }
            })
        self.must({
            "bool": {
                "should": conditions,
                "minimum_should_match": minimum_to_match
            }
        })
        return self

    def must_query_string(self, query, default_field="*", analyse_wildcard=False):
        """
        Must match the query string specified in the query argument.
        """
        self.must({
            "query_string": {
                "query": query,
                "analyze_wildcard": analyse_wildcard,
                "default_field": default_field
            }
        })
        return self

    def aggregation(self, aggregation: AggregationBuilderInterface):
        """
        Add an aggregation of the returned values to the query
        """
        self._aggs.update(aggregation.get_dict())
        return self

    def get_dict(self) -> dict:
        return {
            "aggs": self._aggs,
            "size": 0,
            "_source": {
                "excludes": []
            },
            "stored_fields": [
                "*"
            ],
            "query": {
                "bool": {
                    "must": self._must,
                    "filter": self._filter,
                    "should": self._should,
                    "must_not": self._must_not
                }
            }
        }

class FiltersItemBuilder(AggregationBuilderInterface):
    """
    Builder for the filters that are used by the aggregations
    """

    def __init__(self):
        self._items = {}

    def add_filter_item(self, name, value):
        self._items.update({name: value})
        return self

    def query_string(self, name, query, default_field: str = "*", analyse_wildcard: bool = False):
        self.add_filter_item(name, {
            "query_string": {
                "query": query,
                "analyze_wildcard": analyse_wildcard,
                "default_field": default_field
            }
        })
        return self

    def get_dict(self):
        return self._items


class ElasticSearchAggregationBuilder(AggregationBuilderInterface):
    """
    Builds an aggregation for the ElasticSearchQueryBuilder.
    """
    def __init__(self, name=''):
        self.name = str(name)
        self.value = {}

    def add_type(self, type_name, value):
        """
        Add a generic aggregation term to the aggregation builder
        """
        self.value.update({type_name: value})
        return self

    def terms(self, field, limit, order, extra=None):
        """
        Add a term to the elastic search query aggregation.

        :param field: The field name
        :param limit: The maximum number of results to select from the field
        :param order: The ordering of the results in this aggregation.
        :param extra: Extra info to pass to ::add_type()
        """
        if extra is None:
            extra = {}
        extra.update({
            'field': field,
            'size': limit,
            'order': order
        })
        self.add_type('terms', extra)
        return self

    def sum(self, field):
        """
        Aggregate the field by summing the values
        """
        self.add_type('sum', {
            'field': field
        })
        return self

    def sum_bucket(self, bucket_path):
        """
        Aggregate the bucket by summing the values
        """
        self.add_type('sum_bucket', {
            "buckets_path": bucket_path
        })
        return self

    def filters(self, filters: Union[List[FiltersItemBuilder], List[dict], FiltersItemBuilder, dict]):
        """
        Apply filter(s) to the aggregation so that only items that match the filter are aggregated

        :param filters: The filters to be used
        """
        if not isinstance(filters, list):
            filters = [ filters ]
        filters_dictionary = {}
        for filter_item in filters:
            try:
                filters_dictionary.update(filter_item.get_dict())
            except AttributeError:
                filters_dictionary.update(filter_item)
        self.add_type('filters', {
           'filters': filters_dictionary
        })
        return self

    def aggregation(self, aggregation: AggregationBuilderInterface):
        """Add an aggregation as a child of this aggregation"""
        if isinstance(aggregation, ElasticSearchAggregationGroupBuilder):
            self.value.update(aggregation.get_dict())
        else:
            self.value.update({'aggs': aggregation.get_dict()})
        return self

    def get_dict(self):
        if self.name == '':
            return self.value
        return {self.name: self.value}

class ElasticSearchAggregationGroupBuilder(AggregationBuilderInterface):
    """
    Builds a group of aggregations
    """
    def __init__(self):
        self._aggregations = {}

    def aggregation(self, value: AggregationBuilderInterface):
        """Add an aggregation to this group"""
        self._aggregations.update(value.get_dict())
        return self

    def aggregations(self, *values: AggregationBuilderInterface):
        """Add aggregations to this group"""
        for value in values:
            self.aggregation(value)
        return self

    def get_dict(self):
        return {
            'aggs': self._aggregations
        }

def try_integer_conversion(value, default=0):
    """
    Try to convert a string to an integer and if this fails
    return the value in the default parameter.
    """
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def perform_elastic_search_request(search_query: Union[str, ElasticSearchQueryBuilder]) -> dict:
    """
    Performs an elastic search request to the Bitergia Analytics API
    using the specified search parameter either as a builder object
    or string.

    Returns a dictionary with the result items. If there is an error
    that means no results are returned, the dictionary will be the
    value {"error": True}.
    """
    if isinstance(search_query, ElasticSearchQueryBuilder):
        search_query = search_query.get_json()
    logging.debug("Performing elastic search query: " + search_query)
    response = requests.get(
        gerrit_search_url,
        headers=elasticsearch_request_headers,
        data=search_query
    )
    logging.debug("Response: " + response.text)
    try:
        response = json.loads(response.text)
    except JSONDecodeError:
        logging.error("Elastic search response not valid JSON.")
        return {'error': True}
    if not isinstance(response, dict) or 'error' in response.keys():
        # Invalid response or query errored out - return as an error
        logging.error("Elastic search query errored.")
        return {'error': True}
    if 'timed_out' in response.keys() and response['timed_out']:
        # Log as skipped
        logging.warning("Elastic search query timed out.")
        return {'timed_out': True}
    return response
