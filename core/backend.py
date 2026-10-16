#!/usr/bin/env python3
"""The base class and the registry of the search backends.

A backend is a source of candidates: it is asked to search for a keyword, and
it answers by putting one message on the message queue.  This module holds the
contract every backend implements (`SearchBackend'), the registry that gives
the EPC layer a way to find a backend by name (`backend_class' and
`backend_by_name'), and the update method names that are part of the protocol
between the two halves (`update_method_name' and `UPDATE_NAMES').

A backend subclasses `SearchBackend' and declares its backend name, which is
both the name the user writes in `blink-search-search-backends' and the key
the menu groups candidates by:

    @register_backend
    class SearchRecentFile(SearchBackend):
        NAME = "Recent File"

The class name also decides the name of the method the Elisp half calls to
push state into the backend: `SearchEAFBrowserHistory' becomes
`search_eaf_browser_history_update'.  `UPDATE_NAMES' collects them, and
scripts/check-backend-contract.py fails the build when the Elisp half calls a
name that no backend builds.
"""

from __future__ import annotations

import re
import subprocess
import threading
from typing import Any, Dict, List, Optional, Tuple, Type

#: backend class -> (NAME, module base name), filled by the decorator.
_BACKENDS: Dict[Type["SearchBackend"], Tuple[str, str]] = {}


def update_method_name(cls: Type[Any]) -> str:
    """Return the EPC method name that pushes items into the backend CLS."""
    module_name = _BACKENDS.get(cls, ("", ""))[1]
    return "{}_update".format(module_name)


def register_backend(cls: Type["SearchBackend"]) -> Type["SearchBackend"]:
    """Register CLS in the backend registry and return it unchanged.

    The decorator is applied at class definition time, so importing a backend
    module is what makes the backend known.  A backend without a NAME is a
    programming error and raises immediately, rather than turning into a
    backend that can never be selected.
    """
    if not getattr(cls, "NAME", None):
        raise ValueError("{} must define NAME".format(cls.__name__))
    module_name = cls.__module__.rsplit(".", 1)[-1]
    if not module_name.startswith("search_"):
        raise ValueError("{} lives in {}, which is not a search_ module".format(cls.__name__, cls.__module__))
    _BACKENDS[cls] = (cls.NAME, module_name)
    return cls


def backend_classes() -> List[Type["SearchBackend"]]:
    """Return every registered backend class, in registration order."""
    return list(_BACKENDS)


def backend_names() -> List[str]:
    """Return the name of every registered backend, in registration order."""
    return [name for name, _module in _BACKENDS.values()]


def update_names() -> List[str]:
    """Return the EPC update method name of every registered backend."""
    return [update_method_name(cls) for cls in _BACKENDS]


