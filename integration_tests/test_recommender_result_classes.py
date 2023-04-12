import logging
import unittest
import weakref
from unittest.mock import patch, MagicMock

import common
import recommender

logging.basicConfig(
    filename=common.path_relative_to_root("logs/recommender_init.test.log.txt"),
    level=logging.DEBUG
)

class TestRecommendationsClass(unittest.TestCase):
    def test_create_recommendation_list(self):
        recommendation_list = recommender.Recommendations()
        self.assertDictEqual(
            {},
            recommendation_list._recommendations_by_name,
            "Recommendations by name list should start empty"
        )
        self.assertDictEqual(
            {},
            recommendation_list._recommendations_by_email,
            "Recommendations by name list should start empty"
        )
        self.assertDictEqual(
            {},
            recommendation_list._names_to_emails,
            "Names to email index should start empty"
        )

    def test_add_recommendation_to_results_by_email(self):
        recommendations = recommender.Recommendations()
        recommendations.add(recommender.RecommendedReviewer("test@test.com", "Test name", 30))
        self.assertDictEqual(
            {},
            recommendations._recommendations_by_name,
            "Recommendation should have been added to the by email list as an email was specified."
        )
        self.assertCountEqual(
            ["test@test.com"],
            recommendations._recommendations_by_email.keys(),
            "Recommendation was not added to the list under it's email."
        )
        self.assertDictEqual(
            {"Test name": "test@test.com"},
            recommendations._names_to_emails,
            "Index was not updated when recommendation was added."
        )
        self.assertEqual(
            recommendations,
            recommendations.get_reviewer_by_email("test@test.com").parent_weak_ref(),
            "Weak reference to the recommendations list from the recommended reviewer was not correct"
        )

    def test_add_recommendation_to_results_by_name(self):
        recommendations = recommender.Recommendations()
        recommendations.add(recommender.RecommendedReviewer(None, "Test name", 20))
        self.assertDictEqual(
            {},
            recommendations._recommendations_by_email,
            "Recommendation should not have been added to the by email list as no email was specified."
        )
        self.assertCountEqual(
            ["Test name"],
            recommendations._recommendations_by_name.keys(),
            "Recommendation was not added to the list under it's name."
        )
        self.assertEqual(
            recommendations,
            recommendations.get_reviewer_by_name("Test name").parent_weak_ref(),
            "Weak reference to the recommendations list from the recommended reviewer was not correct"
        )

    def test_get_recommendations(self):
        recommendations = recommender.Recommendations()
        email_recommendation = recommender.RecommendedReviewer(None, "Test name", 20)
        name_recommendation = recommender.RecommendedReviewer("test@test.com", "Testing", 10)
        recommendations.add(name_recommendation).add(email_recommendation)
        self.assertCountEqual(
            [name_recommendation, email_recommendation],
            recommendations.recommendations,
            "Returned recommended reviewer objects were not as expected"
        )

    def test_get_recommendations_ordered_by_score(self):
        recommendations = recommender.Recommendations()
        email_recommendation = recommender.RecommendedReviewer(None, "Test name", 20)
        name_recommendation = recommender.RecommendedReviewer("test@test.com", "Testing", 10)
        recommendations.add(name_recommendation).add(email_recommendation)
        self.assertEqual(
            [email_recommendation.score, name_recommendation.score],
            list(map(lambda x: x.score, recommendations.ordered_by_score())),
            "Returned recommended reviewer objects were not ordered correctly"
        )

    def test_get_top_n_recommendations(self):
        recommendations = recommender.Recommendations()
        first_recommendation = recommender.RecommendedReviewer(None, "Test name", 20)
        second_recommendation = recommender.RecommendedReviewer("test@test.com", "Testing", 10)
        third_recommendation = recommender.RecommendedReviewer("test@testing.com", "Testing2", 100)
        fourth_recommendation = recommender.RecommendedReviewer("admin@test.com", "Testing12", 0)
        recommendations.add(first_recommendation).add(second_recommendation).add(third_recommendation).add(fourth_recommendation)
        top_3_recommendations = recommendations.top_n(3)
        self.assertEqual(
            3,
            len(top_3_recommendations),
            "More than 3 recommendations were returned by top_n when 'n' was specified as 3."
        )
        self.assertEqual(
            [third_recommendation, first_recommendation, second_recommendation],
            top_3_recommendations,
            "Returned top 2 recommended reviewer objects were not ordered correctly"
        )

