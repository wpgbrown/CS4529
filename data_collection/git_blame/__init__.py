import datetime
import logging
import re
from typing import List, Union, Optional, Any
import common
from git import Repo, RemoteProgress, Commit, Actor, GitCommandError
import urllib.parse
import os
from pathvalidate import sanitize_filename
from dateutil.relativedelta import relativedelta
import time

class GitProgressPrinter(RemoteProgress):
    def update(
        self,
        op_code: int,
        cur_count: Union[str, float],
        max_count: Union[str, float, None] = None,
        message: str = "",
    ) -> None:
        logging.debug(
            "Op code: %d, Current count: %s, Max count: %s, Progress done: %d, Message: %s" % (op_code,
            str(cur_count),
            str(max_count),
            cur_count / (max_count or 100.0),
            message or "")
        )

if __name__ == "__main__":
    logging.basicConfig(filename=common.path_relative_to_root("logs/git_blame.log.txt"), level=logging.DEBUG)

def get_repo(repository: str) -> Repo:
    """
    Gets the Repo object for the provided repository

    :param repository: The name of the repository
    :return: A object allowing interaction with the bare cloned repository
    """
    repository_path = common.path_relative_to_root(
        "data_collection/raw_data/git_repos/" + sanitize_filename(re.sub(r'/', '-', repository))
    )
    if not os.path.exists(repository_path):
        logging.info("Cloning repo as it doesn't exist")
        print("Cloning repository", repository + ". This may take a some time.")
        # Clone the repo if it doesn't already exist
        repo = Repo.clone_from(
            common.gerrit_url_prefix + urllib.parse.quote(repository, safe='') + '.git',
            repository_path,
            progress=GitProgressPrinter()
        )
        return repo
    else:
        repo = Repo(repository_path)
        return repo

def get_bare_repo(repository: str, update_heads: bool = False) -> Repo:
    """
    Gets the Repo object for a bare cloned repo.

    :param repository: The name of the repository
    :param update_heads: Whether the HEADs should be updated if the bare repo already exists
    :return: A object allowing interaction with the bare cloned repository
    """
    bare_cloned_repository_path = common.path_relative_to_root(
        "data_collection/raw_data/git_bare_repos/" + sanitize_filename(re.sub(r'/', '-', repository))
    )
    if not os.path.exists(bare_cloned_repository_path):
        logging.info("Cloning repo as it doesn't exist")
        print("Cloning repository", repository + ". This may take a some time.")
        # Clone the repo if it doesn't already exist
        repo = Repo.clone_from(
            common.gerrit_url_prefix + urllib.parse.quote(repository, safe='') + '.git',
            bare_cloned_repository_path,
            bare=True,
            progress=GitProgressPrinter()
        )
        # Create FETCH_HEAD file
        logging.debug("Fetching heads after clone")
        repo.remote().fetch("refs/heads/*:refs/heads/*", progress=GitProgressPrinter())
        return repo
    else:
        repo = Repo(bare_cloned_repository_path)
        # Check if we should fetch the latest HEADs
        #  based on the last time an update was called.
        if update_heads:
            fetch_head_file = bare_cloned_repository_path + "/FETCH_HEAD"
            fetch_expiry = time.mktime((datetime.datetime.now() - relativedelta(hours=2)).timetuple())
            if not os.path.exists(fetch_head_file) or os.stat(fetch_head_file).st_ctime < fetch_expiry:
                # Update the HEADs for the branches
                logging.debug("Updating heads by a fetch")
                # First point HEAD to correct head
                repo.head.reference = repo.create_head(common.get_main_branch_for_repository(repository))
                # Then fetch heads
                repo.remote().fetch("refs/heads/*:refs/heads/*", progress=GitProgressPrinter())
        return repo

