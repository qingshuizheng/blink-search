#!/usr/bin/env python3
"""Tests for the backends that had no test of their own.

Four of them read command output and two of them keep state between searches,
which is where the interesting mistakes are:

* `SearchGrepPDF` and `SearchPDF` both take the page number rga prints in
  front of the match off the line again, and both have to move the byte
  offsets of the matches back by the same amount -- a `parse_lines' that
  forgets that highlights the wrong text, silently.
* `SearchGrepPDF` marks the directory a match came from with a `$Dn` marker
  when it searches more than one directory, and has to put the real path back
  when the user opens the match.
* `SearchCurrentBuffer` writes the buffer to a temporary file and removes it
  again when a candidate is opened.
* `SearchHistory` splits a recorded line back into the candidate and the
  backend that produced it, and replays it through the callbacks the session
  installs.

Nothing here runs ripgrep, rga or a search: the command output is handed to
`parse_lines' as text, and the Emacs side is replaced.

Run with:
    uv run --frozen python -m unittest test.test_search_tools
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

from backend.search_current_buffer import SearchCurrentBuffer  # noqa: E402
from backend.search_elisp_symbol import SearchElispSymbol  # noqa: E402
from backend.search_grep_pdf import SearchGrepPDF  # noqa: E402
from backend.search_history import HISTORY_SEPARATOR, SearchHistory  # noqa: E402
from backend.search_pdf import SearchPDF  # noqa: E402


def rga_match_line(path: str, page: int, text: str, start: int, end: int) -> str:
    """Build one line of rga JSON output, with its page prefix.

    rga prints the page in front of the text of the line and leaves the line
    number as None, which is exactly what the backends have to undo.
    """
    prefixed = "None:0: Page %d: %s" % (page, text)
    return json.dumps({
        "type": "match",
        "data": {
            "path": {"text": path},
            "line_number": None,
            "lines": {"text": prefixed},
            "submatches": [{"start": start, "end": end,
                            "match": {"text": prefixed[start:end]}}],
        },
    })


class GrepPDFTest(unittest.TestCase):
    """The multi directory pdf backend, driven by hand made rga output."""

    def setUp(self):
        """Build a backend whose search directories are fixed."""
        self.backend = SearchGrepPDF()
        self.backend.message_queue = queue.Queue()
        self.backend.search_paths = ["/papers/"]
        self.backend.row_number = 100

    def parse(self, line, keyword="deep work"):
        """Run one rga line through the backend and return the message."""
        self.backend.parse_lines([line], keyword, 0)
        return self.backend.message_queue.get(timeout=5)

    def test_the_page_prefix_is_taken_off_the_candidate(self):
        """The page rga printed is not part of the text the menu shows."""
        line = rga_match_line("book.pdf", 12, "None:0: Page 12: deep work is hard\n", 17, 26)
        message = self.parse(line)

        self.assertEqual(len(message["items"]), 1)
        self.assertNotIn("Page", message["items"][0]["text"])
        self.assertIn("deep work", message["items"][0]["text"])

    def test_the_match_offsets_follow_the_text(self):
        """The offsets are moved back by the length of the prefix.

        The candidate the menu shows is shorter than the line rga printed, so
        an offset that is not adjusted points at the wrong bytes.
        """
        text = "deep work is hard\n"
        prefixed = "None:0: Page 12: " + text
        start = prefixed.index("deep work")
        line = rga_match_line("book.pdf", 12, text, start, start + 9)
        message = self.parse(line)

        candidate = message["items"][0]
        self.assertEqual(candidate["text"][candidate["matches"][0][0]:candidate["matches"][0][1]],
                         "deep work")

    def test_a_candidate_that_is_not_a_pdf_is_dropped(self):
        """Only matches inside a pdf file become candidates."""
        line = rga_match_line("notes.txt", 1, "None:0: Page 1: deep work\n", 17, 26)
        message = self.parse(line)

        self.assertEqual(message["items"], [])

    def test_the_matched_text_is_kept_for_the_viewer(self):
        """The viewer is told which text to highlight."""
        text = "deep work is hard\n"
        prefixed = "None:0: Page 12: " + text
        start = prefixed.index("deep work")
        line = rga_match_line("book.pdf", 12, text, start, start + 9)
        message = self.parse(line)

        self.assertEqual(message["items"][0]["match_text"], "deep work")

    def test_one_directory_needs_no_marker(self):
        """With a single directory the path is used as it comes."""
        self.assertEqual(self.backend.get_real_path("book.pdf"), "/papers/book.pdf")

    def test_several_directories_put_the_real_path_back(self):
        """The `$Dn' marker of a candidate becomes the directory it came from."""
        # The option is written without a trailing slash in the config, which
        # is what the marker replacement expects.
        self.backend.search_paths = ["/papers", "/books"]
        self.assertEqual(self.backend.get_real_path("$D1/chapter.pdf"), "/books/chapter.pdf")
        self.assertEqual(self.backend.get_real_path("$D0/chapter.pdf"), "/papers/chapter.pdf")

    def test_a_path_without_a_marker_is_returned_as_it_is(self):
        """A match rga reported without a directory mark keeps its path."""
        self.backend.search_paths = ["/papers", "/books"]
        self.assertEqual(self.backend.get_real_path("chapter.pdf"), "chapter.pdf")

    def test_the_search_directories_come_from_the_emacs_option(self):
        """The option wins over the directory the search started in."""
        with mock.patch("backend.search_grep_pdf.get_emacs_var", return_value=["~/papers", "~/books"]):
            self.backend.init_dir("/tmp/project")
        self.assertEqual(self.backend.search_paths, ["~/papers", "~/books"])

    def test_an_empty_option_uses_the_starting_directory(self):
        """With the option empty the project of the start buffer is searched."""
        with mock.patch("backend.search_grep_pdf.get_emacs_var", return_value=None):
            self.backend.init_dir("/tmp/project")
        # A single path is wrapped in a list, which is the shape
        # `parse_lines' and `get_real_path' both index into.
        self.assertEqual(self.backend.search_paths, ["/tmp/project"])

    def test_an_empty_keyword_runs_nothing(self):
        """A keyword of whitespace only does not start rga."""
        with mock.patch("subprocess.Popen") as popen:
            self.backend.search_items("   ", 0)
        popen.assert_not_called()


