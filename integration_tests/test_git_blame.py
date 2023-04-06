import unittest
from git import GitCommandError
import common
from data_collection import git_blame


class TestGitBlame(unittest.TestCase):

    def test_exception_when_missing_file(self):
        # Test that when throwing is True, an exception is thrown for a non-existing file
        with self.assertRaises(GitCommandError):
            git_blame.git_blame_stats_for_head_of_branch("src/No-such-file.phpx", "mediawiki/extensions/CheckUser",
                                                         throw_on_missing_file=True)

    def test_no_exception_when_missing_file(self):
        # Test that no exception is thrown if the file is missing when throwing is set to False
        self.assertDictEqual(
            git_blame.git_blame_stats_for_head_of_branch("src/No-such-file.phpx", "mediawiki/extensions/CheckUser",
                                                         throw_on_missing_file=False),
            {"authors": {}, "committers": {}},
            "File did not exist so no blame info should have been returned"
        )
        self.assertDictEqual(
            git_blame.git_blame_stats_for_head_of_branch("src/No-such-file.phpx", "mediawiki/extensions/CheckUser"),
            {"authors": {}, "committers": {}},
            "File did not exist so no blame info should have been returned"
        )

    def test_get_bare_repo(self):
        repo = git_blame.get_bare_repo("mediawiki/extensions/CheckUser")
        # Check that the repo is actually a bare repo
        self.assertTrue(repo.bare, "Created repo should be bare")

    def test_get_bare_repo_head_references_main_branch(self):
        repo = git_blame.get_bare_repo("mediawiki/extensions/CheckUser")
        # Main branch name could change soon (e.g. master -> main), so make test needs to be resilent to this.
        self.assertEquals(
            repo.create_head(common.get_main_branch_for_repository("mediawiki/extensions/CheckUser")),
            repo.head.reference,
            "Repo does not have the main branch as it's HEAD"
        )

    def test_get_bare_repo_in_right_folder(self):
        repo = git_blame.get_bare_repo("mediawiki/extensions/CheckUser")
        self.assertEquals(
            common.path_relative_to_root("data_collection/raw_data/git_bare_repos/mediawiki-extensions-CheckUser"),
            repo.working_dir,
            "Repo was not created in the correct location"
        )

    def test_get_bare_repo_with_non_existing_repo(self):
        with self.assertRaises(GitCommandError):
            git_blame.get_bare_repo("mediawiki/test/non-existing-repo")

if __name__ == '__main__':
    unittest.main()