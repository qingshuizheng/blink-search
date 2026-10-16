#! /usr/bin/env python
# -*- coding: utf-8 -*-

"""The favourite directories of the user.

Every entry of `blink-search-common-directory' is shown as
"ALIAS NAME", and selecting one opens the file or directory it points
at; continuing the search from an entry searches inside it.
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
from core.utils import eval_in_emacs, get_emacs_var


@register_backend
class SearchCommonDirectory(SearchBackend):
    """The favourite directories the user configured.

    `blink-search-common-directory' pairs a short alias with a path; every
    entry of the directory is offered as "ALIAS NAME", so a candidate says
    which alias it came from.
    """

    NAME = "Common Directory"

    def search_match(self, prefix):
        """Return the entries of every common directory that match PREFIX.

        The alias and the entry name are matched in lower case, so that a
        user does not have to remember how a directory is spelled.  The
        keyword itself is lowered first, because the words of a keyword have
        to appear in order and the candidate they are compared against is
        already lower case.
        """
        prefix = prefix.replace("*", "").lower()
        prefix_regexp = re.compile(".*" + ".*".join(prefix.split()))

        common_directory = get_emacs_var("blink-search-common-directory")

        if type(common_directory) is list and len(common_directory) > 0:
            results = []

            for directory_info in common_directory:
                alias = directory_info[0]
                directory = os.path.expanduser(directory_info[1])

                for path in os.listdir(directory):
                    if self.is_match(prefix, prefix_regexp, "{} {}".format(alias.lower(), path.lower())):
                        results.append("{} {}".format(alias, path))

            return sorted(results)
        else:
            return []

    def get_candiate_dir(self, candidate):
        """Return the path CANDIDATE names, or None when it names none.

        The first word of a candidate is the alias it belongs to; a
        candidate whose alias is not configured any more returns None
        instead of a path that does not exist.
        """
        prefix = candidate.split()[0]
        common_directory = get_emacs_var("blink-search-common-directory")
        if type(common_directory) is list:
            for directory_info in common_directory:
                alias = directory_info[0]
                directory = os.path.expanduser(directory_info[1])

                if prefix == alias:
                    return os.path.join(directory, candidate.replace(prefix, "").strip())

        return None

    def do(self, candidate):
        """Open the file or directory CANDIDATE stands for."""
        candidate_dir = self.get_candiate_dir(candidate)
        if candidate_dir is not None:
            eval_in_emacs("blink-search-open-file", candidate_dir)

    def parent(self, candidate, from_history=False):
        """Open the directory that holds the entry CANDIDATE stands for.

        FROM-HISTORY is accepted for the signature of the base class.
        """
        del from_history
        candidate_dir = self.get_candiate_dir(candidate)
        if candidate_dir is not None:
            eval_in_emacs("blink-search-open-file", os.path.dirname(candidate_dir))

    def continue_search(self, candidate):
        """Search again inside the directory CANDIDATE stands for."""
        candidate_dir = self.get_candiate_dir(candidate)
        if candidate_dir is not None:
            eval_in_emacs("blink-search-continue-search", candidate_dir)
