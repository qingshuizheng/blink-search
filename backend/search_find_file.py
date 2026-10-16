#! /usr/bin/env python
# -*- coding: utf-8 -*-

"""Files found by fd under the project of the start buffer.

A keyword that starts a search with an empty prefix lists the files of
the directory itself, which is what makes the backend useful as a file
browser.
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
import shutil

from core.backend import SearchBackend, register_backend
from core.utils import eval_in_emacs, get_project_path, message_emacs


@register_backend
class SearchFindFile(SearchBackend):
    """Files found by fd under the project of the start buffer.

    An empty prefix lists the entries of the directory the search started
    from, which makes the backend usable as a small file browser; a keyword
    is handed to fd with the words of the keyword joined by ".*", so that
    the words match in order.
    """

    NAME = "Find File"

    def init_dir(self, search_dir: str) -> None:
        """Remember the directory the search starts from.

        SEARCH-DIR is kept as it is for the empty-prefix listing, and its
        project root is used as the directory fd searches in.
        """
        self.search_dir = search_dir
        self.search_path = get_project_path(search_dir)

    def search_match(self, prefix):
        """Return the paths of the files under the project that match PREFIX."""
        prefix = prefix.replace("*", "")
        if len(prefix.split()) > 0:
            if shutil.which("fd"):
                command_list = ["fd", "--regex", ".*".join(prefix.split()), "--full-path",
                                "--search-path", self.search_path]
            elif shutil.which("fdfind"):
                command_list = ["fdfind", ".*".join(prefix.split()), "--full-path",
                                "--search-path", self.search_path]
            else:
                return []
            results = self.get_process_result(command_list)

            return list(map(lambda p: os.path.relpath(p, self.search_path), results))
        else:
            return os.listdir(self.search_dir)

    def do(self, candidate):
        """Open the file CANDIDATE names inside the project."""
        eval_in_emacs("blink-search-open-file", os.path.join(self.search_path, candidate))

    def record_name(self, candidate):
        """Return the absolute path the history should record for CANDIDATE."""
        return os.path.join(self.search_path, candidate)

    def copy(self, candidate):
        """Put the absolute path of CANDIDATE into the kill ring."""
        path = os.path.join(self.search_path, candidate)
        eval_in_emacs("kill-new", path)
        message_emacs("Copy: {}".format(path))

    def parent(self, candidate, from_history=False):
        """Open the directory that holds CANDIDATE.

        FROM-HISTORY marks a candidate that the history backend recorded as
        an absolute path, which must not be joined to the project again.
        """
        if from_history:
            eval_in_emacs("blink-search-open-file", os.path.dirname(candidate))
        else:
            eval_in_emacs("blink-search-open-file", os.path.dirname(os.path.join(self.search_path, candidate)))

    def continue_search(self, candidate):
        """Search again inside CANDIDATE, or inside the directory that holds it."""
        candidate_path = os.path.join(self.search_path, candidate)
        if os.path.isdir(candidate_path):
            continue_path = candidate_path
        else:
            continue_path = os.path.dirname(candidate_path)

        eval_in_emacs("blink-search-continue-search", continue_path)
