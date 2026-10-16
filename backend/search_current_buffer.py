#! /usr/bin/env python
# -*- coding: utf-8 -*-

"""The content of the buffer the search started from.

The Elisp half hands the text over once, base64 encoded; the backend
writes it to a temporary file and runs ripgrep over that file, so a
search of the current buffer finds the same matches ripgrep would find
in a saved file, without saving it.
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


import base64
import hashlib
import os
import tempfile

from core.backend import SearchBackend, register_backend
from core.utils import eval_in_emacs, message_emacs, parse_rg_line, touch


@register_backend
class SearchCurrentBuffer(SearchBackend):
    """The content of the buffer the search started from.

    Emacs hands the text over once, base64 encoded so that any encoding
    survives the trip.  The text is written to a temporary file and ripgrep
    runs over that file, which is what lets a search of an unsaved buffer
    find the same matches ripgrep would find in a saved one.
    """

    NAME = "Current Buffer"

    def __init__(self):
        """Build a backend without a temporary file yet."""
        super().__init__()
        self.buffer_temp_path = ""
        self.buffer_name = ""

    def init_buffer(self, buffer_name, buffer_content):
        """Write the content of BUFFER-NAME to a temporary file.

        BUFFER-CONTENT is the base64 encoded text of the buffer.  The path
        of the file is derived from the buffer name, so that searching the
        same buffer twice reuses the same file instead of filling the
        temporary directory.
        """
        self.buffer_name = buffer_name
        self.buffer_content = base64.b64decode(buffer_content).decode("utf-8")

        md5 = hashlib.md5()
        md5.update(buffer_name.encode("utf-8"))
        self.buffer_temp_path = os.path.join(tempfile.gettempdir(),
                                             "blink-search-temp-buffer-{}".format(md5.hexdigest()))
        touch(self.buffer_temp_path)
        with open(self.buffer_temp_path, "w", encoding="utf-8", errors="ignore") as f:
            f.write(self.buffer_content)

    def search_match(self, prefix):
        """Return the lines of the temporary file that match PREFIX."""
        prefix = prefix.replace("*", "")
        if len(prefix.split()) > 0 and os.path.exists(self.buffer_temp_path) and len(prefix) > 0:
            lines = self.get_process_result(["rg", "-S", "--json", "--max-columns", "300",
                                             "-g", "!node_modules",
                                             "-g", "!__pycache__",
                                             "-g", "!dist",
                                             ".*".join(prefix.split()),
                                             self.buffer_temp_path])

            results = []
            for line in lines:
                result = parse_rg_line(line)
                if result is not None:
                    if len(result["text"]) < 1000:
                        results.append(result)
                    else:
                        results.append({"text": result["text"][:1000], "matches": [result["matches"][0]]})

            return results
        return []

    def do(self, candidate):
        """Jump to the line of the buffer that CANDIDATE stands for.

        The temporary file is removed afterwards: the buffer is the master
        copy, and the next search writes the file again.
        """
        candidate_infos = candidate.split(":")
        eval_in_emacs("blink-search-current-buffer-do",
                      self.buffer_name,
                      int(candidate_infos[0]),
                      int(candidate_infos[1]))

        os.unlink(self.buffer_temp_path)

    def select(self, candidate, start_buffer_name):
        """Preview CANDIDATE without leaving the search.

        START-BUFFER-NAME is accepted for the signature of the base class;
        the preview always jumps inside the buffer the search started from.
        """
        del start_buffer_name
        candidate_infos = candidate["text"].split(":")
        eval_in_emacs("blink-search-current-buffer-preview",
                      self.buffer_name,
                      int(candidate_infos[0]),
                      int(candidate_infos[1]))

    def copy(self, candidate):
        """Put the text of the matched line into the kill ring."""
        candidate_text = candidate.split(":")[-1]
        eval_in_emacs("kill-new", candidate_text)
        message_emacs("Copy: {}".format(candidate_text))
