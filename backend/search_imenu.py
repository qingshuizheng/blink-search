#! /usr/bin/env python
# -*- coding: utf-8 -*-

"""The imenu index of the buffer the search started from.

Emacs pushes the index as (name, position) pairs; the backend keeps the
positions so that selecting a candidate can jump to it.
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


import re

from core.backend import SearchBackend, register_backend
from core.utils import eval_in_emacs


@register_backend
class SearchIMenu(SearchBackend):
    """The imenu index of the buffer the search started from."""

    NAME = "IMenu"

    def __init__(self):
        """Build an index backend with an empty name to position map."""
        super().__init__()
        self.item_dict = {}

    def update(self, items):
        """Replace the index with ITEMS, a list of (NAME, POSITION) pairs.

        The names are the candidates and the positions are kept aside, so
        that selecting a candidate can hand the position back to Emacs.
        """
        self.items = items
        self.item_dict = {}
        for item in items:
            self.item_dict[str(item[0])] = item[1]

    def search_match(self, prefix: str):
        """Return the names of the items whose name matches PREFIX."""
        prefix_regexp = re.compile(".*" + ".*".join(prefix.replace("*", "").split()), re.IGNORECASE)
        return list(filter(lambda symbol: self.is_match(prefix, prefix_regexp, symbol), self.item_dict.keys()))

    def do(self, candidate):
        """Jump to the position of CANDIDATE."""
        if candidate in self.item_dict:
            eval_in_emacs("blink-search-imenu-do", self.item_dict[candidate])
