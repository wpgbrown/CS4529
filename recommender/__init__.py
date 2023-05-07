import json
import os
import weakref
from abc import ABC, abstractmethod
from functools import lru_cache
from weakref import ReferenceType
from collections.abc import Iterable, Sized
import logging
from typing import List, Union, Optional, Iterator, Any, Tuple
import itertools
import urllib.parse
import requests

from data_collection import git_blame
from data_collection.preprocessing import reviewer_votes_to_percentages, comment_counts_to_percentages
import common
import time

class WeightingsBase(common.TimePeriods):
    def __init__(self, weightings_file):
        weightings = json.load(open(weightings_file, 'r'))
        weightings: dict
        self._weightings = weightings

    def __iter__(self):
        return iter(self._weightings)

@lru_cache(maxsize=1)
def load_members_of_mediawiki_repos() -> dict:
    members_list = common.path_relative_to_root('data_collection/raw_data/members_of_mediawiki_repos.json')
    return json.load(open(members_list, 'r'))

@lru_cache(maxsize=5)
def get_members_of_repo(repository: str) -> List[dict[str, Any]]:
    groups_with_rights_to_merge = load_members_of_mediawiki_repos()['groups_for_repository'][repository].keys()
    groups_with_rights_to_merge = list(filter(lambda x: x not in common.group_exclude_list, groups_with_rights_to_merge))
    return list(filter(_get_members_of_repo_helper, list(itertools.chain.from_iterable([members for group_id, members in load_members_of_mediawiki_repos()['members_in_group'].items() if group_id in groups_with_rights_to_merge]))))

def _get_members_of_repo_helper(user: dict) -> bool:
    if 'name' in user and user['name'] in common.username_exclude_list:
        return False
    if 'username' in user and user['username'] in common.username_exclude_list:
        return False
    if 'display_name' in user and user['display_name'] in common.username_exclude_list:
        return False
    if 'email' in user and user['email'] in common.email_exclude_list:
        return False
    return True

@lru_cache(maxsize=1)
def get_reviewer_data():
    percentage_list = common.path_relative_to_root('data_collection/raw_data/reviewer_vote_percentages_for_repos.json')
    if not os.path.exists(percentage_list):
        comment_counts_to_percentages.convert_data_to_percentages()
    return json.load(open(percentage_list, 'r'))

@lru_cache(maxsize=1)
def get_comment_data():
    percentage_list = common.path_relative_to_root('data_collection/raw_data/comment_count_percentages_by_author_for_repo.json')
    if not os.path.exists(percentage_list):
        reviewer_votes_to_percentages.convert_data_to_percentages()
    return json.load(open(percentage_list, 'r'))

