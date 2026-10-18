#! /usr/bin/env python
# -*- coding: utf-8 -*-


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

from core.utils import eval_in_emacs
from core.backend import SearchBackend, register_backend


@register_backend
class SearchRecentFile(SearchBackend):
    """The files of `recentf-list'.

    Emacs pushes the list; the backend matches names and opens the file a
    candidate stands for.
    """

    NAME = "Recent File"

    def do(self, candidate):
        """Visit the file CANDIDATE names."""
        eval_in_emacs("find-file", candidate)

    def parent(self, candidate, from_history=False):
        """Open the directory that holds CANDIDATE.

        FROM-HISTORY is accepted for the signature of the base class; a
        recent file candidate is an absolute path either way.
        """
        del from_history
        eval_in_emacs("blink-search-open-file", os.path.dirname(candidate))