class PDFTest(unittest.TestCase):
    """The single file pdf backend, driven by hand made rga output."""

    def setUp(self):
        """Build a backend that searches one file."""
        self.backend = SearchPDF()
        self.backend.message_queue = queue.Queue()
        self.backend.search_paths = ["/papers/book.pdf"]

    def test_the_page_number_is_part_of_the_candidate(self):
        """The line number of a pdf match is its page."""
        text = "deep work is hard\n"
        prefixed = "None:0: Page 12: " + text
        start = prefixed.index("deep work")
        line = rga_match_line("book.pdf", 12, text, start, start + 9)

        self.backend.parse_lines([line], "deep work", 0)
        message = self.backend.message_queue.get(timeout=5)

        self.assertEqual(len(message["items"]), 1)
        self.assertTrue(message["items"][0]["text"].startswith("12:"),
                        message["items"][0]["text"])

    def test_the_file_comes_from_the_start_buffer(self):
        """The file to search is the one the search was started from."""
        with mock.patch("backend.search_pdf.get_emacs_var", return_value="/papers/book.pdf"):
            self.backend.init_dir("/tmp")
        self.assertEqual(self.backend.search_paths, ["/papers/book.pdf"])

    def test_an_empty_keyword_runs_nothing(self):
        """A keyword of whitespace only does not start rga."""
        with mock.patch("subprocess.Popen") as popen:
            self.backend.search_items("", 0)
        popen.assert_not_called()


