#!/usr/bin/env python3
"""The Python half of blink-search.

Emacs starts this file with the port of the EPC server it listens on.  The
process then:

1. opens the connection back to Emacs and starts an EPC server of its own,
2. builds one instance of every search backend,
3. waits for the EPC method `search' and answers by putting candidates on a
   message queue, which a second thread turns into menu updates.

The split into an event thread and a message thread comes from the original
implementation and is what keeps the menu responsive: the event thread is
never blocked by a backend that is still running.

The module is also a command line entry point: `python3 blink_search.py PORT'.
"""

from __future__ import annotations

import importlib
import pkgutil
import queue
import sys
import threading
import traceback
from typing import Any, Dict, List, Optional

from epc.server import ThreadingEPCServer

import backend as backend_package
from core.backend import SearchBackend, backend_classes, update_method_name
from core.navigator import SearchNavigator, set_history_callbacks
from core.protocol import MESSAGE_UPDATE_BACKEND_ITEMS
from core.session import SearchSession
from core.utils import (
    close_epc_client,
    get_emacs_var,
    init_epc_client,
    logger,
)


def import_backends() -> List[str]:
    """Import every module of the backend package and return their names.

    Importing a backend is what registers it, so this is the discovery step:
    a new file under backend/ joins the menu without an edit anywhere else.
    """
    names = []
    for module_info in pkgutil.iter_modules(backend_package.__path__):
        importlib.import_module("backend.{}".format(module_info.name))
        names.append(module_info.name)
    return sorted(names)


