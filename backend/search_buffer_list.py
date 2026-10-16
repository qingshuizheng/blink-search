#! /usr/bin/env python
# -*- coding: utf-8 -*-

"""The open buffers as a source of candidates.

Emacs pushes the buffer names in tab order, and the backend only filters
them.  A prefix that starts or ends with a star keeps only the hidden
buffers or only the visible ones, which is how a user reaches a buffer
that the tab bar does not show.
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


import functools
import re

from core.backend import SearchBackend, register_backend
from core.utils import eval_in_emacs


@register_backend
class SearchBufferList(SearchBackend):
    """The open buffers, in the order the tab bar shows them in."""

    NAME = "Buffer List"

    def sort_buffer(self, a, b):
        """Order two buffer names A and B for the menu.

        A visible buffer comes before a hidden one, which is the order the
        user reads the tab bar in; two buffers of the same kind are ordered
        by name.
        """
        if (not a.startswith(" *")) and b.startswith(" *"):
            return -1
        elif a.startswith(" *") and (not b.startswith(" *")):
            return 1
        else:
            return a < b

    def update(self, items):
        """Replace the buffer pool with ITEMS, in tab order."""
        self.items = sorted(items, key=functools.cmp_to_key(self.sort_buffer))

    def update_sort_buffers(self, items):
        """Replace the buffer pool with ITEMS, keeping their given order.

        sort-tab knows the order the tabs are in, so the list it pushes is
        used as it stands instead of being sorted here.
        """
        self.items = list(dict.fromkeys(items))

    def search_match(self, prefix: str):
        """Return the buffer names that match PREFIX.

        A prefix that starts with a star keeps only the buffers whose name
        starts with a space, which is how a hidden buffer is reached; a
        prefix that ends with one keeps only those whose name does.
        """
        prefix_regexp = re.compile(".*" + ".*".join(prefix.replace("*", "").split()), re.IGNORECASE)
        match_items = list(filter(lambda symbol: self.is_match(prefix, prefix_regexp, symbol), self.items))

        if prefix.startswith("*"):
            return list(filter(lambda i: i.startswith("*"), match_items))
        elif prefix.startswith(" *"):
            return list(filter(lambda i: i.startswith(" *"), match_items))
        elif prefix.endswith("*"):
            return list(filter(lambda i: i.endswith("*"), match_items))
        else:
            return match_items

    def do(self, candidate):
        """Switch to the buffer named CANDIDATE."""
        eval_in_emacs("switch-to-buffer", candidate)
