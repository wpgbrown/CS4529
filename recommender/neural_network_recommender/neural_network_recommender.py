import json
import logging
import numpy
import requests
import seaborn as sns
from matplotlib import pyplot as plt
from sklearn import preprocessing
import pandas
import time
import urllib.parse
from sklearn.model_selection import train_test_split
from sklearn.neural_network import MLPClassifier

import common
from comment_votes_and_members_of_repos_to_data_frame import preprocess_into_pandas_data_frame
from data_collection import git_blame
from recommender import Recommendations
from common import get_test_data_for_repo

repository = "mediawiki/extensions/CheckUser"
test_data = get_test_data_for_repo(repository)
time_period = list(test_data.keys())[0]
test_data = test_data[time_period][repository]
data_frame = preprocess_into_pandas_data_frame(repository)[time_period]

print("Test data:", test_data)

fig, ax = plt.subplots(figsize=(20,5))
sns.heatmap(data_frame==0, vmin=0, vmax=1, cbar=False, ax=ax).set_title("Products x Features")
plt.show()

recommendations = Recommendations()

for status, sub_test_data in test_data.items():
    print("Status:", status)
    for change_id in sub_test_data.keys():
        sub_test_data[change_id]["id"] = change_id
    sub_test_data = list(sub_test_data.values())
    if len(sub_test_data) <= 1:
        continue
    train, test = train_test_split(sub_test_data)
    for change_info in train:
        print(change_info)
        exit()
        # Rate-limiting
        time.sleep(1)
        # Get the files modified (added, changed or deleted) by the change
        latest_revision_sha = list(change_info['revisions'].keys())[0]
        #branch = change_info[]
        information_about_change_including_git_blame_stats_in_head = {}
        for filename, info in change_info['revisions'][latest_revision_sha]['files'].items():
            # Add deleted and changed files to files modified from the base
            info: dict
            if 'status' not in info.keys():
                # File just modified (not created, moved or deleted), so other authors can likely help
                information_about_change_including_git_blame_stats_in_head[filename] = info
                information_about_change_including_git_blame_stats_in_head[filename].update(
                    {'blame_stats': git_blame.git_blame_stats_for_head_of_branch(filename, repository, branch)}
                )
            else:
                match info['status']:
                    case 'D' | 'W':
                        # File was either deleted or substantially re-written.
                        # While this means none of or very little of the code
                        #  already present will be kept if this is merged, said
                        #  authors and committers are likely to provide some
                        #  useful thoughts on this.
                        information_about_change_including_git_blame_stats_in_head[filename] = info
                        information_about_change_including_git_blame_stats_in_head[filename].update(
                            {'blame_stats': git_blame.git_blame_stats_for_head_of_branch(filename, repository, branch)}
                        )
                    case 'R' | 'C':
                        # File renamed or copied. The authors/committers of the file that was renamed
                        #  or the file that was copied likely have understanding about whether a rename
                        #  or copy would make sense here.
                        # TODO: Test with a change that has a copied file.
                        information_about_change_including_git_blame_stats_in_head[filename] = info
                        information_about_change_including_git_blame_stats_in_head[filename].update(
                            {'blame_stats': git_blame.git_blame_stats_for_head_of_branch(info['old_path'], repository,
                                                                                         branch)}
                        )
        logging.debug("Git blame files from base: " + str(information_about_change_including_git_blame_stats_in_head))
        total_delta_over_all_files = sum(
            [info['size_delta'] for info in information_about_change_including_git_blame_stats_in_head.values()])
        for file, info in information_about_change_including_git_blame_stats_in_head.items():
            logging.debug(info)
            for author_email, author_info in info['blame_stats']['authors'].items():
                reviewer = recommendations.get_reviewer_by_email_or_create_new(author_email)
                for name in author_info['name']:
                    reviewer.names.add(name)
                for key, weighting in weightings.lines_count['authors'].items():
                    reviewer.add_score(author_info[key.replace(' ', '_') + '_lines_count'],
                                       info['size_delta'] / total_delta_over_all_files, weighting)
            for committer_email, committer_info in info['blame_stats']['committers'].items():
                reviewer = recommendations.get_reviewer_by_email_or_create_new(committer_email)
                for name in committer_info['name']:
                    reviewer.names.add(name)
                for key, weighting in weightings.lines_count['committers'].items():
                    reviewer.add_score(committer_info[key.replace(' ', '_') + '_lines_count'],
                                       info['size_delta'] / total_delta_over_all_files, weighting)