class TestRecommendedReviewerClass(unittest.TestCase):
    def test_create_recommended_reviewer_object(self):
        recommendation = recommender.RecommendedReviewer("test@test.com")
        self.assertEqual(
            recommendation.email,
            "test@test.com",
            "Stored email was not correct"
        )
        self.assertEqual(
            list(recommendation.names),
            [],
            "No names should be stored at first"
        )
        self.assertEqual(
            recommendation.score,
            0,
            "Score should be 0 until score is given"
        )

    def test_create_recommended_reviewer_object_with_name_and_score(self):
        recommendation = recommender.RecommendedReviewer(None, "Test", 30)
        self.assertEqual(
            recommendation.email,
            None,
            "No email was specified, so none should be stored."
        )
        self.assertCountEqual(
            list(recommendation.names),
            ["Test"],
            "Test should be stored as the only name"
        )
        self.assertEqual(
            recommendation.score,
            30,
            "Score should be 30 (as specified on creation)"
        )

    def test_create_recommended_reviewer_object_with_no_email_or_name(self):
        with self.assertRaises(ValueError, msg="RecommendedReviewer creation should raise exception if neither email or name was provided"):
            recommender.RecommendedReviewer()

    def test_set_email_after_creation(self):
        recommendation = recommender.RecommendedReviewer(names="Test")
        self.assertIsNone(
            recommendation.email,
            "Email should be None if not specified on creation"
        )
        with self.assertNoLogs(level=logging.WARN):
            recommendation.email = "test@test.com"
        self.assertEqual(
            "test@test.com",
            recommendation.email,
            "Email should be settable if it's current value is None."
        )

    def test_update_email(self):
        recommendation = recommender.RecommendedReviewer("test@test.com", "Test")
        with self.assertLogs(level=logging.WARN):
            recommendation.email = "test@test.com"

    def test_string_representation(self):
        recommendation = recommender.RecommendedReviewer("test@test.com", "Test")
        self.assertEqual(
            "Recommending test@test.com known by username Test with score 0",
            str(recommendation),
            "String representation of the recommendation was not as expected"
        )
        recommendation.names.add("Testing")
        recommendation.score += 11
        self.assertEqual(
            "Recommending test@test.com known by usernames Test and Testing with score 11",
            str(recommendation),
            "String representation of the recommendation was not as expected"
        )
        recommendation.names.add("123456")
        recommendation.score -= 1
        self.assertEqual(
            "Recommending test@test.com known by usernames Test, Testing and 123456 with score 10",
            str(recommendation),
            "String representation of the recommendation was not as expected"
        )

class TestNamesClass(unittest.TestCase):
    def test_properties(self):
        names = recommender.Names(names=["Test", "Testing"], parent_weak_ref=weakref.ref(recommender.RecommendedReviewer(email="test")))
        self.assertCountEqual(
            ["Test", "Testing"],
            list(names.__iter__()),
            "__iter__() function doesn't return correct names"
        )
        self.assertEqual(2, len(names), "__len__() doesn't return correct length")
        self.assertEqual("Test", names[0], "__getitem__() doesn't return correct name")

    @patch.object(recommender.Recommendations, "_update_index")
    def test_add(self, mock: MagicMock):
        recommendations = recommender.Recommendations()
        recommendation = recommender.RecommendedReviewer("test@test.com", "Test")
        recommendations.add(recommendation)
        recommendation.names.add("Testing")
        self.assertTrue(mock.called, "The index update method was not called after adding a name")