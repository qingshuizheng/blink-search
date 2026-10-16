#! /usr/bin/env python
# -*- coding: utf-8 -*-

"""The history of everything the user selected before.

Emacs records a line per action; the backend matches on both the
candidate and the backend it was taken from, so that a repeated search
replays the action of the original backend.
"""


# Copyright (C) 2022 Andy Stewart
#
# Author:     Andy Stewart <lazycat.manatee@gmail.com>
# Maintainer: <lazycat.manatee@gmail.com> <lazycat.manatee@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.


import os
import re

from core.backend import SearchBackend, register_backend
from core.utils import get_emacs_var

#: The character Emacs uses to separate a recorded candidate from the name of
#: the backend it was taken from.
HISTORY_SEPARATOR = "ᛡ"


@register_backend
class SearchHistory(SearchBackend):
    """The history of everything the user selected before.

    Emacs appends one line per action, holding the candidate and the name of
    the backend that produced it.  Selecting a history candidate hands both
    back to that backend, so a repeated search replays the original action
    instead of doing something the history backend guessed.
    """

    NAME = "History"

    def __init__(self):
        """Build a backend that replays through the callbacks the session sets."""
        super().__init__()
        self.candiate_do_callback = None
        self.candiate_parent_callback = None

    def search_match(self, prefix):
        """Return the history entries whose candidate or backend matches PREFIX.

        The two halves are matched in lower case, because the history file is
        written by every backend and a user does not remember the case each
        of them uses.  A file that cannot be read is treated as an empty
        history rather than as a failed search.
        """
        try:
            prefix = prefix.replace("*", "")

            history_path = get_emacs_var("blink-search-history-path")
            if os.path.exists(history_path):
                with open(history_path, encoding="utf-8", errors="ignore") as f:
                    histories = f.read().splitlines()

                match_histories = []
                prefix_regexp = re.compile(".*" + ".*".join(prefix.split()))
                for history in histories:
                    history_infos = history.split(HISTORY_SEPARATOR)
                    if len(history_infos) >= 2:
                        if (prefix_regexp.match(history_infos[0].lower())
                                or prefix_regexp.match(history_infos[1].lower())):
                            match_histories.append("{} [{}]".format(history_infos[0], history_infos[1]))

                return match_histories
        except Exception:  # pylint: disable=broad-except
            import traceback
            traceback.print_exc()
            return []

        return []

    def split_candidate(self, candidate):
        """Return the (CANDIDATE, BACKEND) pair a history line stands for.

        The name of the backend is written between brackets at the end of
        the line, which is what `search_match' builds.
        """
        pattern = r'^(.+)\s+\[([^\[\]]+)\]$'
        return re.search(pattern, candidate)

    def do(self, candidate):
        """Replay the action the recorded backend ran for CANDIDATE."""
        match = self.split_candidate(candidate)
        if self.candiate_do_callback and match:
            self.candiate_do_callback(match.group(2), match.group(1))

    def parent(self, candidate, from_history=False):
        """Replay the parent action of the recorded backend for CANDIDATE.

        FROM-HISTORY is accepted for the signature of the base class.
        """
        del from_history
        match = self.split_candidate(candidate)
        if self.candiate_parent_callback and match:
            self.candiate_parent_callback(match.group(2), match.group(1))