class RecommendedReviewer:
    def __init__(self, emails: Optional[Union[str, 'Names', List[str]]] = None, names: Union[str, 'Names', List[str]] = None, score: float = 0, parent: Optional[ReferenceType] = None, has_rights_to_merge: Optional[bool] = None):
        """
        Creates a recommendation for a given reviewer that has a given score to rank this
        recommendation against other recommendations.

        Either name(s) or emails(s) must be provided

        :param emails: The emails address(es) of the user. Optional if a name provided.
        :param names: The name(s) of the user. Optional if an emails is provided.
        :param score: The score of the recommendation. Optional, can be changed later
        :param parent: A weak reference to the Recommendations list this is stored in.
        """
        if names is None:
            names = []
        if emails is None:
            emails = []
        if isinstance(names, str):
            names = [names]
        if isinstance(emails, str):
            emails = [emails]
        if not len(names) and not len(emails):
            raise ValueError("Email(s) or name(s) must be provided.")
        if not isinstance(names, Names):
            names = Names(names, weakref.ref(self))
        if not isinstance(emails, Emails):
            emails = Emails(emails, weakref.ref(self))
        self._names = names
        self._emails = emails
        self.has_rights_to_merge = has_rights_to_merge
        """Whether this user has the rights to merge the change."""
        self.score = score
        """The score associated with the recommendation. Larger the better."""
        self.parent_weak_ref = parent
        """A weak reference to the recommendations list used to update the index of names to emails. Using weak reference to help avoid cyclic garbage collection problems."""

    @property
    def names(self):
        """Usernames associated with this emails address"""
        return self._names

    @property
    def emails(self):
        """Email address(es) of the reviewer."""
        return self._emails

    def add_score(self, value: float, *weightings: float) -> None:
        """
        Adds to the score attribute with a defined weighting that modifies the value

        :param value: The raw value
        :param weightings: The weighting(s) to apply to it (which are multiplied to the value)
        """
        for weighting in weightings:
            value *= weighting
        self.score += value

    def __lt__(self, other):
        if not isinstance(other, RecommendedReviewer):
            return NotImplemented
        return self.score < other.score

    def __gt__(self, other):
        if not isinstance(other, RecommendedReviewer):
            return NotImplemented
        return self.score > other.score

    def __str__(self):
        return_string = "Recommending"
        if len(self.emails or ''):
            return_string += " user known by email"
            if len(self.emails) != 1:
                return_string += "s"
            if len(self.emails) == 1:
                return_string += " " + self.emails[0]
            elif len(self.emails) == 2:
                return_string += " %s and %s" % (self.emails[0], self.emails[1])
            else:
                return_string += " %s and %s" % (", ".join(self.emails[:-1]), self.emails[-1])
        else:
            return_string += " user"
        if len(self.names):
            if len(self.emails or ''):
                return_string += " and"
            return_string += " known by username"
            if len(self.names) != 1:
                return_string += "s"
            if len(self.names) == 1:
                return_string += " " + self.names[0]
            elif len(self.names) == 2:
                return_string += " %s and %s" % (self.names[0], self.names[1])
            else:
                return_string += " %s and %s" % (", ".join(self.names[:-1]), self.names[-1])
        return return_string + " with score %s" % str(self.score)

class NamesAndEmailsBase(Iterable, Sized, ABC):
    def __init__(self, names_or_emails: List[str], parent_weak_ref: ReferenceType):
        self._names_or_emails = names_or_emails
        self.parent_weak_ref = parent_weak_ref

    @abstractmethod
    def add(self, name_or_email: str):
        return NotImplemented

    def _add(self, name_or_email: str) -> Union[Tuple["Recommendations", "RecommendedReviewer"], None]:
        if name_or_email in self._names_or_emails:
            return
        self._names_or_emails.append(name_or_email)
        parent = self.parent_weak_ref()
        if parent is None or not parent.emails:
            return
        parent: RecommendedReviewer
        if parent.parent_weak_ref is None:
            return
        return parent.parent_weak_ref(), parent

    def __iter__(self) -> Iterator[str]:
        return iter(self._names_or_emails)

    def __contains__(self, item: str):
        return item in self._names_or_emails

    def __len__(self) -> int:
        return len(self._names_or_emails)

    def __str__(self):
        return str(self._names_or_emails)

    def __getitem__(self, index):
        return self._names_or_emails[index]

class Names(NamesAndEmailsBase):
    def __init__(self, names: List[str], parent_weak_ref: ReferenceType):
        super().__init__(names, parent_weak_ref)

    def add(self, name: str):
        _add_result = self._add(name)
        if _add_result is None:
            return
        grandparent, parent = _add_result
        if grandparent is None or parent is None:
            return
        logging.debug("Updating name index for %s using name %s." % (parent.emails, name))
        # _update_name_index is intended for use only by this class, so the underscore is added
        #  to indicate this. Users attempting to add a name for an emails using this method
        #  won't work, so this underscore added to hide the method from suggestions in IDEs.
        grandparent._update_name_index(name, parent) # noqa

