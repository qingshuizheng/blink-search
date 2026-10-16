#!/usr/bin/env python3
"""Run the Python half of blink-search in one process, with a stub Emacs.

This is a debugging tool: it replaces the EPC client that `core.utils' talks
to with a stub that answers the Emacs variables the backends read, then drives
one search and prints what the message queue received.  It shows where a
search stops when the menu stays empty, without an Emacs in the loop.

    python3 scripts/local-search.py KEYWORD [BACKEND ...]
"""

from __future__ import annotations

import queue
import sys
import time
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.protocol import MESSAGE_UPDATE_BACKEND_ITEMS  # noqa: E402
from core.utils import convert_emacs_bool  # noqa: E402

VARS = {
    "blink-search-start-buffer-name": "local-search.py",
    "blink-search-start-buffer-directory": str(Path(__file__).resolve().parent.parent),
    "blink-search-continue-directory": None,
    "blink-search-history-path": "/tmp/blink-local-history.txt",
    "blink-search-db-path": "/tmp/blink-local.db",
    "blink-search-db-table": "kvstore",
    "blink-search-common-directory": [["HOME", str(Path.home())]],
    "blink-search-grep-pdf-search-paths": [],
    "blink-search-start-path-name": "/tmp/none.pdf",
    "blink-search-enable-log": None,
    "eaf-config-location": "",
}

BOOLEANS = {"blink-search-enable-log"}


class StubEmacs:
    """The two calls `core.utils' makes on the EPC client."""

    def __init__(self) -> None:
        """Record every form the search process asks Emacs to evaluate."""
        self.evaluated = []

    def call(self, method, args):
        """Accept an `eval-in-emacs' and remember the form."""
        self.evaluated.append((method, args))
        return None

    def call_sync(self, method, args):
        """Answer `get-emacs-var' and `get-emacs-vars' from VARS."""
        if method == "get-emacs-var":
            name = args[0]
            return [VARS.get(name), "t" if name in BOOLEANS else "nil"]
        if method == "get-emacs-vars":
            return [[VARS.get(name), "t" if name in BOOLEANS else "nil"] for name in args]
        raise AssertionError("unknown call %r" % method)


def main() -> int:
    """Drive one search of the real backends and print what came back."""
    keyword = sys.argv[1] if len(sys.argv) > 1 else "blink"
    backends = sys.argv[2:] or ["Elisp Symbol", "Buffer List", "IMenu", "Recent File"]

    import blink_search
    from core.backend import backend_names

    # `BlinkSearch.__init__' does this in the real process; the diagnostic
    # builds the object by hand, so it does it here.
    blink_search.import_backends()
    print("registered backends: %d" % len(backend_names()))

    messages = queue.Queue()
    # The backends read Emacs variables while they are built (the key/value
    # one opens its database), so the stub client has to be in place first.
    stub = StubEmacs()
    mock.patch("core.utils.epc_client", stub).start()

    process = blink_search.BlinkSearch.__new__(blink_search.BlinkSearch)

    from core.navigator import SearchNavigator, set_history_callbacks
    from core.session import SearchSession

    process.message_queue = messages
    process.session = SearchSession()
    process.backends = process.build_backends()
    process.navigator = SearchNavigator(process.backends, process.session)
    process.session.preview_callback = process.preview_backend_candidate
    set_history_callbacks(process.navigator)

    print("built backends: %d" % len(process.backends))
    print("update methods: %d" % len([n for n in dir(process) if n.endswith("_update")]))

    # The backends that only answer when Emacs pushes state to them.
    process.search_elisp_symbol_update(["blink-search-mode", "blink-search-quit"])
    process.search_imenu_update([["defun-one", 12]])
    backend_list = [name for name in backends if name in process.backends]
    print("searching %r over %r" % (keyword, backend_list))

    # `core.session' imports the name, so that is where it has to be replaced.
    # The patch has to cover the message loop below as well, because that is
    # where the session renders what the backends answered.
    with mock.patch("core.session.eval_in_emacs") as eval_in_emacs:
        process.search(keyword, 10, backend_list)
        time.sleep(3)

    with mock.patch("core.session.eval_in_emacs") as eval_in_emacs:
        seen = 0
        while not messages.empty():
            message = messages.get()
            seen += 1
            print("MESSAGE %s %s items=%d" % (message["name"], message["backend"],
                                              len(message.get("items") or [])))
            # The dispatcher thread does this in the real process; calling it
            # here keeps the diagnostic single threaded.
            if message["name"] == MESSAGE_UPDATE_BACKEND_ITEMS:
                process.session.handle_message(message)

        print("messages: %d" % seen)
        print("candidate items in the session: %d" % len(process.session._candidate_items))
        print("rendered rows: %d" % len(process.session._render_candidate_items))
        print("update calls to Emacs: %d" % len(eval_in_emacs.call_args_list))
        for call in eval_in_emacs.call_args_list:
            args = call.args
            if args and args[0] == "blink-search-update-items":
                print("UPDATE-ITEMS candidates=%d backend=%s" % (len(args[1]), args[5]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
