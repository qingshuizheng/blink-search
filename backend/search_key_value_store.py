#! /usr/bin/env python
# -*- coding: utf-8 -*-

"""A small key/value store kept in a local sqlite database.

The candidates are the keys of the table.  Three prefixes change what a
selection does: "set KEY VALUE" stores a pair, "del KEY" removes one,
and a plain key copies its value into the kill ring.
"""


# Copyright (C) 2022 EdmondFrank
#
# Author:     EdmondFrank <edmomdfrank@yahoo.com>
# Maintainer: <edmomdfrank@yahoo.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.


import re
import sqlite3

from core.backend import SearchBackend, register_backend
from core.utils import eval_in_emacs, get_emacs_var, message_emacs


@register_backend
class SearchKeyValueStore(SearchBackend):
    """Store and recall key/value pairs in a local sqlite database.

    The candidates are the keys of the table.  Three prefixes change what a
    selection does: "set KEY VALUE" stores a pair, "del KEY" removes one,
    and a plain key copies its value into the kill ring, so that a stored
    value can be pasted anywhere in Emacs.
    """

    NAME = "Key Value"

    def __init__(self):
        """Open the database and build the key/value table when it is new."""
        super().__init__()
        blink_search_db_path = get_emacs_var("blink-search-db-path")
        blink_search_db_table = get_emacs_var("blink-search-db-table")
        self.table = blink_search_db_table
        self.conn = self.create_connection(blink_search_db_path)

        init = f"CREATE TABLE IF NOT EXISTS {self.table} (key TEXT NOT NULL, value TEXT NOT NULL);"
        if self.conn:
            self.conn.cursor().execute(init)
        self.set_regexp = re.compile(r"^set\s([^\s]+)\s([^\s]+)$")
        self.del_regexp = re.compile(r"^del\s([^\s]+)$")

    @staticmethod
    def create_connection(db_file):
        """Return a connection to the sqlite database DB-FILE, or None.

        The connection is shared with the threads that run the searches,
        hence `check_same_thread=False'.  A database that cannot be opened
        is reported and leaves the backend without a connection, which the
        other methods check before they use it.
        """
        conn = None
        try:
            conn = sqlite3.connect(db_file, check_same_thread=False)
        except Exception as err:  # pylint: disable=broad-except
            print(err)

        return conn

    def search_match(self, prefix):
        """Return the keys that hold PREFIX, shortest query first.

        A keyword that stores or deletes a pair is offered as a candidate of
        its own, so that a user can type the whole command in one go.
        """
        if not self.conn:
            return []

        query = f"SELECT key FROM {self.table} WHERE key LIKE '%{prefix}%' LIMIT 20;"
        candidates = list(map(lambda row: row[0], self.conn.cursor().execute(query).fetchall()))
        if self.set_regexp.match(prefix) or self.del_regexp.match(prefix):
            candidates.append(prefix)

        return candidates

    def do(self, candidate):
        """Store, delete or copy the pair CANDIDATE stands for.

        "set KEY VALUE" updates the pair when the key exists and inserts it
        otherwise; "del KEY" removes it; any other candidate copies its
        value into the kill ring.
        """
        if not self.conn:
            message_emacs("Invalid connection to sqlite3")
            return

        set_matches = self.set_regexp.match(candidate)
        del_matches = self.del_regexp.match(candidate)
        if set_matches:
            key = set_matches.group(1)
            value = set_matches.group(2)
            exists = f"SELECT 1 FROM {self.table} WHERE key = '{key}';"
            if self.conn.cursor().execute(exists).fetchone():
                # Update existed item
                update = f"UPDATE {self.table} SET value = '{value}' WHERE key = '{key}';"
                self.conn.cursor().execute(update)
                self.conn.commit()
                message_emacs(f"Updated key-value ({key}, {value}) successfully")
            else:
                # Insert new item
                insert = f"INSERT INTO {self.table} (key, value) VALUES (?, ?);"
                self.conn.cursor().execute(insert, (key, value))
                self.conn.commit()
                message_emacs(f"Inserted key-value ({key}, {value}) successfully")
        elif del_matches:
            key = del_matches.group(1)
            delete = f"DELETE FROM {self.table} WHERE key = '{key}';"
            self.conn.cursor().execute(delete)
            self.conn.commit()
            message_emacs(f"Deleted {key} successfully")
        else:
            query = f"SELECT value FROM {self.table} WHERE key = '{candidate}';"
            row = self.conn.cursor().execute(query).fetchone()
            if row:
                eval_in_emacs("kill-new", row[0])
            else:
                message_emacs(f"No key named {candidate}")

    def parent(self, candidate, from_history=False):
        """Copy the value of CANDIDATE, like `do'.

        FROM-HISTORY is accepted for the signature of the base class: a
        stored pair has no parent to open.
        """
        del from_history
        self.do(candidate)

    def clean(self):
        """Close the database when the search is over."""
        super().clean()
        if self.conn is not None:
            self.conn.close()
            self.conn = None
