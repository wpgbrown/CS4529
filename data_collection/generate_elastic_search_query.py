import json
import warnings
from abc import ABCMeta, abstractmethod


class AggregationBuilderInterface(metaclass=ABCMeta):
    @property
    @abstractmethod
    def get_object(self):
        pass

    @property
    @abstractmethod
    def get_json(self) -> str:
        pass

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

    def match_phrase(self, field, values, minimum_to_match=1):
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

    def query_string(self):

    def aggregation(self, aggregation: AggregationBuilderInterface):
        self._aggs.update(aggregation.get_object())
        return self

    def get_object(self):
        """{
            "2": {
                "terms": {
                    "field": "author_name",
                    "size": 5000,
                    "order": {
                        "1": "desc"
                    }
                },
                "aggs": {
                    "1": {
                        "sum": {
                            "field": "is_gerrit_approval"
                        }
                    },
                    "3": {
                        "sum_bucket": {
                            "buckets_path": "3-bucket>_count"
                        }
                    },
                    "4": {
                        "sum_bucket": {
                            "buckets_path": "4-bucket>_count"
                        }
                    },
                    "5": {
                        "sum_bucket": {
                            "buckets_path": "5-bucket>_count"
                        }
                    },
                    "6": {
                        "sum_bucket": {
                            "buckets_path": "6-bucket>_count"
                        }
                    },
                    "3-bucket": {
                        "filters": {
                            "filters": {
                                "approval_value:\"-2\"": {
                                    "query_string": {
                                        "query": "approval_value:\"-2\"",
                                        "analyze_wildcard": True,
                                        "default_field": "*"
                                    }
                                }
                            }
                        }
                    },
                    "4-bucket": {
                        "filters": {
                            "filters": {
                                "approval_value:\"-1\"": {
                                    "query_string": {
                                        "query": "approval_value:\"-1\"",
                                        "analyze_wildcard": True,
                                        "default_field": "*"
                                    }
                                }
                            }
                        }
                    },
                    "5-bucket": {
                        "filters": {
                            "filters": {
                                "approval_value:\"1\"": {
                                    "query_string": {
                                        "query": "approval_value:\"1\"",
                                        "analyze_wildcard": True,
                                        "default_field": "*"
                                    }
                                }
                            }
                        }
                    },
                    "6-bucket": {
                        "filters": {
                            "filters": {
                                "approval_value:\"2\"": {
                                    "query_string": {
                                        "query": "approval_value:\"2\"",
                                        "analyze_wildcard": True,
                                        "default_field": "*"
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }"""
        return {
            "aggs": self._aggs,
            "size": 0,
            "_source": {
                "excludes": []
            },
            "stored_fields": [
                "*"
            ],
            "script_fields": {
                "painless_delay": {
                    "script": {
                        "source": "if (doc.containsKey('status') && doc['type'].value == 'changeset') {\n  if (doc['status'].value == 'MERGED' || doc['status'].value == 'ABANDONED') {\n     return Duration.between(LocalDateTime.ofInstant(Instant.ofEpochMilli(doc['grimoire_creation_date'].value.millis), ZoneId.of('Z')), LocalDateTime.ofInstant(Instant.ofEpochMilli(doc['last_updated'].value.millis), ZoneId.of('Z'))).toMinutes()/1440.0;\n  } else {\n     return Duration.between(LocalDateTime.ofInstant(Instant.ofEpochMilli(doc['grimoire_creation_date'].value.millis), ZoneId.of('Z')), LocalDateTime.ofInstant(Instant.ofEpochMilli(new Date().getTime()), ZoneId.of('Z'))).toMinutes()/1440.0;\n  }\n\n  \n} else {\n  return 0;\n}",
                        "lang": "painless"
                    }
                }
            },
            "docvalue_fields": [
                {
                    "field": "approval_granted_on",
                    "format": "date_time"
                },
                {
                    "field": "approval_max_date",
                    "format": "date_time"
                },
                {
                    "field": "approval_min_date",
                    "format": "date_time"
                },
                {
                    "field": "changeset_max_date",
                    "format": "date_time"
                },
                {
                    "field": "changeset_min_date",
                    "format": "date_time"
                },
                {
                    "field": "closed",
                    "format": "date_time"
                },
                {
                    "field": "comment_created_on",
                    "format": "date_time"
                },
                {
                    "field": "comment_max_date",
                    "format": "date_time"
                },
                {
                    "field": "comment_min_date",
                    "format": "date_time"
                },
                {
                    "field": "created_on",
                    "format": "date_time"
                },
                {
                    "field": "demography_max_date",
                    "format": "date_time"
                },
                {
                    "field": "demography_min_date",
                    "format": "date_time"
                },
                {
                    "field": "grimoire_creation_date",
                    "format": "date_time"
                },
                {
                    "field": "last_updated",
                    "format": "date_time"
                },
                {
                    "field": "metadata__enriched_on",
                    "format": "date_time"
                },
                {
                    "field": "metadata__timestamp",
                    "format": "date_time"
                },
                {
                    "field": "metadata__updated_on",
                    "format": "date_time"
                },
                {
                    "field": "opened",
                    "format": "date_time"
                },
                {
                    "field": "patchset_created_on",
                    "format": "date_time"
                },
                {
                    "field": "patchset_max_date",
                    "format": "date_time"
                },
                {
                    "field": "patchset_min_date",
                    "format": "date_time"
                }
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

    def get_json(self):
        return json.dumps(self.get_object())

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

    def get_object(self):
        return {
            self.name: self.value
        }

    def get_json(self):
        return json.dumps(self.get_object())

class ElasticSearchAggregationGroupBuilder(AggregationBuilderInterface):
    def __init__(self):
        self._aggregations = {}

    def aggregation(self, value: AggregationBuilderInterface):
        self._aggregations.update(value.get_object())
        return self

    def get_object(self):
        return {
            'aggs': self._aggregations
        }

    def get_json(self):
        return json.dumps(self.get_object())

def try_integer_conversion(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default