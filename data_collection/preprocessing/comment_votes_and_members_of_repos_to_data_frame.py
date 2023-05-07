import logging
import re
from pathvalidate import sanitize_filename
import common
from recommender import load_members_of_mediawiki_repos
from recommender.neural_network_recommender import MLPClassifierImplementationBase

# TODO: Unused. Should this be kept?

if __name__ == "__main__":
    logging.basicConfig(filename=common.path_relative_to_root("logs/preprocess_into_data_frame.log.txt"), level=logging.DEBUG)
    repos_and_associated_members = load_members_of_mediawiki_repos()
    for repo in repos_and_associated_members['groups_for_repository'].keys():
        logging.debug("Preprocesing repo " + repo)
        print("Processing", repo)
        for time_period, data_frame in MLPClassifierImplementationBase.preprocess_into_pandas_data_frame(repo).items():
            data_frame.to_json(open(common.path_relative_to_root(
                "data_collection/raw_data/pandas_data_frames/" + sanitize_filename(
                    re.sub(r'/', '-', repo)) + '-' + sanitize_filename(time_period) + '.json'
            ), 'w'))