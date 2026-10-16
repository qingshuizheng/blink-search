
"""Text found by rga inside the pdf file of the start buffer.

The backend searches exactly one file, so a match can be attributed to
a page and the Elisp half can jump straight to it.
"""

import os
import re
import subprocess

from core.backend import SearchBackend, register_backend
from core.utils import eval_in_emacs, get_emacs_var, parse_rg_line

#: See core.backend.SearchGrepPDF: rga puts the page of a match in front of
#: the text of the match, and the backend takes it off again.
RGA_PAGE_PREFIX = re.compile('None:.*?: Page ')


@register_backend
class SearchPDF(SearchBackend):
    """Text found by rga inside the pdf file of the start buffer.

    Only one file is searched, so a match can be attributed to a page and
    the Elisp half can jump straight to it.  The backend joins the search
    only when the buffer the search started from is a pdf file and rga is
    installed.
    """

    NAME = "PDF"

    def __init__(self):
        """Build a backend whose file is not known yet."""
        super().__init__()
        self.row_number = 100
        self.match_text = None
        self.search_paths = []

    def init_dir(self, search_dir: str) -> None:
        """Remember the pdf file the search starts from.

        SEARCH-DIR is accepted for the signature of the base class; the file
        is taken from the Emacs variable that holds it.
        """
        del search_dir
        self.search_paths = [get_emacs_var("blink-search-start-path-name")]

    def search_items(self, prefix: str, ticker: int) -> None:
        """Run rga for PREFIX over the pdf file of the start buffer."""
        prefix = prefix.replace("*", "")
        self.match_text = prefix

        if len(prefix.split()) == 0:
            return

        command_list = ["rga",
                        # Output JSON.
                        "--json",
                        # Smart case.
                        "-S",
                        # Limit column.
                        "--max-columns", "300",
                        # Keyword.
                        ".*".join(prefix.split())]
        for search_path in self.search_paths:
            command_list.append(os.path.expanduser(search_path))

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
        """Turn rga JSON LINES into candidates and send them.

        See `SearchGrepPDF.parse_lines': the page prefix is stripped, the
        match offsets are moved back by its length, and the matched text is
        remembered for the viewer.
        """
        candidates = []
        for line in lines:
            result = parse_rg_line(line)

            if result is not None:
                text = RGA_PAGE_PREFIX.sub('', result['text'])
                remove_len = len(result['text']) - len(text)
                result['text'] = text

                for match in result['matches']:
                    match[0] -= remove_len
                    match[1] -= remove_len

                candidates.append(result)

        for candidate in candidates:
            self.save_match_text(candidate, prefix)

        self.send_candidates(candidates, prefix, ticker)

    @staticmethod
    def save_match_text(candidate, prefix):
        """Store the matched text of CANDIDATE under its match-text key."""
        text = candidate["text"]

        if len(candidate["matches"]) > 0:
            match = candidate["matches"][0]
            try:
                candidate['match_text'] = text.encode()[match[0]:match[1]].decode()
            except UnicodeDecodeError:
                candidate['match_text'] = text[match[0]:match[1]]
        else:
            candidate['match_text'] = prefix

    def do(self, candidate):
        """Open the page of CANDIDATE and highlight the matched text."""
        candidate_infos = candidate.split(":")
        eval_in_emacs("blink-search-pdf-do",
                      self.search_paths[0],
                      int(candidate_infos[0]),
                      self.match_text)

    def select(self, candidate, start_buffer_name):
        """Preview CANDIDATE in the pdf viewer.

        START-BUFFER-NAME is accepted for the signature of the base class.
        """
        del start_buffer_name
        candidate_infos = candidate["text"].split(":")
        self.match_text = candidate['match_text']
        eval_in_emacs("blink-search-pdf-preview",
                      self.search_paths[0],
                      int(candidate_infos[0]),
                      candidate['match_text'])

    def clean(self):
        """Kill rga and cancel the pending preview."""
        self.kill_sub_process()
        eval_in_emacs("blink-search-pdf-clean")
