#! /usr/bin/env python
# -*- coding: utf-8 -*-

"""The browsing history of the EAF browser.

EAF keeps its history in a text file next to its configuration; each
line is a url and a title separated by a marker character.  Selecting a
candidate opens the url again, and its parent action opens the host.
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
from urllib.parse import urlparse

from core.backend import SearchBackend, register_backend
from core.utils import eval_in_emacs, get_emacs_var


@register_backend
class SearchEAFBrowserHistory(SearchBackend):
    """The browsing history of the EAF browser.

    EAF writes one line per visit, holding the url and the title separated
    by a marker character; a candidate shows both, so a user can search for
    a page by its title as well as by its address.
    """

    NAME = "EAF Browser"

    def search_match(self, prefix):
        """Return the history entries whose url or title matches PREFIX."""
        prefix = prefix.replace("*", "")
        eaf_config_path = get_emacs_var("eaf-config-location")
        if type(eaf_config_path) is str and eaf_config_path != "":
            eaf_browser_history_path = os.path.join(eaf_config_path, "browser", "history", "log.txt")
            if os.path.exists(eaf_browser_history_path):
                with open(eaf_browser_history_path, encoding="utf-8", errors="ignore") as f:
                    histories = f.read().splitlines()

                match_histories = []
                prefix_regexp = re.compile(".*" + ".*".join(prefix.split()))
                for history in histories:
                    history_infos = history.split("ᛡ")[0].split("ᛝ")
                    if prefix_regexp.match(history_infos[0].lower()) or prefix_regexp.match(history_infos[1].lower()):
                        match_histories.append(" ".join(history_infos))

                return match_histories

        return []

    def do(self, candidate):
        """Open the url of CANDIDATE in the EAF browser."""
        eval_in_emacs("eaf-open-browser", candidate.split()[-1])

    def parent(self, candidate, from_history=False):
        """Open the host the url of CANDIDATE belongs to.

        A github url goes to the repository root rather than to the host,
        because that is what a user means by the parent of a github page.
        FROM-HISTORY is accepted for the signature of the base class.
        """
        del from_history
        url = candidate.split()[-1]
        host = urlparse(url).hostname
        if host == "github.com":
            parent_url = "/".join(url.split("/")[2:5])
        else:
            parent_url = host
        eval_in_emacs("eaf-open-browser", parent_url)