class Emails(NamesAndEmailsBase):
    def __init__(self, emails: List[str], parent_weak_ref: ReferenceType):
        super().__init__(emails, parent_weak_ref)

    def add(self, email: str):
        _add_result = self._add(email)
        if _add_result is None:
            return
        grandparent, parent = _add_result
        if grandparent is None or parent is None:
            return
        logging.debug("Updating email index for %s using email %s." % (parent.names, email))
        # _update_email_index is intended for use only by this class, so the underscore is added
        #  to indicate this. Users attempting to add a name for an emails using this method
        #  won't work, so this underscore added to hide the method from suggestions in IDEs.
        grandparent._update_email_index(email, parent)  # noqa

class Recommendations(Sized):
    def __init__(self):
        self._recommendations = []
        """All the recommended reviewers stored by this recommendations list"""
        self._recommendations_by_email = {}
        """Emails to RecommendedReviewer objects. Used as a one-to-many index."""
        self._recommendations_by_name = {}
        """Names to RecommendedReviewer objects. Used as a one-to-many index."""

    @property
    def recommendations(self):
        return self._recommendations

    def __len__(self):
        return len(self.recommendations)

    def ordered_by_score(self, only_users_that_can_approve: bool = False) -> List[RecommendedReviewer]:
        """
        Returns the recommendations ordered by their score.

        :param only_users_that_can_approve: Only return users that can approve the change
        :return: The ordered recommendations
        """
        if only_users_that_can_approve:
            return sorted(filter(lambda x: x.has_rights_to_merge, self.recommendations), reverse=True)
        return sorted(self.recommendations, reverse=True)

    def top_n(self, n: int, only_users_that_can_approve: bool = False) -> List[RecommendedReviewer]:
        """
        Gets the top N recommendations.

        :param only_users_that_can_approve: Only return users that can approve the change
        :param n: The number of recommendations to return
        :return: The top N recommendations
        """
        return self.ordered_by_score(only_users_that_can_approve)[:n]

    def add(self, recommendation: RecommendedReviewer) -> 'Recommendations':
        """
        Adds a recommended reviewer to the list of recommendations.

        This recommendation object should not be used in more than
        one recommendation list. If this is desired make a copy of
        it using python's copy.copy()

        :param recommendation: The RecommendedReviewer object
        :return: "self" for chaining calls
        """
        if len(recommendation.emails):
            # Has specified emails, so add these to the index
            logging.debug("Adding recommendation with emails " + str(recommendation.emails))
            if any(email for email in recommendation.emails if email in common.email_exclude_list):
                logging.info("User excluded with emails " + str(recommendation.emails))
                return self
            for email in recommendation.emails:
                email = common.convert_email_to_index_format(email)
                if email in self._recommendations_by_email.keys():
                    # Reviewer already exists with this email. Merge the entries.
                    self.merge_reviewer_entries(self._recommendations_by_email[email], recommendation)
                    return self
                else:
                    # No such reviewer exists with this email. Add it to the index
                    self._recommendations_by_email[email] = recommendation
        if len(recommendation.names):
            # Has specified names, so add these to the index.
            logging.debug("Adding recommendation with names " + str(recommendation.names))
            if any(name for name in recommendation.emails if name in common.username_exclude_list):
                logging.info("User excluded with names " + str(recommendation.names))
                return self
            for name in recommendation.names:
                name = common.convert_name_to_index_format(name)
                if name in self._recommendations_by_name.keys():
                    # Reviewer already exists with this name. Merge the entries.
                    self.merge_reviewer_entries(self._recommendations_by_name[name], recommendation)
                    return self
                else:
                    # No such reviewer exists with this name. Add it to the index
                    self._recommendations_by_name[name] = recommendation
        recommendation.parent_weak_ref = weakref.ref(self)
        self._recommendations.append(recommendation)
        return self

    def _update_name_index(self, name: str, associated_reviewer: RecommendedReviewer) -> "Recommendations":
        name = common.convert_name_to_index_format(name)
        if name in self._recommendations_by_name.keys() \
                and self._recommendations_by_name[name] is not None \
                and self._recommendations_by_name[name] is not associated_reviewer:
            # Merge the already existing entry into the entry given as the argument if the names match
            self.merge_reviewer_entries(associated_reviewer, self._recommendations_by_name[name])
        self._recommendations_by_name[name] = associated_reviewer
        return self

    def _update_email_index(self, email: str, associated_reviewer: RecommendedReviewer) -> "Recommendations":
        email = common.convert_email_to_index_format(email)
        if email in self._recommendations_by_email.keys() \
                and self._recommendations_by_email[email] is not None \
                and self._recommendations_by_email[email] is not associated_reviewer:
            # Merge the already existing entry into the entry given as the argument if the emails match
            self.merge_reviewer_entries(associated_reviewer, self._recommendations_by_email[email])
        self._recommendations_by_email[email] = associated_reviewer
        return self

    def merge_reviewer_entries(self, base: RecommendedReviewer, other_entry: RecommendedReviewer, remove_other_entry: bool = True):
        """
        Merges the second entry into the first entry, attempts to remove
        the second entry from the recommendations list unless told otherwise.

        :param base: The "base" entry. Usually the one that is kept in the recommendations list after being merged.
        :param other_entry: The entry to merge into the base entry, If remove_other_entry is not set to False, this entry is removed from the recommendations list after being merged into the base.
        :param remove_other_entry: Removes the second entry from the list if True. Set to False if it doesn't exist.
        :return:
        """
        logging.debug("Merge! " + str(base.emails or 'No emails'))
        # Merge the second entries attributes into the first entry.
        # Uses the _add method to prevent calls to _update_email_index and _update_name_index
        #  which would cause an infinite loop.
        for name in other_entry.names:
            base.names._add(name) # noqa
        for email in other_entry.emails:
            base.emails._add(email) # noqa
        # Add the names and emails to the index
        base.score += other_entry.score
        base.score /= 2
        if remove_other_entry:
            # Remove the other entry and replace the indexes it used with the base entry
            if other_entry in self._recommendations:
                del self._recommendations[self._recommendations.index(other_entry)]
            for name in other_entry.names:
                name = common.convert_name_to_index_format(name)
                if name in self._recommendations_by_name.keys():
                    self._recommendations_by_name[name] = base
            for email in other_entry.emails:
                email = common.convert_email_to_index_format(email)
                if email in self._recommendations_by_email.keys():
                    self._recommendations_by_email[email] = base


    def get_reviewer_by_email(self, email: str) -> Union[RecommendedReviewer, None]:
        """

        :param email:
        :return:
        """
        email = common.convert_email_to_index_format(email)
        if email in self._recommendations_by_email.keys():
            return self._recommendations_by_email[email]
        return None

    def get_reviewer_by_name(self, name: str) -> Union[RecommendedReviewer, None]:
        """

        :param name:
        :return:
        """
        name = common.convert_name_to_index_format(name)
        if name in self._recommendations_by_name.keys():
            # First check if the index had an emails associated with this name
            return self._recommendations_by_name[name]
        return None

    def get_reviewer_by_email_or_create_new(self, email: str) -> RecommendedReviewer:
        """

        :param email:
        :return:
        """
        logging.debug("Getting by emails")
        reviewer = self.get_reviewer_by_email(email)
        if reviewer is None:
            reviewer = RecommendedReviewer(email)
            self.add(reviewer)
        return reviewer

    def get_reviewer_by_name_or_create_new(self, name: str) -> RecommendedReviewer:
        """

        :param name:
        :return:
        """
        logging.debug("Getting by name")
        reviewer = self.get_reviewer_by_name(name)
        if reviewer is None:
            reviewer = RecommendedReviewer(names=name)
            self.add(reviewer)
        return reviewer

    def __getitem__(self, item):
        reviewer_by_email = self.get_reviewer_by_email(item)
        if reviewer_by_email is not None:
            return reviewer_by_email
        reviewer_by_name = self.get_reviewer_by_name(item)
        if reviewer_by_name is not None:
            return reviewer_by_name
        raise KeyError("Item is neither a defined emails or name in this recommendations list.")

