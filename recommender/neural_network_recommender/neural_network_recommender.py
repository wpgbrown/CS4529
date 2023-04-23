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

repository = "mediawiki/core"
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
    # TODO: Specifying branch can break things
    branch = change_info['branch']
    information_about_change_including_git_blame_stats_in_head = {}
    for filename, info in change_info['files'].items():
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
    data_frame["Author git blame percentage"] = 0
    data_frame["Reviewer git blame percentage"] = 0
    #print(data_frame)
    if total_delta_over_all_files != 0:
        for file, info in information_about_change_including_git_blame_stats_in_head.items():
            logging.debug(info)
            for author_email, author_info in info['blame_stats']['authors'].items():
                if author_info['name'][0] not in data_frame.index.values:
                    data_frame.loc[author_info['name'][0], :] = 0
                data_frame.at[author_info['name'][0], "Author git blame percentage"] += info[
                                                                                            'size_delta'] / total_delta_over_all_files
                reviewer = recommendations.get_reviewer_by_email_or_create_new(author_email)
                for name in author_info['name']:
                    reviewer.names.add(name)
            for committer_email, committer_info in info['blame_stats']['committers'].items():
                reviewer = recommendations.get_reviewer_by_email_or_create_new(committer_email)
                for name in committer_info['name']:
                    reviewer.names.add(name)
                if committer_info['name'][0] not in data_frame.index.values:
                    data_frame.loc[committer_info['name'][0], :] = 0
                data_frame.at[committer_info['name'][0], "Reviewer git blame percentage"] += info['size_delta'] / total_delta_over_all_files
    return data_frame

recommendations = Recommendations()

# Fill recommendations list with users from data frame
approved_clf = MLPClassifier(max_iter=500)
voted_clf = MLPClassifier(max_iter=500)
for status, sub_test_data in test_data.items():
    print("Status:", status)
    for change_id in sub_test_data.keys():
        sub_test_data[change_id]["id"] = change_id
    sub_test_data = list(sub_test_data.values())
    if len(sub_test_data) <= 1:
        continue
    train, test = train_test_split(sub_test_data)
    train = list(train)
    test = list(test)
    for change_info in train[:10]:
        print("Trying")
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
            for row in change_specific_data_frame.iterrows():
                print(row)
            X = change_specific_data_frame.iloc[:,:-2]
            approved = change_specific_data_frame.loc[:,"Actually approved"]
            voted = change_specific_data_frame.loc[:,"Actually voted"]
            approved.replace({0: False}, inplace=True)
            voted.replace({0: False}, inplace=True)
            print(X)
            print(approved)
            print(voted)
            approved_clf.fit(X, approved)
            voted_clf.fit(X, voted)
        except KeyboardInterrupt:
            break
    for change_info in test[:10]:
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
        for row in change_specific_data_frame.iterrows():
            print(row)
        X = change_specific_data_frame.iloc[:, :-2]
        approved = change_specific_data_frame.loc[:, "Actually approved"]
        voted = change_specific_data_frame.loc[:, "Actually voted"]
        approved.replace({0: False}, inplace=True)
        voted.replace({0: False}, inplace=True)
        print(X)
        print(approved)
        print(voted)
        predicted_approved = approved_clf.predict(X)
        predicted_voted = voted_clf.predict(X)
        print("Approved:", accuracy_score(approved, predicted_approved))
        print("Voted:", accuracy_score(voted, predicted_voted))