#! /usr/bin/env python
# -*- coding: utf-8 -*-

"""The elisp symbols of the running Emacs.

Emacs pushes both the symbols of the buffer the search started from and
the global symbols; the backend only sorts and filters them.
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
class SearchElispSymbol(SearchBackend):
    """Every elisp symbol of the running Emacs that a user can look up."""

    NAME = "Elisp Symbol"

    def update(self, items):
        """Replace the symbol pool with ITEMS, shortest first.

        The strings are sorted by length so that the shortest match of a
        keyword is the first candidate: `defun' before `defun-something'.
        """
        self.items = sorted(list(map(str, items)), key=len)

    def do(self, candidate):
        """Describe CANDIDATE, or call it when it is a command."""
        eval_in_emacs("blink-search-elisp-symbol-do", candidate)