class RecommenderImplementationBase:
    def __init__(self, repository: str):
        self.repository = repository

    @staticmethod
    def _make_git_blame_stats(git_blame_stats: dict, change_info: dict, return_dictionary: dict,
                              total_delta_over_all_files: int, file_aliases: dict, git_blame_type: str) -> None:
        time_period_to_key = {y: y.replace(' ', '_') + "_lines_count" for y in common.TimePeriods.DATE_RANGES}
        for file, associated_info in git_blame_stats[git_blame_type].items():
            if file in file_aliases.keys():
                file = file_aliases[file]
            file_size_delta = change_info["files"][file]["size_delta"]
            logging.debug(associated_info)
            sums = {}
            for time_period in common.TimePeriods.DATE_RANGES:
                sums[time_period] = sum([x[time_period_to_key[time_period]] for x in associated_info.values()])
            for email, commit_info in associated_info.items():
                # Only strips whitespace and makes lowercase, so no need to keep original value
                email = common.convert_email_to_index_format(email)
                for name in commit_info['names']:
                    lowercase_name = common.convert_name_to_index_format(name)
                    if lowercase_name not in return_dictionary['_names_to_emails_index'].keys():
                        return_dictionary['_names_to_emails_index'][lowercase_name] = []
                    elif email not in return_dictionary['_names_to_emails_index'][lowercase_name]:
                        # Username uses two or more different emails. Use the already existing one
                        #  as the primary email and add the second to the emails_to_names index.
                        if email not in return_dictionary['_emails_to_names_index'].keys():
                            return_dictionary['_emails_to_names_index'][email] = []
                        return_dictionary['_emails_to_names_index'][email].append(lowercase_name)
                        email = return_dictionary['_names_to_emails_index'][lowercase_name][0]
                    if email not in return_dictionary['_names_to_emails_index'][lowercase_name]:
                        return_dictionary['_names_to_emails_index'][lowercase_name].append(email)
                    if email not in return_dictionary['_emails_to_names_index'].keys():
                        return_dictionary['_emails_to_names_index'][email] = []
                    if lowercase_name not in return_dictionary['_emails_to_names_index'][email]:
                        return_dictionary['_emails_to_names_index'][email].append(lowercase_name)
                    if email not in return_dictionary['names'].keys():
                        return_dictionary['names'][email] = []
                    if name not in return_dictionary['names'][email]:
                        return_dictionary['names'][email].append(name)
                for time_period, result_dictionary_key in time_period_to_key.items():
                    if not sums[time_period]:
                        continue
                    if email not in return_dictionary[git_blame_type][result_dictionary_key]:
                        return_dictionary[git_blame_type][result_dictionary_key][email] = 0
                    return_dictionary[git_blame_type][result_dictionary_key][email] += \
                        (commit_info[time_period_to_key[time_period]] / sums[time_period]) * \
                        (file_size_delta / total_delta_over_all_files)

    def get_change_git_blame_info(self, change_info: dict):
        return_dictionary = {
            "authors": {},
            "committers": {},
            "_emails_to_names_index": {},
            "_names_to_emails_index": {},
            "names": {}
        }
        total_delta_over_all_files = sum(
            [abs(info['size_delta']) for info in change_info['files'].values()])
        time_period_to_key = {y: y.replace(' ', '_') + "_lines_count" for y in common.TimePeriods.DATE_RANGES}
        for git_blame_type_dictionary in [return_dictionary["authors"], return_dictionary["committers"]]:
            git_blame_type_dictionary.update(dict((key, {}) for key in time_period_to_key.values()))
        if total_delta_over_all_files == 0:
            # Return early as no calculations needed because no files were modified (0 for all is fine)
            return return_dictionary
        git_blame_arguments = {
            'repository': self.repository,
            'files': [],
            'per_file': True
        }
        if 'parent_shas' in change_info and len(change_info['parent_shas']):
            git_blame_arguments['parent_commit_sha'] = change_info['parent_shas'][0]
        git_blame_arguments['branch'] = change_info['branch']
        file_aliases = {}
        for filename, info in change_info['files'].items():
            # Add deleted and changed files to files modified from the base
            info: dict
            if info['size'] > 500_000:
                continue
            if 'status' not in info.keys():
                # File just modified (not created, moved or deleted), so other authors can likely help
                git_blame_arguments['files'].append(filename)
            else:
                match info['status']:
                    case 'D' | 'W':
                        # File was either deleted or substantially re-written.
                        # While this means none of or very little of the code
                        #  already present will be kept if this is merged, said
                        #  authors and committers are likely to provide some
                        #  useful thoughts on this.
                        git_blame_arguments['files'].append(filename)
                    case 'R' | 'C':
                        # File renamed or copied. The authors/committers of the file that was renamed
                        #  or the file that was copied likely have understanding about whether a rename
                        #  or copy would make sense here.
                        git_blame_arguments['files'].append(info['old_path'])
                        file_aliases[info['old_path']] = filename
        git_blame_stats = git_blame.git_blame_stats_for_head_of_branch(**git_blame_arguments)
        logging.debug("Git blame files from base: " + str(git_blame_stats))
        self._make_git_blame_stats(git_blame_stats, change_info, return_dictionary, total_delta_over_all_files,
                                   file_aliases, "authors")
        self._make_git_blame_stats(git_blame_stats, change_info, return_dictionary, total_delta_over_all_files,
                                   file_aliases, "committers")
        # Remove indexes used for de-duplication before returning
        del return_dictionary["_emails_to_names_index"]
        del return_dictionary["_names_to_emails_index"]
        return return_dictionary

