import json
import warnings
from abc import ABCMeta, abstractmethod
from collections import ChainMap
from typing import Union, List


class AggregationBuilderInterface(metaclass=ABCMeta):
    @abstractmethod
    def get_dict(self):
        pass

    def get_json(self) -> str:
        return json.dumps(self.get_dict())

"""
The methods that are used to make the queries are based on queries
used to make the interface panel at biterg.

The builder is made by William Brown
"""
class ElasticSearchQueryBuilder:
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
        self.must_not({
            "match_phrase": {
                "author_bot": {
                    "query": True
                }
            }
        })
        return self

    def repository(self, repository_names):
        if not isinstance(repository_names, list):
            self.must({
                "match_phrase": {
                    "repository": {
                        "query": repository_names
                    }
                }
            })
            return self
        repository_conditions = []
        for repository_name in repository_names:
            repository_conditions.append({
                "match_phrase": {
                    "repository": {
                        "query": repository_name
                    }
                }
            })
        self.must({
            "bool": {
                "should": repository_conditions,
                "minimum_should_match": 1
            }
        })
        return self

    def must_match_phrase(self, field, values, minimum_to_match=1):
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
        self.must({
            "query_string": {
                "query": query,
                "analyze_wildcard": analyse_wildcard,
                "default_field": default_field
            }
        })
        return self

    def aggregation(self, aggregation: AggregationBuilderInterface):
        self._aggs.update(aggregation.get_dict())
        return self

    def get_dict(self):
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

    def get_json(self, indent=None):
        return json.dumps(self.get_dict(), indent=indent)

    def get_pretty_json(self):
        return self.get_json(2)

class FiltersItemBuilder(AggregationBuilderInterface):
    def __init__(self):
        self._items = {}

    def add_filter_item(self, name, value):
        self._items.update({name: value})
        return self

    def query_string(self, name, query, default_field: str ="*", analyse_wildcard: bool =False):
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
    def __init__(self, name=''):
        self.name = str(name)
        self.value = {}

    def add_type(self, type_name, value):
        self.value.update({type_name: value})
        return self

    def terms(self, field, limit, order, extra=None):
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
        self.add_type('sum', {
            'field': field
        })
        return self

    def sum_bucket(self, bucket_path):
        self.add_type('sum_bucket', {
            "buckets_path": bucket_path
        })
        return self
    def filters(self, filters: Union[List[FiltersItemBuilder], List[dict], FiltersItemBuilder, dict]):
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
    def __init__(self):
        self._aggregations = {}

    def aggregation(self, value: AggregationBuilderInterface):
        self._aggregations.update(value.get_dict())
        return self

    def aggregations(self, *values: AggregationBuilderInterface):
        for value in values:
            self.aggregation(value)
        return self

    def get_dict(self):
        return {
            'aggs': self._aggregations
        }

def try_integer_conversion(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default