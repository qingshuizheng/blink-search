#!/usr/bin/env python3
"""A fake Emacs for debugging the Python half of blink-search.

It speaks just enough EPC to be the peer blink_search.py expects:

* it listens on a port and is started with that port as its argument;
* it answers `get-emacs-var' / `get-emacs-vars' with a fixed table, so the
  search has a directory and a buffer name to work with;
* it prints every `eval-in-emacs' it receives, which is every answer the
  backends produce, in the order the real Emacs would get them;
* after a configurable delay it calls `search' on the Python side.

Usage:  python3 scripts/fake-emacs.py PORT [SEARCH-DELAY]

Everything it prints goes to stdout; blink_search.py's own logging goes to
stderr, so the two can be told apart.
"""

from __future__ import annotations

import logging
import sys
import threading
import time

from epc.client import EPCClient
from epc.server import ThreadingEPCServer

#: What the Python half is told when it reads an Emacs variable.  The buffer
#: name is the one a session started from a normal file buffer would have.
EMACS_VARS = {
    "blink-search-start-buffer-name": "blink-probe.el",
    "blink-search-start-buffer-directory": "/Users/qingshuizheng/Developer/blink-search",
    "blink-search-continue-directory": None,
    "blink-search-history-path": "/tmp/blink-fake-history.txt",
    "blink-search-db-path": "/tmp/blink-fake.db",
    "blink-search-db-table": "kvstore",
    "blink-search-common-directory": [["HOME", "/Users/qingshuizheng"]],
    "blink-search-grep-pdf-search-paths": [],
    "blink-search-start-path-name": "/tmp/blink-fake.pdf",
    "blink-search-enable-log": None,
    "eaf-config-location": "",
}

#: Variables whose value is a boolean, so the flag the protocol carries is t.
BOOLEAN_VARS = {"blink-search-enable-log"}


class FakeEmacs:
    """The EPC peer of blink_search.py, with the Emacs methods it needs."""

    def __init__(self, port: int, search_delay: float) -> None:
        """Serve on PORT and run a search after SEARCH-DELAY seconds."""
        self.server = ThreadingEPCServer(("127.0.0.1", port), log_traceback=True)
        self.server.allow_reuse_address = True
        self.server.register_instance(self)
        self.search_delay = search_delay
        self.evaluated = 0

        #: The port the Python half announces with its first `eval-in-emacs'
        #: call, and the client that talks to it once it is known.
        self.python_port = None
        self.client = None

        self.server_thread = threading.Thread(target=self.server.serve_forever)
        self.server_thread.start()
        print("fake emacs listening on %d" % port, flush=True)

    def _get_method(self, name: str):
        """Resolve a hyphenated EPC name to the method that answers it."""
        method = getattr(self, name.replace("-", "_"), None)
        return method if callable(method) else None

    # -- the methods blink_search.py calls ---------------------------------

    def eval_in_emacs(self, sexp_string: str):
        """Print one Elisp form, and remember the port of the Python server.

        The first call the Python half makes is
        `(blink-search--first-start PORT)', which is how the real Emacs
        learns where to reach it; the harness takes the port out of the same
        call, because that is what it needs to talk back.
        """
        self.evaluated += 1
        print("EVAL %s" % sexp_string, flush=True)

        marker = "blink-search--first-start '"
        if marker in sexp_string:
            self.python_port = int(sexp_string.split(marker)[1].rstrip(")"))
            print("PYTHON PORT %d" % self.python_port, flush=True)
        return None

    def get_emacs_var(self, var_name: str):
        """Answer one variable, in the (VALUE IS-BOOLEAN) shape Emacs uses."""
        value = EMACS_VARS.get(var_name)
        is_bool = "t" if var_name in BOOLEAN_VARS else "nil"
        print("GETVAR %s -> %r" % (var_name, value), flush=True)
        return [value, is_bool]

    def get_emacs_vars(self, var_names):
        """Answer several variables at once."""
        return [self.get_emacs_var(name) for name in var_names]

    # -- driving the Python half -------------------------------------------

    def wait_for_python(self, timeout: float = 15.0) -> bool:
        """Wait until the Python half announced its port, then connect.

        Return whether the connection was made; the caller reports the
        failure rather than raising, so that a run always prints something
        useful before it exits.
        """
        deadline = time.time() + timeout
        while time.time() < deadline and self.python_port is None:
            time.sleep(0.1)

        if self.python_port is None:
            print("PYTHON NEVER ANNOUNCED ITS PORT", flush=True)
            return False

        self.client = EPCClient(("127.0.0.1", self.python_port), log_traceback=True)
        print("CONNECTED to python port %d" % self.python_port, flush=True)
        return True

    def run_search(self, keyword: str, backends):
        """Call `search' on the Python side once it is listening."""
        if not self.wait_for_python():
            sys.exit(1)

        time.sleep(self.search_delay)
        for name in ("search_elisp_symbol_update",
                     "search_buffer_list_update",
                     "search_imenu_update",
                     "search_recent_file_update"):
            payload = {
                "search_elisp_symbol_update": ["blink-search-mode", "blink-search-quit"],
                "search_buffer_list_update": ["blink-probe.el", "*scratch*"],
                "search_imenu_update": [["defun-one", 12], ["defun-two", 30]],
                "search_recent_file_update": ["/Users/qingshuizheng/notes.org"],
            }[name]
            print("CALL %s" % name, flush=True)
            self.client.call(name, payload)

        print("CALL search %r %r" % (keyword, backends), flush=True)
        self.client.call("search", keyword, 10, backends)
        time.sleep(4)
        print("DONE, %d eval-in-emacs calls seen" % self.evaluated, flush=True)
        sys.exit(0)


def main() -> int:
    """Start the fake Emacs and drive one search."""
    logging.basicConfig(level=logging.DEBUG)
    port = int(sys.argv[1])
    delay = float(sys.argv[2]) if len(sys.argv) > 2 else 2.0
    fake = FakeEmacs(port, delay)

    keyword = "blink"
    backends = ["Elisp Symbol", "Buffer List", "IMenu", "Recent File", "Common Directory"]
    fake.run_search(keyword, backends)
    return 0


if __name__ == "__main__":
    sys.exit(main())
