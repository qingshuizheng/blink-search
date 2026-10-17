#!/usr/bin/env python3
"""Tests for the logic of the search backends.

Everything an external command would do is replaced here: ripgrep output is
handed to `parse_lines' as text, `fd' output is handed to the base class
through a patched `get_process_result', and the Emacs variables a backend
reads are patched in `core.utils', which is where the backends import them
from.  What is left is the part of a backend that can be wrong on its own:
the filtering, the argument building and the offset arithmetic.

Run with:
    uv run --frozen python -m unittest test.test_search_backends
"""

from __future__ import annotations

import json
import os
import queue
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.search_buffer_list import SearchBufferList  # noqa: E402
from backend.search_common_directory import SearchCommonDirectory  # noqa: E402
from backend.search_find_file import SearchFindFile  # noqa: E402
from backend.search_google_suggest import SearchGoogleSuggest  # noqa: E402
from backend.search_grep_file import SearchGrepFile  # noqa: E402
from backend.search_imenu import SearchIMenu  # noqa: E402
from backend.search_key_value_store import SearchKeyValueStore  # noqa: E402
from backend.search_recent_file import SearchRecentFile  # noqa: E402
from core.utils import insert_unique_string_to_file, parse_rg_line  # noqa: E402


def rg_match_line(path="file.el", line=12, column=3, text="a long line of code\n"):
    """Build one line of ripgrep JSON output, as `--json' prints it."""
    return json.dumps({
        "type": "match",
        "data": {
            "path": {"text": path},
            "line_number": line,
            "lines": {"text": text},
            "submatches": [{"start": column, "end": column + 4,
                            "match": {"text": text[column:column + 4]}}],
        },
    })


class BufferListTest(unittest.TestCase):
    """The buffer list backend only filters and orders names."""

    def setUp(self):
        """Build the backend and give it a mixed list of buffers."""
        self.backend = SearchBufferList()
        self.backend.update(["*scratch*", "elisp.el", " *hidden*", "zzz.el"])

    def test_visible_buffers_come_before_hidden_ones(self):
        """A buffer whose name starts with a space is a hidden one.

        The visible buffers keep their alphabetical order among themselves:
        an asterisk is not a space, so `*scratch*' is a visible buffer.
        """
        self.assertEqual(self.backend.items[0], "*scratch*")
        self.assertEqual(self.backend.items[-1], " *hidden*")

    def test_a_prefix_that_starts_with_a_star_is_still_a_keyword(self):
        """A star is a wildcard of the menu, not part of the keyword."""
        self.assertEqual(sorted(self.backend.search_match("*scr")), ["*scratch*"])

    def test_a_trailing_star_is_a_wildcard_of_its_own(self):
        """A prefix that ends with a star keeps names that end with a star.

        The star is taken off the keyword before matching, so `scratch*'
        finds `*scratch*': the trailing star asks for buffers whose name
        ends with a star, and only after that is the keyword matched.
        """
        self.assertEqual(self.backend.search_match("scratch*"), ["*scratch*"])


class CommonDirectoryTest(unittest.TestCase):
    """The common directory backend matches alias and name together."""

    def setUp(self):
        """Build a backend whose only alias points at a temporary directory."""
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        Path(self.directory.name, "notes").mkdir()

        patcher = mock.patch("backend.search_common_directory.get_emacs_var",
                             return_value=[["HOME", self.directory.name]])
        patcher.start()
        self.addCleanup(patcher.stop)

        self.backend = SearchCommonDirectory()

    def test_the_alias_is_part_of_the_candidate(self):
        """A candidate says which alias it came from."""
        self.assertEqual(self.backend.search_match("home"), ["HOME notes"])

    def test_the_alias_is_matched_in_lower_case(self):
        """The alias and the entry name are both matched in lower case."""
        self.assertEqual(self.backend.search_match("home notes"), ["HOME notes"])
        self.assertEqual(self.backend.search_match("HoMe NoTeS"), ["HOME notes"])

    def test_a_candidate_is_turned_back_into_a_path(self):
        """The path of a candidate is the alias path plus its name."""
        self.assertEqual(self.backend.get_candiate_dir("HOME notes"),
                         os.path.join(self.directory.name, "notes"))

    def test_an_unknown_alias_has_no_path(self):
        """A candidate of an alias that is gone has no path."""
        self.assertIsNone(self.backend.get_candiate_dir("GONE notes"))


