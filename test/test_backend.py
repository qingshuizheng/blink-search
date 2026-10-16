#!/usr/bin/env python3
"""Tests for the base class and the registry of the search backends.

The threading discipline is what these tests are about: a backend answers on
a message queue, and only the answer of the newest search may reach it.  The
rest is plain filtering, which is checked against a small backend built here
so that a real one is not needed.

Run with:
    uv run --frozen python -m unittest test.test_backend
"""

from __future__ import annotations

import queue
import re
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.backend import (  # noqa: E402  (import after sys.path)
    SearchBackend,
    backend_classes,
    backend_names,
    register_backend,
    update_method_name,
    update_names,
)


class SampleBackend(SearchBackend):
    """A backend that filters a fixed list of candidate names."""

    NAME = "Sample"

    def __init__(self, message_queue=None, items=None):
        """Build the sample with ITEMS as its candidate pool."""
        super().__init__(message_queue)
        self.items = items if items is not None else ["alpha", "beta", "alphabet"]


class BackendBaseTest(unittest.TestCase):
    """The behaviour every backend inherits."""

    def test_backend_name_comes_from_the_class(self):
        """An instance cannot disagree with the registry about its name."""
        self.assertEqual(SampleBackend().backend_name, "Sample")

    def test_is_match_prefix_contains_and_ordered_words(self):
        """All the ways a candidate may match a keyword are accepted."""
        backend = SampleBackend()
        no_match = re.compile("zzz")
        self.assertTrue(backend.is_match("alph", no_match, "alphabet"))
        self.assertTrue(backend.is_match("phab", no_match, "alphabet"))
        self.assertTrue(backend.is_match("alpha", no_match, "alphabet"))
        self.assertFalse(backend.is_match("zulu", no_match, "alphabet"))

    def test_is_match_matches_the_words_in_order(self):
        """The words of a keyword have to appear in order."""
        backend = SampleBackend()
        ordered = re.compile(".*" + ".*".join("alpha beta".split()), re.IGNORECASE)
        reversed_order = re.compile(".*" + ".*".join("beta alpha".split()), re.IGNORECASE)
        self.assertTrue(backend.is_match("alpha beta", ordered, "alpha beta gamma"))
        self.assertFalse(backend.is_match("beta alpha", reversed_order, "alpha beta gamma"))

    def test_search_match_ignores_the_star_wildcards(self):
        """A star is a wildcard of the Elisp half, not part of the keyword."""
        backend = SampleBackend()
        self.assertEqual(sorted(backend.search_match("*alph")), ["alpha", "alphabet"])

    def test_search_sends_the_candidates_to_the_queue(self):
        """A search puts one update message on the message queue."""
        messages = queue.Queue()
        backend = SampleBackend(messages)
        backend.search("alpha")

        for thread in backend.search_thread_queue:
            thread.join(timeout=5)

        message = messages.get(timeout=5)
        self.assertEqual(message["name"], "update_backend_items")
        self.assertEqual(message["backend"], "Sample")
        self.assertEqual(message["keyword"], "alpha")
        self.assertEqual(sorted(message["items"]), ["alpha", "alphabet"])
        self.assertEqual(backend.search_ticker, 1)

    def test_a_stale_search_does_not_reach_the_queue(self):
        """The answer of an older search is dropped, not merged.

        This is the race a fast typist creates: the first search is still
        running when the second one finishes, and the first one must not
        overwrite the newer candidates.
        """
        messages = queue.Queue()
        backend = SampleBackend(messages)
        backend.search_ticker = 2

        backend.send_candidates(["old"], "old", 1)
        self.assertTrue(messages.empty())

        backend.send_candidates(["new"], "new", 2)
        self.assertFalse(messages.empty())

    def test_default_actions_do_not_raise(self):
        """A backend that cannot open a candidate still answers every call."""
        backend = SampleBackend()
        backend.do("alpha")
        backend.parent("alpha")
        backend.clean()
        backend.init_dir("/tmp")

    def test_kill_sub_process_is_safe_without_a_process(self):
        """Cleaning up before anything ran is not an error."""
        backend = SampleBackend()
        backend.kill_sub_process()
        self.assertIsNone(backend.sub_process)


class _RegisteredForTest(SearchBackend):
    """A backend registered only for the registry tests below.

    It is registered from `setUpClass', with the module name of this file
    patched so that the registry accepts it: a backend only ever lives in
    backend/search_*.py, and the decorator refuses anything else.
    """

    NAME = "Registered For Test"


class BackendRegistryTest(unittest.TestCase):
    """The registry the EPC layer and the menu are built from."""

    @classmethod
    def setUpClass(cls):
        """Register `_RegisteredForTest' as if it lived in a backend module."""
        with mock.patch.object(_RegisteredForTest, "__module__", "backend.search_registered_for_test"):
            register_backend(_RegisteredForTest)

    def test_register_backend_keeps_the_class(self):
        """The class decorated for this module is found by its name."""
        self.assertIn(_RegisteredForTest, backend_classes())
        self.assertIn("Registered For Test", backend_names())
        self.assertIn(update_method_name(_RegisteredForTest), update_names())

    def test_register_backend_refuses_a_class_without_a_name(self):
        """A backend without a name would be unreachable, so it is an error."""
        with self.assertRaises(ValueError):
            @register_backend
            class Nameless(SearchBackend):
                """A backend that forgot to declare its name."""

    def test_update_method_name_comes_from_the_module(self):
        """The EPC update method is named after the module the class is in.

        This is the reason it is not derived from the class name: the class
        names of the real backends cannot be split back into words (EAF and
        IMenu both lose letters), while the module they live in is already
        named after the method the Elisp half calls.
        """
        from backend.search_eaf_browser_history import SearchEAFBrowserHistory

        self.assertEqual(update_method_name(SearchEAFBrowserHistory),
                         "search_eaf_browser_history_update")

    def test_every_registered_backend_has_an_update_method(self):
        """The two lists the protocol is built from stay in step."""
        self.assertEqual(len(backend_names()), len(update_names()))
        for name in update_names():
            self.assertTrue(name.endswith("_update"), name)


if __name__ == "__main__":
    unittest.main()
