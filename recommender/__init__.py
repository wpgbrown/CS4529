from typing import List, Union, Iterable


class RecommendedReviewer:
    def __init__(self, email: str, names: Union[str, List[str]] = None, score: float = 0):
        if names is None:
            names = []
        self.email = email
        """Email address of the reviewer"""
        self.names = names
        """List of usernames associated with this email address"""
        self.score = score
        """The score associated with the recommendation. Larger the better."""

    def __lt__(self, other):
        if not isinstance(other, RecommendedReviewer):
            return NotImplemented
        return self.score < other.score

    def __le__(self, other):
        if not isinstance(other, RecommendedReviewer):
            return NotImplemented
        return self.score <= other.score

    def __eq__(self, other):
        if not isinstance(other, RecommendedReviewer):
            return NotImplemented
        return self.email == self.email

    def __hash__(self):
        return hash(self.email)

    def __str__(self):
        return "Recommending %s known by usernames " % self.email + ",".join(self.names[:-1]) + "and %s with score %f" % (self.names[-1], self.score)

class Recommendations(set):
    def ordered_by_score(self) -> List[RecommendedReviewer]:
        """
        Returns the recommendations ordered by their score.

        :return: The ordered recommendations
        """
        return sorted(self)

    def top_n(self, n: int) -> List[RecommendedReviewer]:
        """
        Gets the top N recommendations.

        :param n: The number of recommendations to return
        :return: The top N recommendations
        """
        return self.ordered_by_score()[:n]

    def add(self, recommendation: RecommendedReviewer) -> None:
        super().add(recommendation)

    def difference_update(self, *s: Iterable[RecommendedReviewer]) -> None:
        super().difference_update(s)

    def intersection_update(self, *s: Iterable[RecommendedReviewer]) -> None:
        super().intersection_update(s)

    def copy(self):
        """
        :rtype: Recommendations[RecommendedReviewer]
        """
        return Recommendations(super().copy())

    def symmetric_difference_update(self, s: Iterable[RecommendedReviewer]) -> None:
        super().symmetric_difference_update(s)

    def union(self, *s: Iterable[RecommendedReviewer]):
        """
        :rtype: Recommendations[RecommendedReviewer]
        """
        return Recommendations(super().union(s))

    def update(self, *s: Iterable[RecommendedReviewer]) -> None:
        super().update(s)

# DEBUG
if __name__ == "__main__":
    recommendations = Recommendations()
    recommendations.add(RecommendedReviewer("test@test.com"))
    recommendations.add(RecommendedReviewer("test@test2.com"))
    recommendations.add(RecommendedReviewer("test@test.com"))