class BlinkSearch:
    """The search process Emacs talks to over EPC.

    Every public method of this class is an EPC method, so the names and the
    argument counts are the protocol: see blink-search-protocol.el and
    core/protocol.py before renaming one.
    """

    def __init__(self, args: List[str]) -> None:
        """Start serving the Emacs that handed us the port in ARGS."""
        init_epc_client(int(args[0]))

        self.server = ThreadingEPCServer(('127.0.0.1', 0), log_traceback=True)
        self.server.allow_reuse_address = True
        self.server.register_instance(self)

        self.server_thread = threading.Thread(target=self.server.serve_forever)
        self.server_thread.start()

        if get_emacs_var("blink-search-enable-log"):
            logger.setLevel("DEBUG")

        # All Emacs requests run in the event thread.
        self.event_queue: "queue.Queue[dict]" = queue.Queue()
        self.event_loop = threading.Thread(target=self.event_dispatcher)
        self.event_loop.start()

        # All backend answers run in the message thread.
        self.message_queue: "queue.Queue[dict]" = queue.Queue()
        self.message_thread = threading.Thread(target=self.message_dispatcher)
        self.message_thread.start()

        self.session = SearchSession()
        self.backends = self.build_backends()
        self.navigator = SearchNavigator(self.backends, self.session)
        self.session.preview_callback = self.preview_backend_candidate
        set_history_callbacks(self.navigator)

        # Pass the epc port to Emacs, which is what starts the session there.
        self.server_eval_first_start()

        # The event loop never exits: this is the main loop of the process.
        self.event_loop.join()

    # -- startup -----------------------------------------------------------

    def build_backends(self) -> Dict[str, SearchBackend]:
        """Build one instance of every registered backend.

        The update methods the Elisp half calls are created here as well:
        `search_imenu_update' and friends are what Emacs uses to push the
        imenu index, the buffer list and the elisp symbols into a backend.
        """
        backends: Dict[str, SearchBackend] = {}
        for backend_class in backend_classes():
            backend = backend_class()
            # The queue is handed over after the construction: a backend needs
            # its own state before it can use the queue, and the backend that
            # opens a database needs it before it can be built at all.
            backend.message_queue = self.message_queue
            backends[backend.backend_name] = backend
            self.build_update_interface(backend_class)

        return backends

    def build_update_interface(self, backend_class) -> None:
        """Create the EPC method that pushes items into BACKEND-CLASS.

        The method name is derived from the class name, so that a backend
        cannot end up with an update method that does not name it.
        """
        def _do(*args):
            """Push ARGS into the backend this method was built for."""
            backend = self.backends.get(backend_class.NAME)
            if backend is not None:
                backend.update(*args)

        _do.__doc__ = "Push new items into the {} backend.".format(backend_class.NAME)
        setattr(self, update_method_name(backend_class), _do)

    def server_eval_first_start(self) -> None:
        """Tell Emacs the port of our EPC server."""
        from core.utils import eval_in_emacs
        eval_in_emacs('blink-search--first-start', self.server.server_address[1])

    # -- the two threads ---------------------------------------------------

    def event_dispatcher(self) -> None:
        """Run the requests that come in from Emacs, one after another."""
        try:
            while True:
                message = self.event_queue.get(True)
                self.message_handler(message)
                self.event_queue.task_done()
        except Exception:  # pylint: disable=broad-except
            logger.error(traceback.format_exc())

    def message_dispatcher(self) -> None:
        """Run the answers that come from the backends, one after another."""
        try:
            while True:
                message = self.message_queue.get(True)

                self.message_handler(message)

                self.message_queue.task_done()
        except Exception:  # pylint: disable=broad-except
            logger.error(traceback.format_exc())

    def message_handler(self, message: dict) -> None:
        """Turn one backend answer into a menu update.

        Only the candidate updates are handled here; anything else is
        logged, because a message nobody understands is a bug rather than a
        reason to stop serving.
        """
        if message.get("name") == MESSAGE_UPDATE_BACKEND_ITEMS:
            self.session.handle_message(message)
        else:
            logger.debug("ignoring unknown message %s", message)

    # -- EPC: the search itself -------------------------------------------

    def search(self, input: str, row_number: int, backend_list: List[str]) -> None:
        """Search everything for INPUT and show ROW-NUMBER candidate rows.

        BACKEND-LIST is the list of backends to search, or an empty list for
        the default one.
        """
        self.navigator.start_search(input, row_number, backend_list)

    def clean(self) -> None:
        """Tell every backend that its candidates are no longer shown."""
        self.navigator.clean()

    def cleanup(self) -> None:
        """Do some cleanup before exit python process."""
        close_epc_client()

    # -- EPC: the actions of a candidate ----------------------------------

    def search_do(self, backend: str, candidate: Any) -> None:
        """Run the default action of CANDIDATE and record it in the history."""
        self.navigator.do(backend, candidate)

    def search_copy(self, backend: str, candidate: Any) -> None:
        """Copy CANDIDATE with the backend that produced it."""
        self.navigator.copy(backend, candidate)

    def search_parent(self, backend: str, candidate: Any) -> None:
        """Open the parent of CANDIDATE."""
        self.navigator.parent(backend, candidate)

    def search_history_parent(self, backend: str, candidate: Any) -> None:
        """Open the parent of a candidate the history backend recorded."""
        self.navigator.parent(backend, candidate, True)

    def search_continue(self, backend: str, candidate: Any) -> None:
        """Search again inside the directory CANDIDATE stands for."""
        self.navigator.continue_search(backend, candidate)

    def search_init_current_buffer(self, buffer_name: str, buffer_content: str) -> None:
        """Hand the content of BUFFER-NAME to the current buffer backend.

        BUFFER-CONTENT is base64 encoded, so that a buffer with mixed
        encodings survives the EPC round trip.
        """
        backend = self.backends.get("Current Buffer")
        if backend is not None:
            backend.init_buffer(buffer_name, buffer_content)

    def search_sort_buffer_list_update(self, buffers: List[str]) -> None:
        """Replace the buffer order the buffer list backend sorts by."""
        backend = self.backends.get("Buffer List")
        if backend is not None:
            backend.update_sort_buffers(buffers)

    # -- EPC: preview and selection ---------------------------------------

    def select_candidate_item(self) -> None:
        """Preview the candidate the selection is on."""
        backend_name = self.session.selected_backend_name()
        candidate = self.session.selected_candidate()
        if backend_name is not None and candidate is not None:
            self.preview_backend_candidate(backend_name, candidate)

    def preview_backend_candidate(self, backend_name: str, candidate: Any) -> None:
        """Ask the backend named BACKEND-NAME to preview CANDIDATE."""
        backend = self.backends.get(backend_name)
        if backend is not None:
            backend.select(candidate, self.start_buffer_name())

    def start_buffer_name(self) -> str:
        """Return the name of the buffer the search started from."""
        return get_emacs_var("blink-search-start-buffer-name") or ""

    def select_next_candidate_item(self) -> None:
        """Move the selection one candidate down."""
        self.session.select_next_candidate_item()

    def select_prev_candidate_item(self) -> None:
        """Move the selection one candidate up."""
        self.session.select_prev_candidate_item()

    def select_next_backend_item(self) -> None:
        """Move the selection down inside one backend."""
        self.session.select_next_backend_item()

    def select_prev_backend_item(self) -> None:
        """Move the selection up inside one backend."""
        self.session.select_prev_backend_item()

    def select_next_candidate_group(self) -> None:
        """Move the selection to the next backend group."""
        self.session.select_next_candidate_group()

    def select_prev_candidate_group(self) -> None:
        """Move the selection to the previous backend group."""
        self.session.select_prev_candidate_group()


def main(argv: Optional[List[str]] = None) -> int:
    """Run the search process on the EPC port given on the command line."""
    arguments = sys.argv[1:] if argv is None else argv
    if len(arguments) < 1:
        print("usage: blink_search.py EPC-PORT", file=sys.stderr)
        return 2

    BlinkSearch(arguments)
    return 0


if __name__ == "__main__":
    sys.exit(main())
