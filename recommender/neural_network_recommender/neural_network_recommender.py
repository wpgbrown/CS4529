import itertools
import json
import logging
import pickle

import numpy
import requests
import seaborn as sns
from matplotlib import pyplot as plt
from sklearn.preprocessing import StandardScaler
import pandas
import time
import urllib.parse
from sklearn.metrics import accuracy_score
from sklearn.model_selection import train_test_split
from sklearn.neural_network import MLPClassifier
import common
from comment_votes_and_members_of_repos_to_data_frame import preprocess_into_pandas_data_frame
from data_collection import git_blame
from recommender import Recommendations
from common import get_test_data_for_repo

if __name__ == "__main__":
    logging.basicConfig(filename=common.path_relative_to_root("logs/neural_network_recommender_logs.log.txt"), level=logging.DEBUG)

repository = "mediawiki/extensions/CheckUser"
test_data = get_test_data_for_repo(repository)
time_period = test_data[0]
test_data = test_data[1]
base_data_frame_for_repo = preprocess_into_pandas_data_frame(repository)[time_period]

# print("Test data:", test_data)

"""fig, ax = plt.subplots(figsize=(20,5))
sns.heatmap(data_frame==0, vmin=0, vmax=1, cbar=False, ax=ax).set_title("Products x Features")
plt.show()"""

def add_change_specific_attributes_to_data_frame(change_info: dict, data_frame: pandas.DataFrame) -> pandas.DataFrame:
    data_frame = data_frame.copy(True)
    #print(change_info)
    # Get the files modified (added, changed or deleted) by the change
    # TODO: Merge with simple recommender code if possible to reduce duplication
    information_about_change_including_git_blame_stats_in_head = {}
    # TODO: Remove duplication by calling the blame once with all files that are wanted inspected.
    # TODO: Exclude files that are too large (causes program to be too slow) - If too large then the git blame stats are unlikely to help much
    for filename, info in change_info['files'].items():
        # Add deleted and changed files to files modified from the base
        info: dict
        if info['size'] > 500_000:
            continue
        if 'status' not in info.keys():
            # File just modified (not created, moved or deleted), so other authors can likely help
            arguments = {
                'files': filename,
                'repository': repository
            }
            if 'parent_shas' in change_info:
                arguments['parent_commit_sha'] = change_info['parent_shas'][0]
            arguments['branch'] = change_info['branch']
            information_about_change_including_git_blame_stats_in_head[filename] = info
            information_about_change_including_git_blame_stats_in_head[filename].update(
                {'blame_stats': git_blame.git_blame_stats_for_head_of_branch(**arguments)}
            )
        else:
            match info['status']:
                case 'D' | 'W':
                    # File was either deleted or substantially re-written.
                    # While this means none of or very little of the code
                    #  already present will be kept if this is merged, said
                    #  authors and committers are likely to provide some
                    #  useful thoughts on this.
                    arguments = {
                        'files': filename,
                        'repository': repository
                    }
                    if 'parent_shas' in change_info:
                        arguments['parent_commit_sha'] = change_info['parent_shas'][0]
                    arguments['branch'] = change_info['branch']
                    information_about_change_including_git_blame_stats_in_head[filename] = info
                    information_about_change_including_git_blame_stats_in_head[filename].update(
                        {'blame_stats': git_blame.git_blame_stats_for_head_of_branch(**arguments)}
                    )
                case 'R' | 'C':
                    # File renamed or copied. The authors/committers of the file that was renamed
                    #  or the file that was copied likely have understanding about whether a rename
                    #  or copy would make sense here.
                    # TODO: Test with a change that has a copied file.
                    arguments = {
                        'files': info['old_path'],
                        'repository': repository
                    }
                    if 'parent_shas' in change_info:
                        arguments['parent_commit_sha'] = change_info['parent_shas'][0]
                    arguments['branch'] = change_info['branch']
                    information_about_change_including_git_blame_stats_in_head[filename] = info
                    information_about_change_including_git_blame_stats_in_head[filename].update(
                        {'blame_stats': git_blame.git_blame_stats_for_head_of_branch(**arguments)}
                    )
    logging.debug("Git blame files from base: " + str(information_about_change_including_git_blame_stats_in_head))
    total_delta_over_all_files = sum(
        [abs(info['size_delta']) for info in information_about_change_including_git_blame_stats_in_head.values()])
    for name in itertools.chain.from_iterable([
        [y + x for y in common.TimePeriods.DATE_RANGES] for x in [" author git blame percentage", " reviewer git blame percentage"]
    ]):
        data_frame[name] = 0
    # print(data_frame.columns.array)
    if total_delta_over_all_files != 0:
        for file, info in information_about_change_including_git_blame_stats_in_head.items():
            logging.debug(info)
            time_period_to_key = {y: y.replace(' ', '_') + "_lines_count" for y in common.TimePeriods.DATE_RANGES}
            author_sums = {}
            for time_period, name in time_period_to_key.items():
                author_sums[time_period] = sum([x[name] for x in info['blame_stats']['authors'].values()])
            committer_sums = {}
            for time_period, name in time_period_to_key.items():
                committer_sums[time_period] = sum([x[name] for x in info['blame_stats']['committers'].values()])
            for author_email, author_info in info['blame_stats']['authors'].items():
                if author_info['name'][0] not in data_frame.index.values:
                    data_frame.loc[author_info['name'][0], :] = 0
                # print(author_info)
                for time_period, name in {y: y + " author git blame percentage" for y in common.TimePeriods.DATE_RANGES}.items():
                    if not author_sums[time_period]:
                        continue
                    data_frame.at[author_info['name'][0], name] += (author_info[time_period_to_key[time_period]] / author_sums[time_period]) * (info['size_delta'] / total_delta_over_all_files)
            for committer_email, committer_info in info['blame_stats']['committers'].items():
                reviewer = recommendations.get_reviewer_by_email_or_create_new(committer_email)
                for name in committer_info['name']:
                    reviewer.names.add(name)
                if committer_info['name'][0] not in data_frame.index.values:
                    data_frame.loc[committer_info['name'][0], :] = 0
                for time_period, name in {y: y + " reviewer git blame percentage" for y in common.TimePeriods.DATE_RANGES}.items():
                    if not committer_sums[time_period]:
                        continue
                    data_frame.at[committer_info['name'][0], name] += (committer_info[time_period_to_key[time_period]] / committer_sums[time_period]) * (info['size_delta'] / total_delta_over_all_files)
    return data_frame

