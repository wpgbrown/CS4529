import json
import weakref
from functools import lru_cache
from weakref import ReferenceType
from collections.abc import Iterable, Sized
import logging
from typing import List, Union, Optional, Iterator, Any
import itertools

import common


class WeightingsBase:
    ALL_TIME = 'all time'
    LAST_YEAR = 'last year'
    LAST_3_MONTHS = 'last three months'
    LAST_MONTH = 'last month'
    def __init__(self, weightings_file):
        weightings = json.load(open(weightings_file, 'r'))
        weightings: dict
        self._weightings = weightings


@lru_cache(maxsize=1)
def load_members_of_mediawiki_repos() -> dict:
    members_list = common.path_relative_to_root('data_collection/raw_data/members_of_mediawiki_repos.json')
    return json.load(open(members_list, 'r'))

def get_members_of_repo(repository: str) -> List[dict[str, Any]]:
    groups_with_rights_to_merge = load_members_of_mediawiki_repos()['groups_for_repository'][repository].keys()
    groups_with_rights_to_merge = list(filter(lambda x: x not in common.group_exclude_list, groups_with_rights_to_merge))
    return list(itertools.chain.from_iterable([members for group_id, members in load_members_of_mediawiki_repos()['members_in_group'].items() if group_id in groups_with_rights_to_merge]))

class RecommendedReviewer:
    def __init__(self, email: Optional[str] = None, names: Union[str, 'Names', List[str]] = None, score: float = 0, parent: Optional[ReferenceType] = None, has_rights_to_merge: Optional[bool] = None):
        """
        Creates a recommendation for a given reviewer that has a given score to rank this
        recommendation against other recommendations.

        Either name(s) or an email must be provided

        :param email: The email address of the user. Optional if a name provided
        :param names: The name(s) of the user. Optional if an email is provided.
        :param score: The score of the recommendation. Optional, can be changed later
        :param parent: A weak reference to the Recommendations list this is stored in.
        """
        self._email = email
        if self._email is not None:
            self._email = self._email.lower()
        if names is None:
            names = []
        if isinstance(names, str):
            names = [names]
        if not len(names) and not email:
            raise ValueError("An email or a name must be provided.")
        if not isinstance(names, Names):
            names = Names(names, weakref.ref(self))
        self._names = names
        self.has_rights_to_merge = has_rights_to_merge
        """Whether this user has the rights to merge the change."""
        self.score = score
        """The score associated with the recommendation. Larger the better."""
        self.parent_weak_ref = parent
        """A weak reference to the recommendations list used to update the index of names to emails. Using weak reference to help avoid cyclic garbage collection problems."""

    @property
    def names(self):
        """Usernames associated with this email address"""
        return self._names

    @property
    def email(self):
        """Email address of the reviewer. Cannot be changed once set."""
        return self._email

    @email.setter
    def email(self, email: str):
        logging.debug("Setting email " + str(email))
        if self._email:
            logging.warning("Attempt to overwrite already set email. This was ignored.")
            return
        self._email = email.lower()
        if self.parent_weak_ref is not None:
            parent = self.parent_weak_ref()
            parent: Recommendations
            if parent is not None:
                # Indicate to the parent recommendations list that an email was specified.
                parent._email_specified_for_reviewer(self)  # noqa

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
        if len(self.email or ''):
            return_string += " " + self.email
            if len(self.names):
                return_string += " known by username"
        if len(self.names):
            if len(self.names) == 1:
                return_string += " " + self.names[0]
            elif len(self.names) == 2:
                return_string += "s %s and %s" % (self.names[0], self.names[1])
            else:
                return_string += "s %s and %s" % (", ".join(self.names[:-1]), self.names[-1])
        return return_string + " with score %s" % str(self.score)