class SearchBackend:
    """Base class of every search backend.

    A backend answers three questions: which candidates match a keyword
    (`search'), what to do with the selected one (`do', `copy', `parent',
    `continue_search'), and what state the Elisp half has to push to it
    (`update', `init_dir', ...).

    The threading discipline is the part that is easy to get wrong, so the
    base class owns it:

    * `search' starts one thread per keystroke and remembers a ticker for it.
      A backend's `search_items' puts its answer on the message queue only
      when its ticker is still the current one, which is what keeps a slow
      search from overwriting the candidates of a newer one.
    * `get_process_result' runs one external command with the backend's own
      `sub_process' slot, killing the previous one first, so that two
      searches of the same backend cannot both write to the same pipe.
    """

    #: Name of the backend, as the user writes it in
    #: `blink-search-search-backends'.  Every subclass must set it.
    NAME: str = ""

    def __init__(self, message_queue=None) -> None:
        """Build a backend that answers on MESSAGE_QUEUE.

        The backend name is taken from the class, so an instance cannot
        disagree with the registry about how it is called.  MESSAGE-QUEUE may
        be left out while a subclass is still setting itself up; the session
        fills it in before the first search.
        """
        self.backend_name = self.NAME
        self.message_queue = message_queue
        self.search_ticker = 0
        self.search_thread_queue: List[threading.Thread] = []
        self.items: List[Any] = []
        self.sub_process: Optional[subprocess.Popen] = None

    def __repr__(self) -> str:
        """Return a debugging form that names the backend and its class."""
        return "<{} {}>".format(self.NAME, type(self).__name__)

    # -- searching ---------------------------------------------------------

    def search(self, prefix: str) -> None:
        """Search for PREFIX on a worker thread and answer on the queue."""
        ticker = self.search_ticker + 1
        self.search_ticker = ticker

        search_thread = threading.Thread(target=lambda: self.search_items(prefix, ticker))
        search_thread.start()
        self.search_thread_queue.append(search_thread)

    def search_items(self, prefix: str, ticker: int) -> None:
        """Answer the search for PREFIX tagged with TICKER.

        The default implementation filters `self.items' and sends the result
        on the message queue when TICKER is still the current one.  A backend
        that runs an external command overrides this instead.
        """
        candidates = self.search_match(prefix)
        self.send_candidates(candidates, prefix, ticker)

    def search_match(self, prefix: str) -> List[Any]:
        """Return the candidates of `self.items' that match PREFIX."""
        prefix = prefix.replace("*", "")
        prefix_regexp = re.compile(".*" + ".*".join(prefix.split()), re.IGNORECASE)
        return list(filter(lambda symbol: self.is_match(prefix, prefix_regexp, symbol), self.items))

    def send_candidates(self, candidates: List[Any], prefix: str, ticker: int) -> None:
        """Put CANDIDATES on the message queue when TICKER is current.

        A backend that found its candidates in several batches calls this
        once per batch, which is what makes the menu fill in progress.
        """
        if ticker == self.search_ticker:
            self.message_queue.put({
                "name": "update_backend_items",
                "backend": self.backend_name,
                "items": candidates,
                "keyword": prefix,
            })

    def is_match(self, prefix: str, prefix_regexp, symbol: str) -> bool:
        """Return whether SYMBOL matches PREFIX.

        A symbol matches when it starts with the prefix, when it starts with
        the prefix once its dashes are removed, when it contains the prefix,
        or when the words of the prefix appear in it in order.
        """
        return (symbol.startswith(prefix)
                or symbol.replace("-", "").startswith(prefix)
                or prefix in symbol
                or bool(prefix_regexp.match(symbol)))

    # -- state the Elisp half pushes in ------------------------------------

    def update(self, items: List[str]) -> None:
        """Replace the candidate pool with ITEMS, shortest first."""
        self.items = sorted(items, key=len)

    def init_dir(self, search_dir: str) -> None:
        """Remember the directory a search should start from.

        The default is a no-op: only the backends that run an external
        command over a directory need it.
        """
        del search_dir

    # -- actions -----------------------------------------------------------

    def select(self, candidate: Any, start_buffer_name: str) -> None:
        """Preview CANDIDATE in the buffer the search started from."""
        del candidate
        from core.utils import eval_in_emacs
        eval_in_emacs("blink-search-select-start-buffer", start_buffer_name)

    def copy(self, candidate: Any) -> None:
        """Put CANDIDATE into the kill ring."""
        from core.utils import eval_in_emacs, message_emacs
        eval_in_emacs("kill-new", candidate)
        message_emacs("Copy: {}".format(candidate))

    def do(self, candidate: Any) -> None:
        """Run the default action of CANDIDATE.

        The default is a no-op: a backend that cannot open a candidate
        simply does nothing when the user selects it.
        """
        del candidate

    def parent(self, candidate: Any, from_history: bool = False) -> None:
        """Open the parent of CANDIDATE.

        FROM_HISTORY marks the call as coming from the history backend, which
        hands over a candidate that another backend produced.
        """
        del from_history
        self.do(candidate)

    def clean(self) -> None:
        """Drop what a previous search of this backend left behind.

        Called when the user leaves the menu; the default only makes sure no
        external command is still running.
        """
        self.kill_sub_process()

    # -- external commands -------------------------------------------------

    def get_process_result(self, command_list: List[str], cwd: Optional[str] = None) -> List[str]:
        """Run COMMAND_LIST in CWD and return its output, one line each.

        The previous command of this backend is killed first, so that two
        searches of the same backend cannot both read the same pipe.  A
        command that fails returns whatever it printed before it died, which
        keeps a search from ending with an empty menu.
        """
        self.kill_sub_process()

        self.sub_process = subprocess.Popen(
            command_list, cwd=cwd,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8")

        results: List[str] = []
        try:
            outs, _errs = self.sub_process.communicate()
            results = [line.strip() for line in outs.splitlines()]
        except Exception:  # pylint: disable=broad-except
            import traceback
            traceback.print_exc()
            self.kill_sub_process()

        return results

    def kill_sub_process(self) -> None:
        """Kill the external command of this backend, if one is running."""
        if self.sub_process is not None:
            try:
                self.sub_process.kill()
            except Exception:  # pylint: disable=broad-except
                pass

            self.sub_process = None


