#!/usr/bin/env python3
"""Which backends a search runs over, and what a selection records.

The menu is not a list of every backend: the default list is what
`blink-search-search-backends' says, or the list in core.protocol when the
option is empty, with the PDF backend joining it only when the buffer the
search started from is a pdf file and rga is installed to read it.

This module also owns the history file: one line per action, holding the
candidate and the name of the backend it was taken from, so that the history
backend can replay the original action later.
"""

from __future__ import annotations

import os
import threading
from typing import Any, Dict, List, Optional

from core.backend import SearchBackend
from core.protocol import DEFAULT_BACKENDS, PDF_BACKEND
from core.session import SearchSession
from core.utils import get_emacs_var, get_emacs_vars, insert_unique_string_to_file, logger, touch

#: The character that separates a recorded candidate from the name of the
#: backend it came from, in the history file.
HISTORY_SEPARATOR = "ᛡ"

#: The backends whose selections are not worth recording: a history entry
#: that points back at the history itself can never be replayed.
BACKENDS_NOT_RECORDED = ("History", "PDF", "Current Buffer", "IMenu", "Grep File")


class SearchNavigator:
    """The backends of a session and the rules that drive them."""

    def __init__(self, backends: Dict[str, SearchBackend], session: SearchSession) -> None:
        """Build a navigator over BACKENDS that renders into SESSION."""
        self.backends = backends
        self.session = session
        self._history_threads: List[threading.Thread] = []

    # -- which backends answer --------------------------------------------

    def backend_names(self) -> List[str]:
        """Return the names of the backends a search runs over."""
        return self.session.backend_list()

    def default_backends(self, start_buffer_name: str) -> List[str]:
        """Return the backends used when the user configured none.

        PDF joins the list only when the file the search started from is a
        pdf and rga is installed, so that an ordinary search never waits for
        an rga run that would find nothing.
        """
        backend_list = list(DEFAULT_BACKENDS)

        if _rga_installed() and start_buffer_name.endswith(".pdf"):
            if PDF_BACKEND not in backend_list:
                backend_list.insert(2, PDF_BACKEND)
        elif PDF_BACKEND in backend_list:
            backend_list.remove(PDF_BACKEND)

        return backend_list

    # -- starting a search -------------------------------------------------

    def start_search(self, input_keyword: str, row_number: int, backend_list: List[str]) -> None:
        """Search everything for INPUT-KEYWORD and show ROW-NUMBER rows.

        BACKEND_LIST is the list the Elisp half asked for, or an empty list
        to use the default one.  Every backend is told which directory to
        search in before it is asked to search, because a backend that runs
        an external command needs to know it.
        """
        self.session.row_number = row_number

        if len(backend_list) == 0:
            start_buffer_name = get_emacs_var("blink-search-start-buffer-name") or ""
            self.session.set_backend_list(self.default_backends(start_buffer_name))
        else:
            self.session.set_backend_list(backend_list)

        start_directory, continue_directory = get_emacs_vars([
            "blink-search-start-buffer-directory",
            "blink-search-continue-directory"])

        if continue_directory:
            self.search_init_search_dir(continue_directory)
        else:
            self.search_init_search_dir(start_directory)

        for backend_name in self.session.backend_list():
            backend = self.backends.get(backend_name)
            if backend is not None:
                backend.search(input_keyword)

    def search_init_search_dir(self, start_dir: str) -> None:
        """Tell every backend that supports it where to search.

        A backend that does not implement `init_dir' above the base class
        does not use a directory, so it is skipped rather than called with
        an argument it would ignore.
        """
        for backend in self.backends.values():
            init_dir = getattr(backend, "init_dir", None)
            if init_dir is not None and init_dir.__func__ is not SearchBackend.init_dir:
                init_dir(start_dir)

    # -- what a selection records -----------------------------------------

    def record_history(self, backend_name: str, candidate: Any) -> None:
        """Append the selection of CANDIDATE in BACKEND-NAME to the history.

        A backend may know a better name for a candidate than the text the
        menu shows, which is what `record_name' is for: a file candidate is
        recorded as an absolute path, so that replaying it does not depend
        on the directory the next search starts from.
        """
        if backend_name in BACKENDS_NOT_RECORDED:
            return

        history_path = get_emacs_var("blink-search-history-path")
        if not os.path.exists(history_path):
            touch(history_path)

        backend = self.backends.get(backend_name)
        record_name = getattr(backend, "record_name", None)
        if record_name is not None:
            candidate = record_name(candidate)

        history_item = f"{candidate}{HISTORY_SEPARATOR}{backend_name}"
        insert_unique_string_to_file(history_path, history_item)

    def record_history_async(self, backend_name: str, candidate: Any) -> None:
        """Record the selection of CANDIDATE on a thread of its own.

        Writing the history file must not delay the action the user asked
        for, so it happens next to it.
        """
        thread = threading.Thread(target=self.record_history, args=(backend_name, candidate))
        thread.start()
        self._history_threads.append(thread)

    # -- running an action -------------------------------------------------

    def do(self, backend_name: str, candidate: Any) -> None:
        """Run the default action of CANDIDATE and record it."""
        self.record_history_async(backend_name, candidate)

        backend = self.backends.get(backend_name)
        if backend is not None:
            backend.do(candidate)

    def copy(self, backend_name: str, candidate: Any) -> None:
        """Copy CANDIDATE with the backend that produced it."""
        backend = self.backends.get(backend_name)
        if backend is not None:
            backend.copy(candidate)

    def parent(self, backend_name: str, candidate: Any, from_history: bool = False) -> None:
        """Open the parent of CANDIDATE.

        FROM-HISTORY marks a candidate the history backend handed over,
        which the backend it came from has to treat differently.
        """
        backend = self.backends.get(backend_name)
        if backend is not None:
            backend.parent(candidate, from_history)

    def continue_search(self, backend_name: str, candidate: Any) -> None:
        """Search again inside the directory CANDIDATE stands for."""
        backend = self.backends.get(backend_name)
        if backend is None:
            return

        continue_search = getattr(backend, "continue_search", None)
        if continue_search is not None:
            continue_search(candidate)
        else:
            from core.utils import message_emacs
            message_emacs("{} not support continue search.".format(backend.backend_name))

    def clean(self) -> None:
        """Tell every backend that its candidates are no longer shown."""
        for backend in self.backends.values():
            clean = getattr(backend, "clean", None)
            if clean is not None:
                clean()


def _rga_installed() -> bool:
    """Return whether the `rga' command is available on this machine."""
    import shutil
    return shutil.which("rga") is not None


def set_history_callbacks(navigator: SearchNavigator) -> None:
    """Point the history backend at NAVIGATOR, so that it can replay actions.

    The history backend hands a recorded candidate back to the backend that
    produced it, which is the navigator's job; the two callbacks it needs
    are installed here rather than in the backend, because the backend has
    no way to reach the other backends.
    """
    history = navigator.backends.get("History")
    if history is None:
        logger.debug("no history backend registered, history replay is off")
        return

    history.candiate_do_callback = navigator.do
    history.candiate_parent_callback = lambda backend, candidate: navigator.parent(backend, candidate, True)


def selected_backend_name(session: SearchSession) -> Optional[str]:
    """Return the name of the backend the session selected, or None."""
    return session.selected_backend_name()
