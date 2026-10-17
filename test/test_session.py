#!/usr/bin/env python3
"""Tests for the state and the navigation of one search session.

The session is where the menu's arithmetic lives, so the tests below drive it
from one message to the next and check the rows it decides to show.  Nothing
here needs Emacs: `core.session.eval_in_emacs' is replaced by a recorder, so
the tests also check what the Elisp half would have been told.

Run with:
    uv run --frozen python -m unittest test.test_session
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.protocol import MESSAGE_UPDATE_BACKEND_ITEMS  # noqa: E402
from core.session import SearchSession  # noqa: E402


def update_message(backend: str, keyword: str, items: list) -> dict:
    """Build the message a backend puts on the queue for ITEMS."""
    return {
        "name": MESSAGE_UPDATE_BACKEND_ITEMS,
        "backend": backend,
        "items": items,
        "keyword": keyword,
    }


class SessionTestCase(unittest.TestCase):
    """A session with the calls to Emacs recorded instead of sent."""

    def setUp(self):
        """Build a session that renders eight rows and record its updates."""
        self.updates = []
        patcher = mock.patch("core.session.eval_in_emacs",
                             side_effect=lambda *args: self.updates.append(args))
        self.addCleanup(patcher.stop)
        patcher.start()

        self.session = SearchSession()
        self.session.row_number = 8
        self.session.set_backend_list(["Alpha", "Beta"])

    def last_update(self):
        """Return the argument list of the last update sent to Emacs."""
        return self.updates[-1]

    def test_one_backend_shows_every_candidate(self):
        """A single backend is not squeezed to share the window."""
        self.session.set_backend_list(["Alpha"])
        self.session.handle_message(update_message("Alpha", "a", ["a1", "a2", "a3"]))

        update = self.last_update()
        # (candidate items, candidate index, backend items, backend index,
        #  backend name, position, total, backend number)
        self.assertEqual(len(update[1]), 3)
        self.assertEqual(update[5], "Alpha")
        self.assertEqual(update[6], 1)
        self.assertEqual(update[7], 3)
        self.assertEqual(update[8], 1)

    def test_several_backends_share_the_window(self):
        """Every backend that has a candidate shows at least five of them."""
        self.session.handle_message(update_message("Alpha", "a", ["a%d" % i for i in range(20)]))
        self.session.handle_message(update_message("Beta", "a", ["b%d" % i for i in range(20)]))

        update = self.last_update()
        # five rows per backend are offered, and the window shows the eight
        # that fit; the ninth row is reached by scrolling.
        self.assertEqual(len(update[1]), self.session.window_size)
        self.assertEqual(update[1][0]["backend"], "Alpha")
        self.assertEqual(update[1][5]["backend"], "Beta")

    def test_a_new_keyword_moves_the_selection_to_the_top(self):
        """Changing the keyword restarts the menu at the first candidate."""
        self.session.handle_message(update_message("Alpha", "a", ["a%d" % i for i in range(20)]))
        self.session.select_next_candidate_item()
        self.session.select_next_candidate_item()
        self.assertEqual(self.last_update()[2], 2)

        self.session.handle_message(update_message("Alpha", "ab", ["a%d" % i for i in range(20)]))
        self.assertEqual(self.last_update()[2], 0)

    def test_the_selection_can_walk_the_whole_answer(self):
        """Moving down far enough selects every candidate of one backend.

        The menu shows eight rows at a time, so the window has to scroll once
        the selection reaches the bottom row; with several backends the
        window is made of their slices and is shorter than eight rows, which
        is the other case and is covered by the group tests.
        """
        self.session.set_backend_list(["Alpha"])
        self.session.handle_message(update_message("Alpha", "a", ["a%d" % i for i in range(20)]))

        for _ in range(12):
            self.session.select_next_candidate_item()

        self.assertEqual(self.session.selected_candidate(), "a12")

        # the window scrolled: a12 was not one of the first eight candidates
        # the answer offered, and it is not on the last row of the window
        # either, because the window stops growing when it reaches the end.
        candidate_items = self.last_update()[1]
        self.assertNotIn("a12", ["a%d" % i for i in range(8)])
        self.assertIn("a12", [item["candidate"] for item in candidate_items])

    def test_the_selection_stops_at_the_last_candidate(self):
        """The last candidate does not scroll past the end of the answer."""
        self.session.handle_message(update_message("Alpha", "a", ["a1", "a2"]))

        self.session.select_next_candidate_item()
        before = len(self.updates)
        self.session.select_next_candidate_item()
        self.assertEqual(len(self.updates), before)

    def test_the_selection_stops_at_the_first_candidate(self):
        """The first candidate does not scroll above the start of the answer."""
        self.session.handle_message(update_message("Alpha", "a", ["a1", "a2"]))

        before = len(self.updates)
        self.session.select_prev_candidate_item()
        self.assertEqual(len(self.updates), before)

    def test_group_navigation_jumps_to_the_next_backend(self):
        """Group navigation lands on the first candidate of the next backend."""
        self.session.handle_message(update_message("Alpha", "a", ["a%d" % i for i in range(6)]))
        self.session.handle_message(update_message("Beta", "a", ["b%d" % i for i in range(6)]))

        self.assertEqual(self.session.group_index_list(), [0, 5])

        self.session.select_next_candidate_group()
        self.assertEqual(self.last_update()[5], "Beta")
        self.assertEqual(self.session.selected_candidate(), "b0")

    def test_group_navigation_goes_back_to_the_previous_backend(self):
        """Group navigation upwards lands on the previous backend again."""
        self.session.handle_message(update_message("Alpha", "a", ["a%d" % i for i in range(6)]))
        self.session.handle_message(update_message("Beta", "a", ["b%d" % i for i in range(6)]))

        self.session.select_next_candidate_group()
        self.session.select_prev_candidate_group()
        self.assertEqual(self.session.selected_candidate(), "a0")

    def test_an_empty_answer_clears_the_menu(self):
        """A search that found nothing renders an empty menu."""
        self.session.handle_message(update_message("Alpha", "a", ["a1"]))
        self.session.handle_message(update_message("Alpha", "zzz", []))

        update = self.last_update()
        self.assertEqual(update[1], [])
        self.assertEqual(update[3], [])
        self.assertEqual(update[5], "")
        self.assertEqual(update[6], 0)

    def test_moving_inside_a_backend_previews_the_candidate(self):
        """The backend window asks its owner to preview what it selected."""
        previews = []
        self.session.preview_callback = lambda backend, candidate: previews.append((backend, candidate))
        self.session.handle_message(update_message("Alpha", "a", ["a%d" % i for i in range(4)]))

        self.session.select_next_backend_item()
        self.assertEqual(previews, [("Alpha", "a1")])

    def test_backend_candidate_number_of_an_unknown_backend_is_zero(self):
        """A backend that has not answered yet counts as empty."""
        self.assertEqual(self.session.backend_candidate_number("Gamma"), 0)

    def test_an_unknown_message_is_ignored(self):
        """A message the session does not understand changes nothing."""
        self.session.handle_message(update_message("Alpha", "a", ["a1"]))
        before = len(self.updates)
        self.session.handle_message({"name": "something_else"})
        self.assertEqual(len(self.updates), before)


if __name__ == "__main__":
    unittest.main()


class StartSearchTestCase(unittest.TestCase):
    """What `start_search' does with the variables it reads from Emacs."""

    def setUp(self):
        """Build a navigator over one recording backend."""
        from core.navigator import SearchNavigator

        self.searched = []
        self.initialised = []

        class RecordingBackend:
            """A backend that records what the navigator tells it."""

            backend_name = "Recording"

            def search(self, keyword):
                """Remember the keyword the navigator passed on."""
                self_outer.searched.append(keyword)

            def init_dir(self, directory):
                """Remember the directory the navigator passed on."""
                self_outer.initialised.append(directory)

        self_outer = self
        self.backend = RecordingBackend()
        self.session = SearchSession()
        self.session.row_number = 10
        self.navigator = SearchNavigator({"Recording": self.backend}, self.session)

    def test_a_directory_that_is_not_a_string_is_skipped(self):
        """An empty answer from Emacs does not reach the backends.

        This is the crash that left the menu empty: the start directory
        arrived as False, a backend handed it to `os.path.expanduser', and
        the TypeError came back through EPC instead of any candidate.
        """
        with mock.patch("core.navigator.logger"):
            self.navigator.search_init_search_dir(False)
        self.assertEqual(self.initialised, [])

    def test_an_empty_directory_is_skipped(self):
        """An empty string is not a directory either."""
        with mock.patch("core.navigator.logger"):
            self.navigator.search_init_search_dir("")
        self.assertEqual(self.initialised, [])

    def test_a_real_directory_reaches_every_backend(self):
        """A directory a backend knows what to do with is passed on."""
        self.navigator.search_init_search_dir("/tmp/project")
        self.assertEqual(self.initialised, ["/tmp/project"])

    def test_a_search_still_starts_without_a_directory(self):
        """A search with no directory still asks the backends to search.

        The backends that run over a directory find nothing without one, but
        the ones that do not -- the buffer list, the elisp symbols, the
        history -- still answer, which is what keeps the menu useful.
        """
        with mock.patch("core.navigator.get_emacs_vars", return_value=[False, False]), \
             mock.patch("core.navigator.get_emacs_var", return_value=""), \
             mock.patch("core.navigator.logger"):
            self.navigator.start_search("blink", 10, ["Recording"])

        self.assertEqual(self.searched, ["blink"])
        self.assertEqual(self.initialised, [])