class FindFileTest(unittest.TestCase):
    """The find file backend builds the fd command line itself."""

    def setUp(self):
        """Build a backend whose project root is a temporary directory."""
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        Path(self.directory.name, "a.el").write_text("", encoding="utf-8")

        self.backend = SearchFindFile()
        self.backend.search_dir = self.directory.name
        self.backend.search_path = self.directory.name

    def test_an_empty_prefix_lists_the_directory(self):
        """An empty prefix lists what is in the directory itself."""
        self.backend.search_dir = self.directory.name
        self.assertEqual(self.backend.search_match(""), ["a.el"])

    def test_a_keyword_is_joined_with_a_dot_star(self):
        """The words of a keyword are joined so that they match in order."""
        captured = {}

        def fake_get_process_result(command_list, cwd=None):
            """Record the command line and answer with one match."""
            del cwd
            captured["command_list"] = command_list
            return [os.path.join(self.directory.name, "a.el")]

        self.backend.get_process_result = fake_get_process_result
        with mock.patch("shutil.which", return_value="/usr/bin/fd"):
            self.assertEqual(self.backend.search_match("a e"), ["a.el"])

        self.assertIn("a.*e", captured["command_list"])
        self.assertIn("--search-path", captured["command_list"])


class GoogleSuggestTest(unittest.TestCase):
    """The google suggestion backend only has to recognise a url."""

    def setUp(self):
        """Build the backend, whose network calls the tests never make."""
        self.backend = SearchGoogleSuggest()

    def test_a_url_is_recognised(self):
        """A url and a local html file are both openable."""
        for candidate in ("http://example.com", "https://example.com/a/b",
                          "ftp://example.com", "file.html"):
            self.assertTrue(self.backend.is_valid_url(candidate), candidate)

    def test_a_phrase_is_not_a_url(self):
        """A keyword with a space in it is a search, not an address."""
        for candidate in ("hello world", "", "not a url at all"):
            self.assertFalse(self.backend.is_valid_url(candidate), candidate)

    def test_a_url_is_opened_as_it_stands(self):
        """A candidate that is a url is opened without a search around it."""
        with mock.patch("backend.search_google_suggest.eval_in_emacs") as eval_in_emacs:
            self.backend.do("https://example.com")
        eval_in_emacs.assert_called_once_with("blink-search-open-browser", "https://example.com")

    def test_a_phrase_becomes_a_google_search(self):
        """A candidate that is a phrase becomes a google search."""
        with mock.patch("backend.search_google_suggest.eval_in_emacs") as eval_in_emacs:
            self.backend.do("hello world")
        eval_in_emacs.assert_called_once_with(
            "blink-search-open-browser",
            "http://www.google.com/search?q=hello%20world")


class GrepFileTest(unittest.TestCase):
    """The grep backend turns ripgrep JSON into menu candidates."""

    def setUp(self):
        """Build a backend rooted at a temporary project."""
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)

        self.messages = queue.Queue()
        self.backend = SearchGrepFile()
        self.backend.message_queue = self.messages
        self.backend.search_path = self.directory.name

    def test_parse_lines_prefixes_the_relative_path(self):
        """A candidate starts with the path of the match relative to the root."""
        inside = os.path.join(self.directory.name, "file.el")
        self.backend.parse_lines([rg_match_line(path=inside)], "code", 0)

        message = self.messages.get(timeout=5)
        self.assertEqual(message["items"][0]["text"], "file.el:12:3: a long line of code")
        # "file.el:12:3: " is 15 bytes, so the match at column 3 of the line
        # is at byte 18 of the candidate.
        self.assertEqual(message["items"][0]["matches"], [[17, 21]])

    def test_parse_lines_drops_a_line_that_is_not_a_match(self):
        """A line ripgrep printed about the file itself is not a candidate."""
        self.backend.parse_lines([json.dumps({"type": "begin", "data": {}})], "code", 0)

        message = self.messages.get(timeout=5)
        self.assertEqual(message["items"], [])

    def test_a_long_line_is_cut_to_its_first_match(self):
        """A line longer than the menu can show keeps its first match only."""
        inside = os.path.join(self.directory.name, "file.el")
        self.backend.parse_lines([rg_match_line(path=inside, text="x" * 1200)], "code", 0)

        message = self.messages.get(timeout=5)
        self.assertEqual(len(message["items"][0]["text"]), 1000)
        self.assertEqual(len(message["items"][0]["matches"]), 1)

    def test_a_stale_ticker_does_not_reach_the_queue(self):
        """An answer of an older search is dropped."""
        self.backend.search_ticker = 2
        self.backend.parse_lines([rg_match_line()], "code", 1)
        self.assertTrue(self.messages.empty())