class CurrentBufferTest(unittest.TestCase):
    """The current buffer backend writes and removes its temporary file."""

    def setUp(self):
        """Build a backend with a temporary file of its own."""
        self.backend = SearchCurrentBuffer()
        self.backend.message_queue = queue.Queue()

    def test_the_buffer_is_written_to_a_temporary_file(self):
        """The base64 content Emacs sends is decoded and written out."""
        import base64
        content = "one\ntwo\nthree\n"
        self.backend.init_buffer("notes.el", base64.b64encode(content.encode("utf-8")).decode())

        with open(self.backend.buffer_temp_path, encoding="utf-8") as written:
            self.assertEqual(written.read(), content)
        self.addCleanup(os.unlink, self.backend.buffer_temp_path)

    def test_the_temporary_path_is_derived_from_the_buffer_name(self):
        """The same buffer name always gives the same temporary file."""
        import base64
        payload = base64.b64encode(b"content").decode()
        self.backend.init_buffer("notes.el", payload)
        first = self.backend.buffer_temp_path

        self.backend.init_buffer("notes.el", payload)
        self.assertEqual(self.backend.buffer_temp_path, first)
        self.addCleanup(os.unlink, first)

        self.backend.init_buffer("other.el", payload)
        self.assertNotEqual(self.backend.buffer_temp_path, first)
        self.addCleanup(os.unlink, self.backend.buffer_temp_path)

    def test_a_search_without_a_buffer_finds_nothing(self):
        """The backend answers an empty list before Emacs sent the content."""
        self.assertEqual(self.backend.search_match("anything"), [])


class ElispSymbolTest(unittest.TestCase):
    """The elisp symbol backend sorts and describes what Emacs pushed."""

    def test_the_shortest_symbol_comes_first(self):
        """The symbols are ordered by length, so the shortest match wins."""
        backend = SearchElispSymbol()
        backend.update(["blink-search-update-items", "car", "blink-search"])
        self.assertEqual(backend.items, ["car", "blink-search", "blink-search-update-items"])

    def test_do_describes_the_symbol(self):
        """Selecting a symbol asks Emacs for its documentation."""
        backend = SearchElispSymbol()
        with mock.patch("backend.search_elisp_symbol.eval_in_emacs") as eval_in_emacs:
            backend.do("blink-search")
        eval_in_emacs.assert_called_once_with("blink-search-elisp-symbol-do", "blink-search")


class HistoryTest(unittest.TestCase):
    """The history backend records, matches and replays."""

    def setUp(self):
        """Build a history backend over a file of its own."""
        self.path = tempfile.NamedTemporaryFile(suffix=".txt", delete=False)
        self.path.close()
        self.addCleanup(os.unlink, self.path.name)
        with open(self.path.name, "w", encoding="utf-8") as history:
            history.write("blink-search{separator}backend\n".format(separator=HISTORY_SEPARATOR))

        patcher = mock.patch("backend.search_history.get_emacs_var", return_value=self.path.name)
        patcher.start()
        self.addCleanup(patcher.stop)

        self.backend = SearchHistory()

    def test_a_recorded_line_becomes_a_candidate(self):
        """A candidate shows the recorded text and the backend it came from."""
        self.assertEqual(self.backend.search_match("blink"), ["blink-search [backend]"])

    def test_the_candidate_and_the_backend_are_split_again(self):
        """The bracket at the end of a candidate names the backend."""
        match = self.backend.split_candidate("blink-search [Find File]")
        self.assertEqual(match.group(1), "blink-search")
        self.assertEqual(match.group(2), "Find File")

    def test_a_candidate_without_a_backend_does_not_match(self):
        """A line that does not name a backend is not a history candidate."""
        self.assertIsNone(self.backend.split_candidate("blink-search"))

    def test_do_replays_through_the_callback_of_the_recorded_backend(self):
        """Selecting a history candidate runs the original backend's action."""
        calls = []
        self.backend.candiate_do_callback = lambda backend, candidate: calls.append((backend, candidate))

        self.backend.do("blink-search [Find File]")
        self.assertEqual(calls, [("Find File", "blink-search")])

    def test_parent_replays_through_the_other_callback(self):
        """The parent action goes back to the backend as well."""
        calls = []
        self.backend.candiate_parent_callback = lambda backend, candidate: calls.append((backend, candidate))

        self.backend.parent("blink-search [Find File]")
        self.assertEqual(calls, [("Find File", "blink-search")])

    def test_a_backend_that_never_ran_is_not_replayed(self):
        """Without callbacks a selection does nothing, and does not raise."""
        self.backend.do("blink-search [Find File]")


if __name__ == "__main__":
    unittest.main()