def _generate_stats_for_commit(actor: Actor, commit_date, lines_count: int, result_dictionary: dict) -> None:
    author_entry: Actor
    # Skip bots
    if common.convert_email_to_index_format(actor.email) in common.email_exclude_list:
        return
    if common.convert_name_to_index_format(actor.name) in common.username_exclude_list:
        return
    if actor.email not in result_dictionary.keys():
        result_dictionary[actor.email] = {
            'names': [],
            'all_time_lines_count': 0,
            'last_year_lines_count': 0,
            'last_three_months_lines_count': 0,
            'last_month_lines_count': 0,
        }
    if actor.name not in result_dictionary[actor.email]['names']:
        result_dictionary[actor.email]['names'].append(actor.name)
    result_dictionary[actor.email]['all_time_lines_count'] += lines_count
    for relative_delta, key in [
        (relativedelta(month=1), 'month'),
        (relativedelta(months=3), 'three_months'),
        (relativedelta(year=1), 'year'),
    ]:
        if commit_date > time.mktime((datetime.datetime.now() - relative_delta).timetuple()):
            result_dictionary[actor.email]['last_' + key + '_lines_count'] += lines_count

def git_blame_stats_for_head_of_branch(files: Union[List[str], str], repository: str, branch: Optional[str] = None, parent_commit_sha: str = None, throw_on_missing_file: bool = False, per_file: bool = False):
    # Get the Repo object for the specified repository
    repo = get_bare_repo(repository)
    # Use the "main" branch if no branch or parent sha specified
    if not branch:
        branch = common.get_main_branch_for_repository(repository)
    if branch:
        if parent_commit_sha:
            logging.debug("Moving to specified branch before trying commit")
        else:
            logging.debug("Using branch.")
        # Update the HEAD to the specified branch if branch is specified
        try:
            repo.head.reference = next(filter(lambda x: x.path.replace('refs/heads/', '') == branch or x.path == branch, repo.heads))
        except StopIteration:
            # Use main branch instead.
            branch = common.get_main_branch_for_repository(repository)
            repo.head.reference = next(filter(lambda x: x.path.replace('refs/heads/', '') == branch or x.path == branch, repo.heads))
    try:
        if parent_commit_sha:
            logging.debug("Using parent sha")
            parent_commit_sha: str
            # Update the HEAD to the specified sha commit
            repo.head.reference = repo.commit(parent_commit_sha)
    except ValueError:
        logging.warning("Unable to find sha " + parent_commit_sha + ". Using branch instead.")
    if isinstance(files, str):
        files = [files]
    authors = {}
    committers = {}
    for file in files:
        if per_file:
            authors[file] = {}
            committers[file] = {}
        try:
            for blame_entry in repo.blame_incremental(repo.head, file, w=True, M=True, C=True):
                lines_count = blame_entry.linenos.stop - blame_entry.linenos.start
                commit_entries: Any
                commit_entries = blame_entry.commit
                # Through testing the actual type of blame_entry.commit should just be "Commit" instead of a dictionary.
                # However, incase there is a dictionary returned this is accounted for.
                if isinstance(commit_entries, dict):
                    commit_entries = list(commit_entries.values())
                if isinstance(commit_entries, Commit):
                    commit_entries = [commit_entries]
                commit_entries: List[Commit]
                for commit_entry in commit_entries:
                    # Assign the author of the commit the lines in the file
                    if per_file:
                        # If in "per file" mode add the stats to a separate list for this file.
                        _generate_stats_for_commit(
                            commit_entry.author, commit_entry.authored_date, lines_count, authors[file]
                        )
                        _generate_stats_for_commit(
                            commit_entry.committer, commit_entry.committed_date, lines_count, committers[file]
                        )
                    else:
                        _generate_stats_for_commit(
                            commit_entry.author, commit_entry.authored_date, lines_count, authors
                        )
                        _generate_stats_for_commit(
                            commit_entry.committer, commit_entry.committed_date, lines_count, committers
                        )
        except GitCommandError as e:
            # Ignore missing files from the HEAD.
            #
            # In cases of patches that depend on another not merged change,
            #  that change does not contain information we want to get here
            #  as the change hasn't been merged (thus the committer is not available).
            #
            # In this case the file may not exist as it was added in said
            #  unmerged change.
            if not throw_on_missing_file and re.search(r'fatal: no such path ' + file, e.stderr):
                logging.info("File " + file + " doesn't exist in the HEAD commit.")
                continue
            raise e
    return {
        'authors': authors,
        'committers': committers
    }

if __name__ == "__main__":
    print(git_blame_stats_for_head_of_branch("src/Hooks.php", "mediawiki/extensions/CheckUser"))