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

class WeightingsBase:
    def __init__(self, weightings_file):
        weightings = json.load(open(weightings_file, 'r'))
        weightings: dict
        self._weightings = weightings

    def __iter__(self):
        return iter(self._weightings)

@lru_cache(maxsize=1)
def load_members_of_mediawiki_repos() -> dict:
    """
    Load the data set of members of groups that have access to mediawiki repos.
    """
    members_list = common.path_relative_to_root('data_collection/raw_data/members_of_mediawiki_repos.json')
    return json.load(open(members_list, 'r'))

@lru_cache(maxsize=5)
def get_members_of_repo(repository: str) -> List[dict[str, Any]]:
    """
    Get the users who have rights to merge code on the specified repository.

    :param repository: The repository that users have to have rights to merge on to be returned.
    """
    # Get the groups that have access to this repository
    groups_with_rights_to_merge = load_members_of_mediawiki_repos()['groups_for_repository'][repository].keys()
    # Filter out groups which have been globally excluded (such as groups that only have bot accounts)
    groups_with_rights_to_merge = list(filter(lambda x: x not in common.group_exclude_list, groups_with_rights_to_merge))
    # Return the members of these groups as one list, excluding users that have been globally excluded (such as bot accounts).
    return list(filter(_get_members_of_repo_helper, list(itertools.chain.from_iterable(
        [members for group_id, members in load_members_of_mediawiki_repos()['members_in_group'].items()
         if group_id in groups_with_rights_to_merge]
    ))))

def _get_members_of_repo_helper(user: dict) -> bool:
    """
    Returns True if the user is not globally excluded. Otherwise returns false.
    """
    def __get_members_of_repo_helper(user_key: str):
        if user_key in user and common.convert_name_to_index_format(user[user_key]) in common.username_exclude_list:
            return False
        return True
    if not __get_members_of_repo_helper('name'):
        return False
    if not __get_members_of_repo_helper('username'):
        return False
    if not __get_members_of_repo_helper('display_name'):
        return False
    if 'email' in user and common.convert_email_to_index_format(user['email']) in common.email_exclude_list:
        return False
    return True

@lru_cache(maxsize=1)
def get_reviewer_data():
    """
    Load and return the code review percentages data
    """
    percentage_list = common.path_relative_to_root('data_collection/raw_data/reviewer_vote_percentages_for_repos.json')
    if not os.path.exists(percentage_list):
        comment_counts_to_percentages.convert_data_to_percentages()
    return json.load(open(percentage_list, 'r'))

@lru_cache(maxsize=1)
def get_comment_data():
    """
    Load and return the comment percentages data
    """
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

class _NamesAndEmailsBase(Iterable, Sized, ABC):
    def __init__(self, names_or_emails: List[str], parent_weak_ref: ReferenceType):
        self._names_or_emails = [x.strip() for x in names_or_emails]
        self.parent_weak_ref = parent_weak_ref

    @abstractmethod
    def add(self, name_or_email: str):
        return NotImplemented

    def _add(self, name_or_email: str) -> Union[Tuple["Recommendations", "RecommendedReviewer"], None]:
        name_or_email = name_or_email.strip()
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

class Names(_NamesAndEmailsBase):
    def __init__(self, names: List[str], parent_weak_ref: ReferenceType):
        super().__init__(names, parent_weak_ref)

    def add(self, name: str):
        """
        Add the specified name to the list of names for this recommended reviewer.

        :param name: The name to be associated with this reviewer.
        """
        # Add the name
        _add_result = self._add(name)
        # If this Names list is associated with a recommendations list then
        #  update the index of names to recommended reviewers so that
        #  Recommendations::get_reviewer_by_name can find this recommendation.
        #
        # The calls to the protected ::_update_email_index and ::_update_name_index
        #  method are done because the index needs updating. They are protected
        #  as these methods should not be called by the user who gets given the
        #  Recommendations list, however, this other class needs to call it to
        #  update the index for the names/emails.
        if _add_result is None:
            return
        grandparent, parent = _add_result
        if grandparent is None or parent is None:
            return
        if common.convert_name_to_index_format(name) in common.username_to_email_map.keys():
            # If a name is associated with an email in the global username to email map,
            #  then add this email to the index too for this reviewer.
            logging.debug("Email specified globally")
            grandparent._update_email_index(common.username_to_email_map[common.convert_name_to_index_format(name)], parent) # noqa
        logging.debug("Updating name index for %s using name %s." % (parent.emails, name))
        grandparent._update_name_index(name, parent) # noqa