recommendations = Recommendations()

# Fill recommendations list with users from data frame
for status, sub_test_data in test_data.items():
    approved_clf = MLPClassifier(max_iter=1000)
    voted_clf = MLPClassifier(max_iter=1000)
    try:
        print("Status:", status)
        for change_id in sub_test_data.keys():
            sub_test_data[change_id]["id"] = change_id
        sub_test_data = list(sub_test_data.values())
        if len(sub_test_data) <= 1:
            continue
        train, test = train_test_split(sub_test_data)
        train = list(train)
        test = list(test)
        X_train = []
        approved_train = []
        voted_train = []
        for i, change_info in enumerate(train):
            print("Collating training data", i, "out of", len(train))
            logging.info("Collating training data " + str(i) + " out of " + str(len(train)))
            try:
                change_specific_data_frame = add_change_specific_attributes_to_data_frame(change_info, base_data_frame_for_repo)
                # Store lowercase representation to actual case used for indexing purposes
                lower_case_names = {x.lower(): x for x in change_specific_data_frame.index.values}
                # Add whether they actually voted
                change_specific_data_frame["Actually voted"] = False
                change_specific_data_frame["Actually approved"] = False
                # Check if voted
                for vote in change_info['code_review_votes']:
                    name = None
                    # Try to find associated data_frame row
                    if 'name' in vote and vote['name'].lower() in lower_case_names:
                        name = lower_case_names[vote['name'].lower()]
                    elif 'display_name' in vote and vote['display_name'].lower() in lower_case_names:
                        name = lower_case_names[vote['display_name'].lower()]
                    elif 'username' in vote and vote['username'].lower() in lower_case_names:
                        name = lower_case_names[vote['username'].lower()]
                    if name is None:
                        # No matching name found. Add it to the array.
                        # TODO: Is this the right thing to do? Should a continue be used instead
                        change_specific_data_frame.loc[vote['name'], :] = 0
                    change_specific_data_frame.at[vote['name'], "Actually voted"] = True
                    if vote['value'] == 2:
                        # Was an approval vote
                        change_specific_data_frame.at[vote['name'], "Actually approved"] = True
                change_specific_data_frame = change_specific_data_frame.fillna(0)
                """for row in change_specific_data_frame.iterrows():
                    #if row[1]["Can merge changes?"]:
                    print(row)"""
                X_train.append(change_specific_data_frame.iloc[:,:-2])
                approved_train.append(change_specific_data_frame.loc[:,"Actually approved"].replace({0: False}))
                voted_train.append(change_specific_data_frame.loc[:,"Actually voted"].replace({0: False}))
            except KeyboardInterrupt:
                break
        X_test = []
        approved_test = []
        voted_test = []
        for i, change_info in enumerate(test):
            print("Collating test data", i, "out of", len(test))
            logging.info("Collating test data " + str(i) + " out of " + str(len(train)))
            # Test model
            change_specific_data_frame = add_change_specific_attributes_to_data_frame(change_info, base_data_frame_for_repo)
            # Store lowercase representation to actual case used for indexing purposes
            lower_case_names = {x.lower(): x for x in change_specific_data_frame.index.values}
            # Add whether they actually voted
            change_specific_data_frame["Actually voted"] = False
            change_specific_data_frame["Actually approved"] = False
            # Check if voted
            for vote in change_info['code_review_votes']:
                name = None
                # Try to find associated data_frame row
                if 'name' in vote and vote['name'].lower() in lower_case_names:
                    name = lower_case_names[vote['name'].lower()]
                elif 'display_name' in vote and vote['display_name'].lower() in lower_case_names:
                    name = lower_case_names[vote['display_name'].lower()]
                elif 'username' in vote and vote['username'].lower() in lower_case_names:
                    name = lower_case_names[vote['username'].lower()]
                if name is None:
                    # No matching name found. Add it to the array.
                    # TODO: Is this the right thing to do? Should a continue be used instead
                    change_specific_data_frame.loc[vote['name'], :] = 0
                change_specific_data_frame.at[vote['name'], "Actually voted"] = True
                if vote['value'] == 2:
                    # Was an approval vote
                    change_specific_data_frame.at[vote['name'], "Actually approved"] = True
            change_specific_data_frame = change_specific_data_frame.fillna(0)
            """for row in change_specific_data_frame.iterrows():
                print(row)"""
            X_test.append(change_specific_data_frame.iloc[:, :-2])
            approved_test.append(change_specific_data_frame.loc[:, "Actually approved"].replace({0: False}))
            voted_test.append(change_specific_data_frame.loc[:, "Actually voted"].replace({0: False}))
        # Now scale data
        print("Scaling")
        scaler = StandardScaler()
        for X in X_train:
            scaler.fit(X)
        for i, X in enumerate(X_train):
            X_train[i][X.columns] = scaler.transform(X[X.columns])
        for i, X in enumerate(X_test):
            X_test[i][X.columns] = scaler.transform(X[X.columns])

        # Now apply training data
        print("Training")
        for i, X in enumerate(X_train):
            approved = approved_train[i]
            voted = voted_train[i]
            approved_clf.fit(X, approved)
            voted_clf.fit(X, voted)

        # Now test using testing data
        print("Predicting")
        for i, X in enumerate(X_train):
            approved = approved_test[i]
            voted = voted_test[i]
            predicted_approved = approved_clf.predict(X)
            predicted_voted = voted_clf.predict(X)
            print("Approved:", accuracy_score(approved, predicted_approved))
            print("Voted:", accuracy_score(voted, predicted_voted))
    except BaseException:
        pass
    pickle.dump(approved_clf,
                open(common.path_relative_to_root("recommender/neural_network_recommender/models/" + status + "_approved_clf.pickle"), "bw"))
    pickle.dump(voted_clf,
                open(common.path_relative_to_root("recommender/neural_network_recommender/models/" + status + "_voted_clf.pickle"), "bw"))