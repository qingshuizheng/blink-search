#!/usr/bin/env python3
"""The state and the navigation of one blink-search session.

A search session is what the menu shows: the candidates of every backend,
which of them is selected, and which slice of them fits into the window the
Elisp half gave us.  All of it lives in this class as data, and every method
that changes it is either an answer to a new keystroke or a movement of the
selection.

The distinction that matters is between the whole answer and the window on it:

* `_candidate_items' and `_backend_items' are the whole answer of the last
  search.
* `_render_candidate_items' and `_render_backend_items' are the rows the menu
  is showing right now, a slice of the above.
* `_candidate_index' and `_backend_index' are the selected row inside the
  window, `_candidate_offset' and `_backend_offset' the row the window starts
  at.

Elisp owns the windows; this class only decides which rows go in them, and it
tells Elisp about the result with `blink-search-update-items'.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.protocol import MESSAGE_UPDATE_BACKEND_ITEMS
from core.utils import eval_in_emacs

#: How many candidates of one backend the menu shows at least, when several
#: backends have something to offer and the window is too small for all of
#: them.  A backend that is squeezed below this number shows nothing at all,
#: which is worse than showing a few rows of it.
MIN_CANDIDATES_PER_BACKEND = 5


class SearchSession:
    """The candidates of one search, and the selection inside them."""

    def __init__(self, row_number: int = 0) -> None:
        """Build an empty session that renders ROW-NUMBER rows.

        ROW-NUMBER is how many candidate lines the window holds; it is set
        again by every `search'.
        """
        self.row_number = row_number
        self.keyword = ""

        #: How many rows the windows hold.  It is `row_number' once an answer
        #: has arrived, and it is what the scrolling arithmetic uses: the
        #: whole answer can be longer than the window (the number of
        #: candidates the backends offered is not a multiple of the window
        #: size), so a movement that used the length of the shown slice
        #: would stop before the end of it.
        self.window_size = row_number

        #: Called with (BACKEND-NAME, CANDIDATE) when a movement inside one
        #: backend should show the new candidate.  The session does not own
        #: the backends, so whoever does fills this in.
        self.preview_callback = None

        self._items_by_backend: Dict[str, List[Any]] = {}
        self._candidate_items: List[dict] = []
        self._backend_items: List[Any] = []
        self._backend_list: List[str] = []

        self._candidate_index = 0
        self._candidate_offset = 0
        self._backend_index = 0
        self._backend_offset = 0

        self._render_candidate_items: List[dict] = []
        self._render_backend_items: List[Any] = []

    # -- what the last search found ---------------------------------------

    def set_backend_list(self, backend_list: List[str]) -> None:
        """Remember the backends the current search runs over."""
        self._backend_list = list(backend_list)

    def backend_list(self) -> List[str]:
        """Return the backends the current search runs over."""
        return list(self._backend_list)

    def backend_candidate_number(self, backend_name: str) -> int:
        """Return how many candidates BACKEND-NAME offered, or zero.

        A backend that has not answered yet counts as zero, which is what
        keeps the first render of a search from waiting for the slowest
        backend.
        """
        return len(self._items_by_backend.get(backend_name) or [])

    # -- answers from the backends ----------------------------------------

    def handle_message(self, message: dict) -> None:
        """Take one message from a backend.

        A message that carries a new candidate list rebuilds the menu; any
        other message is ignored, so that a backend may put more message
        kinds on the queue later without breaking the session.
        """
        if message["name"] == MESSAGE_UPDATE_BACKEND_ITEMS:
            self._handle_backend_items(message["backend"], message["keyword"], message["items"])

    def _handle_backend_items(self, backend_name: str, keyword: str, items: List[Any]) -> None:
        """Merge the ITEMS BACKEND-NAME found for KEYWORD into the menu."""
        self._items_by_backend[backend_name] = items

        self._candidate_items = []
        self._backend_items = []

        candidate_counter = sum(self.backend_candidate_number(name) for name in self._backend_list)

        for name in self._backend_list:
            candidates = self._items_by_backend.get(name)
            if not candidates:
                continue

            if len(self._backend_list) > 1:
                if candidate_counter < self.row_number:
                    # Show all candidates if total number is less than row number.
                    candidate_show_number = len(candidates)
                else:
                    # Show as many candidates as possible.
                    candidate_show_number = max(MIN_CANDIDATES_PER_BACKEND,
                                                int(self.row_number / candidate_counter))
            else:
                # Show all candidates if only have one backend.
                candidate_show_number = len(candidates)

            for candidate in candidates[:min(len(candidates), candidate_show_number)]:
                self._candidate_items.append({
                    "backend": name,
                    "candidate": candidate,
                })

        if len(self._candidate_items) > 0:
            self._backend_items = self._items_by_backend[self._candidate_items[0]["backend"]]
            self.window_size = self.row_number

            if keyword != self.keyword:
                # Move cursor to first candidate when search keyword change.
                self._reset_window()
            else:
                # Don't change candidate offset if search keyword not change.
                self._update_render_candidate_items()
                self._update_render_index_and_offset()
        else:
            # Clean everything if no result found.
            self._backend_items = []
            self._reset_window()
            self._render_backend_items = []

        self.keyword = keyword

        self.render_items()

    def _reset_window(self) -> None:
        """Move the window back to the first candidate."""
        self._render_candidate_items = self._candidate_items[:min(self.window_size, len(self._candidate_items))]
        self._render_backend_items = self._backend_items[:min(self.window_size, len(self._backend_items))]
        self._candidate_offset = 0
        self._candidate_index = 0
        self._backend_offset = 0
        self._backend_index = 0

    # -- telling Elisp what to draw ---------------------------------------

    def render_items(self) -> None:
        """Send the rows the menu should show to the Elisp half."""
        if len(self._candidate_items) > 0:
            selected = self._selected_candidate_item()
            backend_name = selected["backend"]
            candidate_index = self._backend_offset + self._backend_index + 1
        else:
            backend_name = ""
            candidate_index = 0

        eval_in_emacs("blink-search-update-items",
                      self._render_candidate_items, self._candidate_index,
                      self._render_backend_items, self._backend_index,
                      backend_name, candidate_index,
                      len(self._backend_items), len(self._backend_list))

    def _selected_candidate_item(self) -> dict:
        """Return the candidate item the selection is on."""
        return self._candidate_items[self._candidate_offset + self._candidate_index]

    def _selected_backend_candidate(self) -> Any:
        """Return the candidate of the selected backend row."""
        return self._backend_items[self._backend_offset + self._backend_index]

    def selected_backend_name(self) -> Optional[str]:
        """Return the backend the selection is in, or None when empty."""
        if not self._candidate_items:
            return None
        return self._selected_candidate_item()["backend"]

    def selected_candidate(self) -> Optional[Any]:
        """Return the candidate the selection is on, or None when empty."""
        if not self._candidate_items:
            return None
        return self._selected_candidate_item()["candidate"]

    def backend_selected_candidate(self) -> Optional[Any]:
        """Return the candidate of the selected row of the backend window."""
        if not self._backend_items:
            return None
        return self._selected_backend_candidate()

    # -- the window on the answer -----------------------------------------

    def _update_render_index_and_offset(self) -> None:
        """Point the backend window at the selected candidate.

        The two windows are independent: the candidate window holds the rows
        of every backend, the backend window the rows of one backend.  When
        the selection moves in the first one, the second one has to scroll to
        keep showing the selected candidate.
        """
        try:
            candidate = self._selected_candidate_item()
            backend_index = self._backend_items.index(candidate["candidate"])

            if backend_index >= self.window_size:
                self._backend_offset = backend_index - (self.window_size - 1)
                self._backend_index = self.window_size - 1
            else:
                self._backend_offset = 0
                self._backend_index = backend_index

            self._render_backend_items = self._backend_items[
                self._backend_offset:min(self.window_size, len(self._backend_items))]
        except Exception:  # pylint: disable=broad-except
            import traceback
            traceback.print_exc()

            self._backend_offset = 0
            self._backend_index = 0

            self._render_backend_items = self._backend_items[:min(self.window_size, len(self._backend_items))]

    def _update_render_candidate_items(self) -> None:
        """Scroll the candidate window so that the selection stays in it."""
        self._render_candidate_items = self._candidate_items[
            self._candidate_offset:self._candidate_offset + self.window_size]
        self._backend_items = self._items_by_backend[
            self._render_candidate_items[self._candidate_index]["backend"]]

    def _update_render_backend_items(self) -> None:
        """Scroll the backend window."""
        self._render_backend_items = self._backend_items[
            self._backend_offset:self._backend_offset + self.window_size]

    # -- navigation --------------------------------------------------------

    def group_index_list(self) -> List[int]:
        """Return the index where the candidates of a new backend start.

        The menu shows the candidates backend by backend, so every change of
        backend name is where a group starts.
        """
        group_list: List[int] = []
        last_backend_name = ""
        for index, item in enumerate(self._candidate_items):
            backend_name = item["backend"]
            if backend_name != last_backend_name:
                group_list.append(index)
                last_backend_name = backend_name

        return group_list

    def select_next_candidate_item(self) -> None:
        """Move the selection one candidate down.

        The window scrolls when the selection would leave it, and a selection
        that is already on the last candidate stays where it is instead of
        redrawing the same menu.
        """
        need_update = True

        if len(self._candidate_items) > 0:
            if self._candidate_index < min(self.window_size, len(self._candidate_items)) - 1:
                self._candidate_index += 1
                self._update_render_candidate_items()
            elif self._candidate_offset + self._candidate_index == len(self._candidate_items) - 1:
                need_update = False
            else:
                self._candidate_offset += 1
                self._update_render_candidate_items()
        else:
            need_update = False

        if need_update:
            self._update_render_index_and_offset()
            self.render_items()

    def select_prev_candidate_item(self) -> None:
        """Move the selection one candidate up."""
        need_update = True

        if len(self._candidate_items) > 0:
            if self._candidate_index > 0:
                self._candidate_index -= 1
                self._update_render_candidate_items()
            elif self._candidate_offset == 0 and self._candidate_index == 0:
                need_update = False
            else:
                self._candidate_offset -= 1
                self._update_render_candidate_items()
        else:
            need_update = False

        if need_update:
            self._update_render_index_and_offset()
            self.render_items()

    def _move_to_candidate(self, next_index: int) -> None:
        """Put the selection on the candidate NEXT-INDEX of the answer.

        NEXT-INDEX is absolute; the window scrolls as little as it can and
        the selection lands on the row of the window that holds it.
        """
        if next_index >= self._candidate_offset and next_index < self._candidate_offset + self.window_size:
            self._candidate_index = next_index - self._candidate_offset
        else:
            self._candidate_index = 0
            self._candidate_offset = next_index

        self._update_render_candidate_items()
        self._update_render_index_and_offset()
        self.render_items()

    def _move_to_candidate_from_below(self, next_index: int) -> None:
        """Put the selection on NEXT-INDEX, scrolling upwards if needed."""
        if next_index >= self._candidate_offset and next_index < self._candidate_offset + self.window_size:
            self._candidate_index = next_index - self._candidate_offset
        else:
            self._candidate_index = 0
            self._candidate_offset = next_index

        self._update_render_candidate_items()
        self._update_render_index_and_offset()
        self.render_items()

    def select_next_candidate_group(self) -> None:
        """Move the selection to the first candidate of the next backend.

        The target is put on the first row of the window rather than at the
        row it would have had in the old window: a group starts a new part
        of the menu, so the user expects to read it from its first line.
        """
        if len(self._candidate_items) > 0:
            candidate_index = self._candidate_offset + self._candidate_index
            match_list = list(filter(lambda index: candidate_index < index, self.group_index_list()))
            if len(match_list) > 0:
                self._move_to_candidate(match_list[0])

    def select_prev_candidate_group(self) -> None:
        """Move the selection to the first candidate of the previous backend.

        The group is shown from its first row, so the window scrolls up to
        where the group begins instead of stopping one row above the old
        selection.
        """
        if len(self._candidate_items) > 0:
            candidate_index = self._candidate_offset + self._candidate_index
            match_list = list(filter(lambda index: candidate_index > index, self.group_index_list()))
            if len(match_list) > 0:
                self._move_to_candidate_from_below(match_list[-1])

    def select_next_backend_item(self) -> None:
        """Move the selection down inside the candidates of one backend."""
        need_update = True

        if len(self._backend_items) > 0:
            if self._backend_index < min(self.window_size - 1, len(self._backend_items)) - 1:
                self._backend_index += 1
            elif self._backend_offset + self._backend_index == len(self._backend_items) - 1:
                need_update = False
            else:
                self._backend_offset += 1
                self._update_render_backend_items()
        else:
            need_update = False

        if need_update:
            self.render_items()
            self.preview_selected()

    def select_prev_backend_item(self) -> None:
        """Move the selection up inside the candidates of one backend."""
        need_update = True

        if len(self._backend_items) > 0:
            if self._backend_index > 0:
                self._backend_index -= 1
            elif self._backend_offset == 0 and self._backend_index == 0:
                need_update = False
            else:
                self._backend_offset -= 1
                self._update_render_backend_items()
        else:
            need_update = False

        if need_update:
            self.render_items()
            self.preview_selected()

    def preview_selected(self) -> None:
        """Ask the session's owner to preview the selected backend row.

        Moving inside one backend means the user is comparing the candidates
        of that backend, so every move shows the new one.  The session does
        not know how to preview a candidate; the owner set `preview_callback'
        for that.
        """
        if self.preview_callback is None:
            return

        backend_name = self.selected_backend_name()
        candidate = self.backend_selected_candidate()
        if backend_name is None or candidate is None:
            return

        self.preview_callback(backend_name, candidate)
