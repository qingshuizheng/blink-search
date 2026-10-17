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
from core.utils import eval_in_emacs, get_emacs_var, message_emacs, touch


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
        """Open the database and build the key/value table when it is new.

        A database that cannot be used leaves the backend switched off rather
        than broken: `sqlite3.connect("")' is happy to return a connection
        that fails on its first statement, so the connection is not proof
        that the database works.  A backend that is switched off finds no
        candidate and reports why, which is what keeps a bad path from
        taking the whole search down.
        """
        super().__init__()
        self.usable = False
        self.conn = None
        self.table = get_emacs_var("blink-search-db-table") or "kvstore"

        db_path = get_emacs_var("blink-search-db-path")
        if not isinstance(db_path, str) or db_path == "":
            message_emacs("Key Value: no usable database path, the backend is off")
        else:
            # The directory may not exist yet on a fresh machine: sqlite
            # creates the file but not the path to it, and answers "unable to
            # open database file" when the directory is missing.
            touch(db_path)
            connection = self.create_connection(db_path)
            if connection is not None:
                try:
                    connection.cursor().execute(
                        f"CREATE TABLE IF NOT EXISTS {self.table} "
                        "(key TEXT NOT NULL, value TEXT NOT NULL);")
                    self.conn = connection
                    self.usable = True
                except sqlite3.Error as err:
                    message_emacs("Key Value: {} ({})".format(err, db_path))

        self.set_regexp = re.compile(r"^set\s([^\s]+)\s([^\s]+)$")
        self.del_regexp = re.compile(r"^del\s([^\s]+)$")

    @staticmethod
    def create_connection(db_file):
        """Return a connection to the sqlite database DB-FILE, or None.

        The connection is shared with the threads that run the searches,
        hence `check_same_thread=False'.  A path that is not a string, or
        that cannot be opened, is reported and returns None.
        """
        if not isinstance(db_file, str) or db_file == "":
            return None

        try:
            return sqlite3.connect(db_file, check_same_thread=False)
        except sqlite3.Error as err:
            message_emacs("Key Value: {} ({})".format(err, db_file))
            return None

    def search_match(self, prefix):
        """Return the keys that hold PREFIX, shortest query first.

        A keyword that stores or deletes a pair is offered as a candidate of
        its own, so that a user can type the whole command in one go.
        """
        if not self.usable:
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
        if not self.usable:
            message_emacs("Key Value backend has no database")
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
            try:
                self.conn.close()
            except sqlite3.Error as err:
                message_emacs("Key Value: {} while closing".format(err))
            self.conn = None
        self.usable = False
