#!/usr/bin/env python3
"""Tests for the wiring of the search process.

What is checked here is the part of `BlinkSearch` that builds the backends and
the EPC methods around them, without an Emacs and without a network: the EPC
server, the connection back to Emacs and the two loops are replaced.  A backend
that is registered but never instantiated, or an update method that the Elisp
half calls but that was never built, is what these tests are for.

Run with:
    uv run --frozen python -m unittest test.test_process
"""

from __future__ import annotations

import queue
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import blink_search  # noqa: E402
from core.backend import backend_names, update_names  # noqa: E402


class ProcessWiringTest(unittest.TestCase):
    """`BlinkSearch' is built by hand, so that no process is started."""

    @classmethod
    def setUpClass(cls):
        """Import every backend, which is what registers them."""
        blink_search.import_backends()

    def setUp(self):
        """Build a process object without starting anything.

        The key value backend opens a database when it is built, so the two
        Emacs variables it reads are answered here; an in-memory database
        keeps the test from writing anything.
        """
        def fake_get_emacs_var(name):
            """Answer the two variables the key value backend reads."""
            return ":memory:" if name == "blink-search-db-path" else "kvstore"

        patcher = mock.patch("backend.search_key_value_store.get_emacs_var",
                             side_effect=fake_get_emacs_var)
        patcher.start()
        self.addCleanup(patcher.stop)

        self.process = blink_search.BlinkSearch.__new__(blink_search.BlinkSearch)
        self.process.message_queue = queue.Queue()
        self.process.backends = self.process.build_backends()

    def test_every_registered_backend_is_instantiated(self):
        """The menu is built from the registry, so every entry is an instance."""
        self.assertEqual(sorted(self.process.backends), sorted(backend_names()))

    def test_every_backend_gets_the_message_queue(self):
        """A backend that answers nowhere would leave the menu empty."""
        for name, backend in self.process.backends.items():
            self.assertIs(backend.message_queue, self.process.message_queue, name)

    def test_every_update_method_is_built(self):
        """The Elisp half calls one update method per backend module."""
        for name in update_names():
            self.assertTrue(callable(getattr(self.process, name, None)), name)

    def test_an_update_method_reaches_its_backend(self):
        """Calling `search_imenu_update' replaces the imenu candidates."""
        self.process.search_imenu_update([["defun-one", 12]])
        self.assertEqual(self.process.backends["IMenu"].item_dict, {"defun-one": 12})

    def test_the_history_backend_can_replay_through_the_others(self):
        """The navigator installs the two callbacks the history backend needs."""
        from core.navigator import SearchNavigator, set_history_callbacks
        from core.session import SearchSession

        session = SearchSession()
        navigator = SearchNavigator(self.process.backends, session)
        set_history_callbacks(navigator)

        history = self.process.backends["History"]
        self.assertEqual(history.candiate_do_callback, navigator.do)
        self.assertTrue(callable(history.candiate_parent_callback))

    def test_the_default_backend_list_is_what_the_protocol_declares(self):
        """The navigator falls back to the list in core.protocol."""
        from core.navigator import SearchNavigator
        from core.protocol import DEFAULT_BACKENDS
        from core.session import SearchSession

        navigator = SearchNavigator(self.process.backends, SearchSession())
        # An empty buffer name is not a pdf, so the PDF backend stays out.
        self.assertEqual(navigator.default_backends(""), list(DEFAULT_BACKENDS))

    def test_the_pdf_backend_joins_for_a_pdf_buffer_when_rga_is_installed(self):
        """A pdf buffer is searched with rga when rga is available."""
        from core.navigator import SearchNavigator
        from core.protocol import PDF_BACKEND
        from core.session import SearchSession

        navigator = SearchNavigator(self.process.backends, SearchSession())
        with mock.patch("core.navigator._rga_installed", return_value=True):
            backend_list = navigator.default_backends("/tmp/paper.pdf")

        self.assertIn(PDF_BACKEND, backend_list)


if __name__ == "__main__":
    unittest.main()