class RecommenderImplementation(RecommenderImplementationBase, ABC):
    def __init__(self, repository: str):
        super().__init__(repository)

    @abstractmethod
    def recommend_using_change_info(self, change_info: dict) -> Recommendations:
        """
        Recommend reviewers for a patch using pre-downloaded change information

        :param change_info: Change information for this patch
        :return:
        """
        return NotImplemented

    def recommend_using_change_id(self, change_id: str, branch: str = '') -> Recommendations:
        """
        Recommend reviewers for a patch using a Change-ID and (optionally) a branch

        :param change_id: The Change-ID for this patch (as detailed on gerrit)
        :param branch: The branch this change is on (required if change exists on multiple branches)
        :return: The recommended reviewers
        :raises HTTPError: If information provided does not match a change or multiple patches match
        """
        # Rate-limiting
        time.sleep(1)
        # Get information about the latest revision
        change_id_for_request = change_id
        if '~' not in change_id_for_request:
            if self.repository.strip():
                if branch.strip():
                    change_id_for_request = branch + '~' + change_id_for_request
                change_id_for_request = self.repository + '~' + change_id_for_request
        change_id_for_request = urllib.parse.quote(change_id_for_request, safe='')
        request_url = common.gerrit_api_url_prefix + 'changes/' + change_id_for_request + '?o=CURRENT_REVISION&o=CURRENT_FILES&o=COMMIT_FOOTERS&o=TRACKING_IDS'
        logging.debug("Request made for change info: " + request_url)
        response = requests.get(request_url, auth=common.secrets.gerrit_http_credentials())
        # Needed in case the user provides an unrecognised change ID, repository or branch.
        response.raise_for_status()
        change_info = json.loads(common.remove_gerrit_api_json_response_prefix(response.text))
        logging.debug("Returned change info: " + str(change_info))
        latest_revision_sha = list(change_info['revisions'].keys())[0]
        change_info['files'] = change_info['revisions'][latest_revision_sha]['files']
        return self.recommend_using_change_info(change_info)