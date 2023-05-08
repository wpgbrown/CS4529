import json
import sqlite3
from typing import Union
import ijson
import common
from common import path_relative_to_root

# DB allows indexing by repo name
# TODO: Unused. Keep for reference in paper about approaches followed?

def get_test_data_db() -> Union[sqlite3.Connection, None]:
    try:
        connection = sqlite3.connect(common.path_relative_to_root("data_collection/raw_data/test_data_set.db"))
        cursor = connection.cursor()
        # connection.set_trace_callback(print)
        if cursor.execute("""SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='test_data_set';""").fetchone()[0]:
            # Truncate DB to re-insert data (incase it has changed).
            cursor.execute("""DELETE FROM test_data_set;""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS test_data_set (id INTEGER PRIMARY KEY, repository TEXT NOT NULL UNIQUE, time_period VARCHAR(20) NOT NULL, merged_changes TEXT, open_changes TEXT, abandoned_changes TEXT);""")
        cursor.execute("""CREATE UNIQUE INDEX IF NOT EXISTS repo_name ON test_data_set (repository);""")
        cursor.close()
        connection.commit()
        return connection
    except BaseException as e:
        print("Error", repr(e))
        return None

with open(path_relative_to_root('data_collection/raw_data/test_data_set_copy.json'), 'rb') as f:
    connection = get_test_data_db()
    if connection is not None:
        cursor = connection.cursor()
        for repo, repo_data in ijson.kvitems(f, "item"):
            print(repo)
            time_period = list(repo_data.keys())[0]
            print(time_period)
            cursor.execute("INSERT INTO test_data_set (repository, time_period, merged_changes, open_changes, abandoned_changes) VALUES (?, ?, ?, ?, ?)", [repo, time_period, json.dumps(repo_data[time_period]["merged"]), json.dumps(repo_data[time_period]["open"]), json.dumps(repo_data[time_period]["abandoned"])])
        cursor.close()
        connection.commit()
        connection.close()