class IMenuTest(unittest.TestCase):
    """The imenu backend keeps the position of every candidate."""

    def test_update_builds_the_name_to_position_map(self):
        """The names are the candidates and the positions are kept aside."""
        backend = SearchIMenu()
        backend.update([["defun-one", 12], ["defun-two", 30]])

        self.assertEqual(backend.items, [["defun-one", 12], ["defun-two", 30]])
        self.assertEqual(backend.item_dict, {"defun-one": 12, "defun-two": 30})

    def test_do_jumps_to_the_position_of_the_candidate(self):
        """Selecting a candidate hands its position back to Emacs."""
        backend = SearchIMenu()
        backend.update([["defun-one", 12]])

        with mock.patch("backend.search_imenu.eval_in_emacs") as eval_in_emacs:
            backend.do("defun-one")
        eval_in_emacs.assert_called_once_with("blink-search-imenu-do", 12)


class RecentFileTest(unittest.TestCase):
    """The recent file backend opens what the candidate names."""

    def test_do_visits_the_file(self):
        """A recent file candidate is an absolute path."""
        backend = SearchRecentFile()
        with mock.patch("backend.search_recent_file.eval_in_emacs") as eval_in_emacs:
            backend.do("/tmp/notes.org")
        eval_in_emacs.assert_called_once_with("find-file", "/tmp/notes.org")

    def test_parent_opens_the_directory(self):
        """The parent of a file is the directory that holds it."""
        backend = SearchRecentFile()
        with mock.patch("backend.search_recent_file.eval_in_emacs") as eval_in_emacs:
            backend.parent("/tmp/dir/notes.org")
        eval_in_emacs.assert_called_once_with("blink-search-open-file", "/tmp/dir")