class Names(Iterable, Sized):
    def __init__(self, names: List[str], parent_weak_ref: ReferenceType):
        self._names = names
        self.parent_weak_ref = parent_weak_ref

    def add(self, name: str):
        name = name
        if name in self._names:
            return
        self._names.append(name)
        parent = self.parent_weak_ref()
        if parent is None or not parent.email:
            return
        parent: RecommendedReviewer
        if parent.parent_weak_ref is None:
            return
        grandparent = parent.parent_weak_ref()
        if grandparent is None:
            return
        grandparent: Recommendations
        logging.debug("Updating index for %s using name %s." % (parent.email, name))
        # _update_index is intended for use only by this class, so the underscore is added
        #  to indicate this. Users attempting to add a name for an email using this method
        #  won't work, so this underscore added to hide the method from suggestions in IDEs.
        grandparent._update_index(name, parent.email, True, parent) # noqa

    def __iter__(self) -> Iterator[str]:
        return iter(self._names)

    def __contains__(self, item: str):
        return item in self._names

    def __len__(self) -> int:
        return len(self._names)

    def __str__(self):
        return str(self._names)

    def __getitem__(self, index):
        return self._names[index]

class Recommendations:
    def __init__(self):
        self._recommendations_by_email = {}
        """Emails to RecommendedReviewer objects"""
        self._recommendations_by_name = {}
        """Names to RecommendedReviewer objects which do not have an associated email"""
        self._names_to_emails = {}
        """Usernames to emails. Used as a non-unique index (i.e. many-to-one) for _recommendations_by_email"""

    @property
    def recommendations(self):
        return dict(self._recommendations_by_email, **self._recommendations_by_name).values()

    def ordered_by_score(self, filter_for_users_that_can_merge: bool = False) -> List[RecommendedReviewer]:
        """
        Returns the recommendations ordered by their score.

        :param filter_for_users_that_can_merge: TODO: Better parameter name
        :return: The ordered recommendations
        """
        if filter_for_users_that_can_merge:
            return sorted(filter(lambda x: x.has_rights_to_merge, self.recommendations), reverse=True)
        return sorted(self.recommendations, reverse=True)

    def top_n(self, n: int, filter_for_users_that_can_merge: bool = False) -> List[RecommendedReviewer]:
        """
        Gets the top N recommendations.

        :param filter_for_users_that_can_merge: TODO: Better parameter name
        :param n: The number of recommendations to return
        :return: The top N recommendations
        """
        return self.ordered_by_score(filter_for_users_that_can_merge)[:n]

    def add(self, recommendation: RecommendedReviewer) -> 'Recommendations':
        """
        Adds a recommended reviewer to the list of recommendations.

        This recommendation object should not be used in more than
        one recommendation list. If this is desired make a copy of
        it using python's copy.copy()

        :param recommendation: The RecommendedReviewer object
        :return: "self" for chaining calls
        """
        if recommendation.email:
            # Has a specified email, so use this to reference the reviewer
            logging.debug("Adding recommendation with email " + recommendation.email)
            if recommendation.email in self._recommendations_by_email.keys():
                logging.info("Recommendation by email already existed. Overwriting.")
            self._recommendations_by_email[recommendation.email] = recommendation
            for name in recommendation.names:
                # Check if any pre-existing reviewer item uses the same name.
                # If so, then merge them into this recommendation.
                if name in self._recommendations_by_name.keys():
                    logging.debug("Entries existed with a name that is also used by the one being added.")
                    self._merge_reviewer_entries(recommendation, self._recommendations_by_name[name])
            for name in recommendation.names:
                self._update_index(name, recommendation.email)
        elif len(recommendation.names):
            # Has specified names but no specified email, so use names as the reference
            for name in recommendation.names:
                if name in self._recommendations_by_name.keys():
                    logging.info("Recommendation by name already existed. Overwriting.")
                self._recommendations_by_name[name] = recommendation
        else:
            raise ValueError("Recommended reviewer has no email or name. One of these must be provided.")
        recommendation.parent_weak_ref = weakref.ref(self)
        return self

    def _update_index(self, name: str, email: str, merge_entries_with_same_name: bool = False, recommended_reviewer: Optional[RecommendedReviewer] = None) -> 'Recommendations':
        """
        Updates the index of names to email addresses.

        Code that uses the results should not need to interact with this
        method. To add a name to be associated with a reviewer, use
        RecommendedReviewer.names.add().

        :param name: The name to associate with the email address
        :param email: The email address
        :return: "self" for chaining calls
        """
        if name in self._names_to_emails.keys():
            logging.info("Name already defined to an email, but updating the index.")
            """if merge_entries_with_same_name and recommended_reviewer is not None and self.get_reviewer_by_email(self._names_to_emails[name]) is not recommended_reviewer:
                if name == "umherirrender":
                    print("AHAHQAHA")
                    print(name)
                    print(self.get_reviewer_by_email(self._names_to_emails[name]).names)
                    print(recommended_reviewer.email)
                    print(self.get_reviewer_by_email(self._names_to_emails[name]).email)
                self._merge_reviewer_entries(self.get_reviewer_by_email(self._names_to_emails[name]), recommended_reviewer)"""
        self._names_to_emails[name] = email
        return self

    def _email_specified_for_reviewer(self, recommended_reviewer: RecommendedReviewer):
        """

        :param recommended_reviewer:
        :return:
        """
        if self.get_reviewer_by_email(recommended_reviewer.email):
            # Merge attributes from the entry that already has this email
            #  with the entry provided.
            self._merge_reviewer_entries(recommended_reviewer, self.get_reviewer_by_email(recommended_reviewer.email))
        self._recommendations_by_email[recommended_reviewer.email] = recommended_reviewer
        for name in recommended_reviewer.names:
            # Remove the object from the recommendations by name list
            del self._recommendations_by_name[name]
            # Add this name email pair to the index of names to emails
            self._update_index(name, recommended_reviewer.email)

    def _merge_reviewer_entries(self, base: RecommendedReviewer, other_entry: RecommendedReviewer, remove_other_entry: bool = True):
        """
        Merges the second entry into the first entry, attempts to remove
        the second entry from the recommendations list unless told otherwise.

        :param base: The "base" entry. Usually the one that is kept in the recommendations list after being merged.
        :param other_entry: The entry to merge into the base entry, If remove_other_entry is not set to False, this entry is removed from the recommendations list after being merged into the base.
        :param remove_other_entry: Removes the second entry from the list if True. Set to False if it doesn't exist.
        :return:
        """
        logging.debug("Merge! " + str(base.email or 'No email'))
        # Merge the second entries attributes into the first entry
        for name in other_entry.names:
            base.names.add(name)
        base.score += other_entry.score
        base.score /= 2
        if remove_other_entry:
            # Remove the second entry as it has been merged
            if other_entry.email in self._recommendations_by_email:
                # "is" comparison doesn't call __eq__ so the references need to point to the same
                #  object for this to be true.
                if other_entry is self._recommendations_by_email[other_entry.email]:
                    # Remove the second entry from the recommendations list
                    del self._recommendations_by_email[other_entry.email]
            for name in other_entry.names:
                if name in self._recommendations_by_name and other_entry is self._recommendations_by_name[name]:
                    del self._recommendations_by_name[name]

    def get_reviewer_by_email(self, email: str) -> Union[RecommendedReviewer, None]:
        """

        :param email:
        :return:
        """
        if email in self._recommendations_by_email.keys():
            return self._recommendations_by_email[email]
        return None

    def get_reviewer_by_name(self, name: str) -> Union[RecommendedReviewer, None]:
        """

        :param name:
        :return:
        """
        if name in self._names_to_emails.keys():
            # First check if the index had an email associated with this name
            return self._recommendations_by_email[self._names_to_emails[name]]
        if name in self._recommendations_by_name.keys():
            # Then check if the name is associated to a reviewer without an email
            return self._recommendations_by_name[name]
        return None

    def get_reviewer_by_email_or_create_new(self, email: str) -> RecommendedReviewer:
        """

        :param email:
        :return:
        """
        logging.debug("Getting by email")
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
        raise KeyError("Item is neither a defined email or name in this recommendations list.")