class Emails(_NamesAndEmailsBase):
    def __init__(self, emails: List[str], parent_weak_ref: ReferenceType):
        super().__init__(emails, parent_weak_ref)

    def add(self, email: str):
        # Add the email to the list of emails.
        _add_result = self._add(email)
        # If this Emails list is associated with a recommendations list then
        #  update the index of emails to recommended reviewers so that
        #  Recommendations::get_reviewer_by_email can find this recommendation.
        #
        # The calls to the protected ::_update_email_index method are done because
        #  the index needs updating. It is protected as the methods should not be
        #  called by the user who gets given a Recommendations object when asking
        #  for recommendations, however, this class still needs to call it to update
        #  the index.
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
    """
    A class that is used to hold the recommendations returned by either implementation
    in an implementation non-specific way. It also provides several de-duplication
    techniques.
    """

    def __init__(self, exclude_names: Union[List[str], str] = '', exclude_emails: Union[List[str], str] = ''):
        """
        Creates a recommendations list that excludes the specified names and emails
        from showing in the results.

        :param exclude_names: The usernames to exclude from the results (such as the change owner's username)
        :param exclude_emails: The emails to exclude from the results (such as the change owner's email)
        """
        self._recommendations = []
        """All the recommended reviewers stored by this recommendations list"""
        self._recommendations_by_email = {}
        """Emails to RecommendedReviewer objects. Used as a one-to-many index."""
        self._recommendations_by_name = {}
        """Names to RecommendedReviewer objects. Used as a one-to-many index."""
        self._exclude_names = []
        """Usernames to be excluded from recommendations. For example, don't recommend the author of the patch."""
        self._exclude_emails = []
        """Email addresses to be excluded from recommendations. For example, don't recommend the author of the patch."""
        if exclude_names:
            if isinstance(exclude_names, str):
                exclude_names = [exclude_names]
            for name in exclude_names:
                self._exclude_names.append(common.convert_name_to_index_format(name))
        if exclude_emails:
            if isinstance(exclude_emails, str):
                exclude_emails = [exclude_emails]
            for email in exclude_emails:
                self._exclude_emails.append(common.convert_email_to_index_format(email))

    @property
    def recommendations(self):
        """
        The recommendations provided in this result object.
        """
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
        # Un-assign any previous parent ref to prevent issues below.
        recommendation.parent_weak_ref = None
        # Check to see if any of the usernames or emails specified
        #  have been globally excluded or excluded for this recommendations list.
        if len(recommendation.names):
            if any(name for name in recommendation.names if common.convert_name_to_index_format(name) in common.username_exclude_list):
                logging.info("User with names " + str(recommendation.names) + "globally excluded.")
                return self
            if any(name for name in recommendation.names if common.convert_name_to_index_format(name) in self._exclude_names):
                logging.info("User with names " + str(recommendation.names) + "excluded from this recommendations list.")
                return self
        if len(recommendation.emails):
            if any(email for email in recommendation.emails if common.convert_email_to_index_format(email) in common.email_exclude_list):
                logging.info("User excluded with emails " + str(recommendation.emails))
                return self
            if any(email for email in recommendation.emails if common.convert_email_to_index_format(email) in self._exclude_emails):
                logging.info("User with names " + str(recommendation.emails) + "excluded from this recommendations list.")
                return self
        # The user is not excluded from the results, so continue to add them as a recommended reviewer.
        if len(recommendation.names):
            # Has specified names, so add these to the index.
            logging.debug("Adding recommendation with names " + str(recommendation.names))
            for name in recommendation.names:
                name = common.convert_name_to_index_format(name)
                if name in common.username_to_email_map.keys():
                    recommendation.emails.add(common.username_to_email_map[name])
                if name in self._recommendations_by_name.keys():
                    # Reviewer already exists with this name. Merge the entries.
                    self.merge_reviewer_entries(self._recommendations_by_name[name], recommendation)
                    return self
                else:
                    # No such reviewer exists with this name. Add it to the index
                    self._recommendations_by_name[name] = recommendation
        if len(recommendation.emails):
            # Has specified emails, so add these to the index
            logging.debug("Adding recommendation with emails " + str(recommendation.emails))
            for email in recommendation.emails:
                email = common.convert_email_to_index_format(email)
                if email in self._recommendations_by_email.keys():
                    # Reviewer already exists with this email. Merge the entries.
                    self.merge_reviewer_entries(self._recommendations_by_email[email], recommendation)
                    return self
                else:
                    # No such reviewer exists with this email. Add it to the index
                    self._recommendations_by_email[email] = recommendation
        # Give the recommendation the parent weak ref of this recommendations list
        recommendation.parent_weak_ref = weakref.ref(self)
        # Append the recommendation to the internal recommendations list.
        self._recommendations.append(recommendation)
        return self

    def _update_name_index(self, name: str, associated_reviewer: RecommendedReviewer) -> "Recommendations":
        """
        Update the internal recommendations name index. Called by the Names
        class when a name is added to the list for a reviewer.

        :param name: The new username to be added to the index
        :param associated_reviewer: The RecommendedReviewer object associated with this name
        """
        # Convert the name to the index format
        name = common.convert_name_to_index_format(name)
        if name in self._recommendations_by_name.keys() \
                and self._recommendations_by_name[name] is not None \
                and self._recommendations_by_name[name] is not associated_reviewer:
            # If the name is already associated with another reviewer, merge these users together
            self.merge_reviewer_entries(associated_reviewer, self._recommendations_by_name[name])
        # Add this reviewer to the index under the name.
        self._recommendations_by_name[name] = associated_reviewer
        return self

    def _update_email_index(self, email: str, associated_reviewer: RecommendedReviewer) -> "Recommendations":
        """
        Update the internal recommendations email index. Called by the Emails
        class when a name is added to the list for a reviewer.

        :param email: The new email to be added to the index
        :param associated_reviewer: The RecommendedReviewer object associated with this email
        """
        # Convert the email to the index format.
        email = common.convert_email_to_index_format(email)
        if email in self._recommendations_by_email.keys() \
                and self._recommendations_by_email[email] is not None \
                and self._recommendations_by_email[email] is not associated_reviewer:
            # If the email is already associated with another reviewer, merge these users together
            self.merge_reviewer_entries(associated_reviewer, self._recommendations_by_email[email])
        # Add this reviewer under the email provided in the index.
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
        Get the reviewer associated with the email provided as the first argument, returning
        None if no email is associated with a reviewer.

        :param email: The email being used to search for the reviewer
        :return: None if no such user in this list has the email, otherwise the RecommendedReviewer object
        """
        email = common.convert_email_to_index_format(email)
        if email in self._recommendations_by_email.keys():
            return self._recommendations_by_email[email]
        return None

    def get_reviewer_by_name(self, name: str) -> Union[RecommendedReviewer, None]:
        """
        Get the reviewer associated with the name provided as the first argument, returning
        None if this name is not associated with a reviewer.

        :param name: The name being used to search for the reviewer
        :return: None if no such user in this list has this name, otherwise the RecommendedReviewer object
        """
        name = common.convert_name_to_index_format(name)
        if name in self._recommendations_by_name.keys():
            return self._recommendations_by_name[name]
        return None

    def get_reviewer_by_email_or_create_new(self, email: str) -> RecommendedReviewer:
        """
        Get the reviewer associated with the email provided as the first argument, returning
        a new RecommendedReviewer object if no recommendation has this email.

        :param email: The email address
        :return: A RecommendedReviewer object
        """
        reviewer = self.get_reviewer_by_email(email)
        if reviewer is None:
            reviewer = RecommendedReviewer(email)
            self.add(reviewer)
        return reviewer

    def get_reviewer_by_name_or_create_new(self, name: str) -> RecommendedReviewer:
        """
        Get the reviewer associated with the name provided as the first argument, returning
        a new RecommendedReviewer object if no recommendation has this name.

        :param name: The username
        :return: A RecommendedReviewer object
        """
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
    @staticmethod
    def _make_git_blame_stats(git_blame_stats: dict, change_info: dict, return_dictionary: dict,
                              total_delta_over_all_files: int, file_aliases: dict, git_blame_type: str) -> None:
        """
        Make the git blame stats for the change provided in the change_info.

        :param git_blame_stats: The git blame stats as returned by git_blame.git_blame_stats_for_head_of_branch
        :param change_info: The change info for the change being processed
        :param return_dictionary: The dictionary to place the git blame stats in
        :param total_delta_over_all_files: The total delta over all files being modified in this change
        :param file_aliases: If a file has been moved in this change, this contains the old names as the keys and
         the new names as values
        :param git_blame_type: What type of git blame data is being requested to be processed in this call.
        """
        time_period_to_key = {y.value: y.value.replace(' ', '_') + "_lines_count" for y in common.TimePeriods}
        for file, associated_info in git_blame_stats[git_blame_type].items():
            # Update the filename used for files that have been moved to use the new filename
            if file in file_aliases.keys():
                file = file_aliases[file]
            file_size_delta = change_info["files"][file]["size_delta"]
            # Sum the line count data together for each time period
            sums = {}
            for time_period in common.TimePeriods:
                time_period = time_period.value
                sums[time_period] = sum([x[time_period_to_key[time_period]] for x in associated_info.values()])
            for email, commit_info in associated_info.items():
                # Only strips whitespace and makes lowercase to make index form,
                #  so no need to keep original value
                email = common.convert_email_to_index_format(email)
                # Create a map of names to emails that was generated from the git blame stat data.
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
                # Produce the git blame stat percentage.
                for time_period, result_dictionary_key in time_period_to_key.items():
                    if not sums[time_period]:
                        continue
                    if email not in return_dictionary[git_blame_type][result_dictionary_key]:
                        return_dictionary[git_blame_type][result_dictionary_key][email] = 0
                    return_dictionary[git_blame_type][result_dictionary_key][email] += \
                        (commit_info[time_period_to_key[time_period]] / sums[time_period]) * \
                        (file_size_delta / total_delta_over_all_files)

    @classmethod
    def get_change_git_blame_info(cls, repository: str, change_info: dict):
        """
        Get the git blame info for the change.

        :param repository: The repository this change is on
        :param change_info: The change info associated with the change.
        """
        return_dictionary = {
            "authors": {},
            "committers": {},
            "_emails_to_names_index": {},
            "_names_to_emails_index": {},
            "names": {}
        }
        total_delta_over_all_files = sum(
            [abs(info['size_delta']) for info in change_info['files'].values()])
        time_period_to_key = {y.value: y.value.replace(' ', '_') + "_lines_count" for y in common.TimePeriods}
        # Fill out the result dictionary with empty dictionaries.
        for git_blame_type_dictionary in [return_dictionary["authors"], return_dictionary["committers"]]:
            git_blame_type_dictionary.update(dict((key, {}) for key in time_period_to_key.values()))
        if total_delta_over_all_files == 0:
            # Return early as no calculations needed because no files were modified (0 for all is fine)
            return return_dictionary
        # Build the arguments to the git blame function.
        git_blame_arguments = {
            'repository': repository,
            'files': [],
            'per_file': True
        }
        if 'parent_shas' in change_info and len(change_info['parent_shas']):
            # Use the parent sha if available as this will perform stats on the code that was
            #  used as the base for the change.
            git_blame_arguments['parent_commit_sha'] = change_info['parent_shas'][0]
        git_blame_arguments['branch'] = change_info['branch']
        file_aliases = {}
        for filename, info in change_info['files'].items():
            # Add deleted and changed files to files modified from the base
            info: dict
            if info['size'] > 500_000:
                continue
            if 'status' not in info.keys():
                # File just modified (not created, moved or deleted),
                #  so other authors can likely help. As such include this
                #  in the files to get git-blame stats for.
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
        # Get the git blame stats using the arguments that were built above.
        git_blame_stats = git_blame.git_blame_stats_for_head_of_branch(**git_blame_arguments)
        logging.debug("Git blame files from base: " + str(git_blame_stats))
        # Compile the git blame stats into a format that can be understood by the recommendation implementations.
        cls._make_git_blame_stats(git_blame_stats, change_info, return_dictionary, total_delta_over_all_files,
                                   file_aliases, "authors")
        cls._make_git_blame_stats(git_blame_stats, change_info, return_dictionary, total_delta_over_all_files,
                                   file_aliases, "committers")
        # Remove indexes used for de-duplication by _make_git_blame_stats before returning
        del return_dictionary["_emails_to_names_index"]
        del return_dictionary["_names_to_emails_index"]
        return return_dictionary

class RecommenderImplementation(RecommenderImplementationBase, ABC):
    def __init__(self, repository: str):
        """
        Create the recommendations class that can be used to perform recommendations on the provided
        repository

        :param repository: The repository this object will be able to perform evaluations on.
        """
        self.repository = repository

    @abstractmethod
    def recommend_using_change_info(self, change_info: dict) -> Recommendations:
        """
        Recommend reviewers for a patch using pre-downloaded change information

        :param change_info: Change information for this patch
        :return: The recommendations in a Recommendations object
        """
        return NotImplemented

    def recommend_using_change_id(self, change_id: str, branch: str = '') -> Recommendations:
        """
        Recommend reviewers for a patch using a Change-ID and (optionally) a branch

        :param change_id: The Change-ID for this patch (as detailed on gerrit)
        :param branch: The branch this change is on (required if change exists on multiple branches)
        :return: The recommended reviewers in a Recommendations object
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
        request_url = common.gerrit_api_url_prefix + 'changes/' + change_id_for_request + '?o=CURRENT_REVISION&o=CURRENT_FILES&o=COMMIT_FOOTERS&o=TRACKING_IDS&o=DETAILED_ACCOUNTS'
        logging.debug("Request made for change info: " + request_url)
        response = requests.get(request_url, auth=common.secrets.gerrit_http_credentials())
        # Needed in case the user provides an unrecognised change ID, repository or branch.
        response.raise_for_status()
        change_info = json.loads(common.remove_gerrit_api_json_response_prefix(response.text))
        logging.debug("Returned change info: " + str(change_info))
        latest_revision_sha = list(change_info['revisions'].keys())[0]
        change_info['files'] = change_info['revisions'][latest_revision_sha]['files']
        return self.recommend_using_change_info(change_info)