class KeyValueStoreTest(unittest.TestCase):
    """The key value backend stores, deletes and recalls pairs."""

    def setUp(self):
        """Build a backend on a database of its own.

        The directory of the database is a fresh temporary one, so the
        backend has to create it -- which is what a home directory that has
        never seen this package looks like.
        """
        self.database = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.database.close()
        self.addCleanup(os.unlink, self.database.name)

        def fake_get_emacs_var(name):
            """Answer the two variables the backend reads."""
            return self.database.name if name == "blink-search-db-path" else "kvstore"

        patcher = mock.patch("backend.search_key_value_store.get_emacs_var",
                             side_effect=fake_get_emacs_var)
        patcher.start()
        self.addCleanup(patcher.stop)

        self.backend = SearchKeyValueStore()

    def test_a_pair_is_stored_and_found_again(self):
        """A "set" candidate stores the pair and the key becomes a candidate."""
        with mock.patch("backend.search_key_value_store.eval_in_emacs"), \
                    mock.patch("backend.search_key_value_store.message_emacs"):
            self.backend.do("set answer 42")

        self.assertIn("answer", self.backend.search_match("answer"))

        with mock.patch("backend.search_key_value_store.eval_in_emacs") as eval_in_emacs:
            self.backend.do("answer")
        eval_in_emacs.assert_called_once_with("kill-new", "42")

    def test_a_pair_is_updated_in_place(self):
        """Storing the same key twice updates the value."""
        with mock.patch("backend.search_key_value_store.eval_in_emacs"), \
                    mock.patch("backend.search_key_value_store.message_emacs"):
            self.backend.do("set answer 42")
            self.backend.do("set answer 43")

        with mock.patch("backend.search_key_value_store.eval_in_emacs") as eval_in_emacs:
            self.backend.do("answer")
        eval_in_emacs.assert_called_once_with("kill-new", "43")

    def test_a_pair_is_deleted(self):
        """A "del" candidate removes the key from the candidates."""
        with mock.patch("backend.search_key_value_store.eval_in_emacs"), \
                    mock.patch("backend.search_key_value_store.message_emacs"):
            self.backend.do("set answer 42")
            self.backend.do("del answer")

        self.assertNotIn("answer", self.backend.search_match("answer"))

    def test_a_database_that_cannot_be_opened_switches_the_backend_off(self):
        """A bad path is reported, not raised.

        `sqlite3.connect("")' returns a connection that fails on its first
        statement, so a backend that trusted the connection object raised out
        of the search instead of answering with no candidate.
        """
        with mock.patch("backend.search_key_value_store.get_emacs_var",
                        side_effect=lambda name: "" if name == "blink-search-db-path" else "kvstore"), \
             mock.patch("backend.search_key_value_store.message_emacs") as report:
            backend = SearchKeyValueStore()

        self.assertFalse(backend.usable)
        self.assertIsNone(backend.conn)
        self.assertEqual(backend.search_match("anything"), [])
        backend.clean()
        self.assertTrue(report.called)

    def test_a_path_that_is_not_a_string_switches_the_backend_off(self):
        """An Emacs variable that came back empty is not a path."""
        with mock.patch("backend.search_key_value_store.get_emacs_var",
                        side_effect=lambda name: False if name == "blink-search-db-path" else "kvstore"), \
             mock.patch("backend.search_key_value_store.message_emacs"):
            backend = SearchKeyValueStore()

        self.assertFalse(backend.usable)
        self.assertEqual(backend.search_match("anything"), [])

    def test_a_table_that_cannot_be_created_switches_the_backend_off(self):
        """A database that refuses the table is reported as well."""
        with mock.patch("backend.search_key_value_store.get_emacs_var",
                        side_effect=lambda name: self.database.name if name == "blink-search-db-path" else "bad table name!"), \
             mock.patch("backend.search_key_value_store.message_emacs") as report:
            backend = SearchKeyValueStore()

        self.assertFalse(backend.usable)
        self.assertTrue(report.called)


class UtilityTest(unittest.TestCase):
    """The helpers the backends share."""

    def test_parse_rg_line_without_a_search_path(self):
        """Without a root the candidate starts at the line number."""
        result = parse_rg_line(rg_match_line(path="/tmp/file.el", line=7, column=2))
        self.assertEqual(result["text"], "7:2: a long line of code")

    def test_parse_rg_line_with_a_search_path(self):
        """With a root the candidate starts with the relative path."""
        result = parse_rg_line(rg_match_line(path="/tmp/project/file.el", line=7, column=2),
                               "/tmp/project")
        self.assertEqual(result["text"], "file.el:7:2: a long line of code")

    def test_parse_rg_line_ignores_a_line_it_cannot_read(self):
        """A line that is not ripgrep JSON is not a candidate."""
        self.assertIsNone(parse_rg_line("not json"))
        self.assertIsNone(parse_rg_line(json.dumps({"type": "begin", "data": {}})))

    def test_insert_unique_string_to_file_does_not_duplicate(self):
        """A string is appended once, however often it is recorded."""
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "history.txt")
            Path(path).touch()
            insert_unique_string_to_file(path, "one")
            insert_unique_string_to_file(path, "one")
            insert_unique_string_to_file(path, "two")

            with open(path, encoding="utf-8") as history:
                self.assertEqual(history.read().splitlines(), ["one", "two"])


if __name__ == "__main__":
    unittest.main()


class KeyValueStorePathTest(unittest.TestCase):
    """The directory of the database is created when it is missing."""

    def test_a_missing_directory_is_created(self):
        """sqlite creates the file but not the path to it.

        On a machine where ~/.local/share or the var directory does not exist
        yet, opening the database answered "unable to open database file",
        which switched the backend off and reported a message about a file
        the user never chose.
        """
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "a", "b", "kv.db")

            def var(name):
                return path if name == "blink-search-db-path" else "kvstore"

            with mock.patch("backend.search_key_value_store.get_emacs_var", side_effect=var), \
                 mock.patch("backend.search_key_value_store.message_emacs"):
                backend = SearchKeyValueStore()

            try:
                self.assertTrue(backend.usable)
                self.assertTrue(os.path.exists(path))
            finally:
                backend.clean()
