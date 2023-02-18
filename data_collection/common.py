from secrets_interface import load_secrets

extensions_list = [ line.strip() for line in open("extensions_list.txt", "r").readlines() ]

secrets = load_secrets()

gerrit_api_url_prefix = 'https://gerrit.wikimedia.org/r/a/'

elasticsearch_request_headers = {'kbn-xsrf': 'true', 'content-type': 'application/json'}
gerrit_search_url = 'https://wikimedia.biterg.io/data/gerrit/_search'
git_search_url = 'https://wikimedia.biterg.io/data/git/_search'
phabricator_search_url = 'https://wikimedia.biterg.io/data/phabricator/_search'