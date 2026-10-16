#! /usr/bin/env python
# -*- coding: utf-8 -*-

"""Text found by ripgrep under the project of the start buffer.

The matches are read as ripgrep JSON, so the menu can highlight the
matched bytes inside the line.
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
import subprocess

from core.backend import SearchBackend, register_backend
from core.utils import eval_in_emacs, get_project_path, message_emacs, parse_rg_line


@register_backend
class SearchGrepFile(SearchBackend):
    """Text found by ripgrep under the project of the start buffer.

    ripgrep is asked for JSON, so the menu can highlight the bytes that
    matched inside the line.  The answer is sent as soon as `row_number'
    matches have arrived, which is what makes the menu fill in while a
    large project is still being searched.
    """

    NAME = "Grep File"

    def __init__(self):
        """Build a backend that reports its matches in batches."""
        super().__init__()
        self.row_number = 100
        self.search_path = ""

    def init_dir(self, search_dir: str) -> None:
        """Remember the project root that the search starts from."""
        self.search_path = get_project_path(search_dir)

    def search_items(self, prefix: str, ticker: int) -> None:
        """Run ripgrep for PREFIX and send the matches it finds.

        The command is killed before a new one is started and again when it
        is done, so that a keyword typed quickly does not leave a ripgrep
        running per keystroke.
        """
        prefix = prefix.replace("*", "")
        if len(prefix.split()) == 0:
            return

        command_list = ["rg",
                        # Output JSON.
                        "--json",
                        # Smart case.
                        "-S",
                        # Limit column.
                        "--max-columns", "300",
                        # Ignore unnecessary files.
                        "-g", "!node_modules",
                        "-g", "!__pycache__",
                        "-g", "!dist",
                        # Keyword.
                        ".*".join(prefix.split()),
                        # Search directory.
                        os.path.expanduser(self.search_path)]

        self.kill_sub_process()

        self.sub_process = subprocess.Popen(command_list, stdout=subprocess.PIPE,
                                            stderr=subprocess.PIPE, text=True, encoding="utf-8")

        lines = []
        try:
            while True:
                if self.sub_process is None:
                    break

                line = self.sub_process.stdout.readline()  # type: ignore[union-attr]

                if not line:
                    break

                lines.append(line.strip())

                if len(lines) == self.row_number:
                    self.parse_lines(lines, prefix, ticker)
        except Exception:  # pylint: disable=broad-except
            import traceback
            traceback.print_exc()
        finally:
            self.kill_sub_process()

        self.parse_lines(lines, prefix, ticker)

    def parse_lines(self, lines, prefix, ticker):
        """Turn ripgrep JSON LINES into candidates and send them.

        A line that is longer than the menu can show is cut to its first
        match, because the rest of it is the part the user is not looking
        for anyway.
        """
        candidates = []
        for line in lines:
            result = parse_rg_line(line, self.search_path)
            if result is not None:
                if len(result["text"]) < 1000:
                    candidates.append(result)
                else:
                    candidates.append({"text": result["text"][:1000], "matches": [result["matches"][0]]})

        self.send_candidates(candidates, prefix, ticker)

    def do(self, candidate):
        """Visit the match CANDIDATE names and flash its line."""
        candidate_infos = candidate.split(":")
        eval_in_emacs("blink-search-grep-file-do",
                      os.path.join(self.search_path, candidate_infos[0]),
                      int(candidate_infos[1]),
                      int(candidate_infos[2]))

    def select(self, candidate, start_buffer_name):
        """Preview the match CANDIDATE names in the preview window.

        START-BUFFER-NAME is accepted for the signature of the base class.
        """
        del start_buffer_name
        candidate_infos = candidate["text"].split(":")
        eval_in_emacs("blink-search-grep-file-preview",
                      os.path.join(self.search_path, candidate_infos[0]),
                      int(candidate_infos[1]),
                      int(candidate_infos[2]))

    def copy(self, candidate):
        """Put the matched text of CANDIDATE into the kill ring."""
        candidate_text = candidate.split(":")[-1]
        eval_in_emacs("kill-new", candidate_text)
        message_emacs("Copy: {}".format(candidate_text))

    def parent(self, candidate, from_history=False):
        """Open the directory that holds the file of CANDIDATE.

        FROM-HISTORY is accepted for the signature of the base class: the
        recorded candidate is relative to the project either way.
        """
        del from_history
        candidate_infos = candidate.split(":")
        eval_in_emacs("blink-search-open-file",
                      os.path.dirname(os.path.join(self.search_path, candidate_infos[0])))

    def clean(self):
        """Kill ripgrep and drop the buffers its previews opened."""
        self.kill_sub_process()
        eval_in_emacs("blink-search-grep-file-clean")
