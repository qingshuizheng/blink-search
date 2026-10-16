#! /usr/bin/env python
# -*- coding: utf-8 -*-

"""Google suggestions, and plain urls, opened in a browser.

A keyword that is already a url is offered as it stands; anything else
is sent to the Google suggestion endpoint and the answers are offered
next to it.
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


import json
import re

import requests

from core.backend import SearchBackend, register_backend
from core.utils import eval_in_emacs


@register_backend
class SearchGoogleSuggest(SearchBackend):
    """Google suggestions, and urls, opened in a browser.

    A keyword that is already a url is offered as it stands and opened
    directly; anything else is sent to the Google suggestion endpoint and
    the answers are offered next to a "search for it" entry.
    """

    NAME = "Google Suggest"

    def is_valid_url(self, url: str):
        """Return whether URL looks like something a browser can open."""
        if len(url.split()) > 1:
            return False

        pattern = re.compile(
            r'^(?:http|ftp)s?://'  # http:// or https://
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|'  # domain...
            r'localhost|'  # localhost...
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
            r'(?::\d+)?'  # optional port
            r'(?:/?|[/?]\S+)$', re.IGNORECASE)

        return bool(pattern.match(url)) or url.endswith(".html")

    def search_items(self, prefix: str, ticker: int):
        """Offer PREFIX itself, then the suggestions Google answers with.

        The url is sent first, so that a user who pasted an address does not
        have to wait for the network round trip before the menu shows it.
        """
        if self.is_valid_url(prefix):
            self.send_candidates([prefix], prefix, self.search_ticker)

        candidates = self.search_match(prefix)
        self.send_candidates(candidates, prefix, ticker)

    def search_match(self, prefix):
        """Return the suggestions of the Google endpoint for PREFIX.

        A network error leaves only the keyword itself when it is a url, and
        an empty list otherwise: a search may not fail because a suggestion
        service is unreachable.
        """
        if len(prefix.split()) > 0:
            query = prefix.replace(" ", "%20")
            try:
                response = requests.get('http://google.com/complete/search?client=chrome&q={}'.format(query), headers={
                    "User-Agent":
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/70.0.3538.102 Safari/537.36 Edge/18.19582"
                }, timeout=5)

                if self.is_valid_url(prefix) and (not (any(list(filter(lambda schema: prefix.startswith(schema),
                                                                      ["http://", "https://", "ftp://", "ftps://"]))))):
                    prefix = "http://" + prefix

                return [prefix] + json.loads(response.text)[1]
            except Exception:  # pylint: disable=broad-except
                if self.is_valid_url(prefix):
                    return [prefix]
                return []
        else:
            return []

    def do(self, candidate):
        """Open CANDIDATE in the browser `blink-search-browser-function' names.

        A keyword that is not a url becomes a Google search for it.
        """
        if self.is_valid_url(candidate):
            eval_in_emacs("blink-search-open-browser", candidate)
        else:
            eval_in_emacs("blink-search-open-browser",
                          "http://www.google.com/search?q={}".format(candidate.replace(" ", "%20")))
