
"""Text found by rga inside the pdf files below a set of directories.

rga reports the page of a match as part of the line, so the backend
strips that prefix again and keeps the page and the matched text for
the Elisp half to jump to.
"""

import os
import re
import subprocess

from core.backend import SearchBackend, register_backend
from core.utils import eval_in_emacs, get_emacs_var, parse_rg_line

#: rga reports the page of a match inside the line it prints, in front of the
#: text of the match itself; the backend takes it off again and keeps the
#: page aside for the Elisp half to jump to.
RGA_PAGE_PREFIX = re.compile('None:.*?: Page ')


@register_backend
class SearchGrepPDF(SearchBackend):
    """Text found by rga inside the pdf files below a set of directories.

    The directories come from `blink-search-grep-pdf-search-paths' when it
    is set, and from the directory the search started in otherwise.  More
    than one directory is supported by marking the directory a match came
    from with a "$Dn" prefix, which is replaced by the real path when the
    user opens the match.
    """

    NAME = "Grep PDF"

    def __init__(self):
        """Build a backend whose search directories are not known yet."""
        super().__init__()
        self.row_number = 100
        self.match_text = None
        self.search_paths = []

    def init_dir(self, search_dir: str) -> None:
        """Remember the directories the search runs over.

        SEARCH-DIR is used only when `blink-search-grep-pdf-search-paths'
        is empty, so that a user who configured the option never pays for
        an rga run over the whole project.
        """
        self.search_paths = get_emacs_var("blink-search-grep-pdf-search-paths")
        self.search_paths = self.search_paths if self.search_paths else search_dir
        if type(self.search_paths) is str:
            self.search_paths = [self.search_paths]

    def search_items(self, prefix: str, ticker: int) -> None:
        """Run rga for PREFIX over the configured directories."""
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

        The page prefix is stripped and the byte offsets of the matches are
        moved back by its length, and the matched text is remembered next to
        the candidate, because that is what the pdf viewer has to highlight.
        """
        candidates = []
        for line in lines:
            if len(self.search_paths) > 1:
                result = parse_rg_line(line, '/')
            else:
                result = parse_rg_line(line, self.search_paths[0])

            if result is not None:
                text = RGA_PAGE_PREFIX.sub('', result['text'])
                remove_len = len(result['text']) - len(text)
                result['text'] = text

                if len(self.search_paths) > 1:
                    for index, path in enumerate(self.search_paths):
                        if path[1:] in result['text']:
                            text = result['text'].replace(path[1:], f'$D{index}')
                            remove_len += len(result['text']) - len(text)
                            result['text'] = text
                            break

                for match in result['matches']:
                    match[0] -= remove_len
                    match[1] -= remove_len

            if result is not None and '.pdf' in result['text'].split(':')[0]:
                candidates.append(result)

        for candidate in candidates:
            self.save_match_text(candidate, prefix)

        self.send_candidates(candidates, prefix, ticker)

    @staticmethod
    def save_match_text(candidate, prefix):
        """Store the matched text of CANDIDATE under its match-text key.

        The stored form is what the pdf viewer highlights; a candidate whose
        offsets do not decode falls back to the text of the line, and one
        without any match falls back to the keyword.
        """
        text = candidate["text"]

        if len(candidate["matches"]) > 0:
            match = candidate["matches"][0]
            try:
                candidate['match_text'] = text.encode()[match[0]:match[1]].decode()
            except UnicodeDecodeError:
                candidate['match_text'] = text[match[0]:match[1]]
        else:
            candidate['match_text'] = prefix

    def get_real_path(self, file):
        """Return the path of FILE with its "$Dn" directory mark expanded."""
        if len(self.search_paths) == 1:
            return os.path.join(self.search_paths[0], file)

        for index, path in enumerate(self.search_paths):
            path_mark = f'$D{index}'
            if path_mark in file:
                return file.replace(path_mark, path)
        return file

    def do(self, candidate):
        """Open the page of CANDIDATE and highlight the matched text."""
        candidate_infos = candidate.split(":")
        eval_in_emacs("blink-search-grep-pdf-do",
                      self.get_real_path(candidate_infos[0]),
                      int(candidate_infos[1]),
                      self.match_text)

    def select(self, candidate, start_buffer_name):
        """Preview CANDIDATE in the pdf viewer.

        START-BUFFER-NAME is accepted for the signature of the base class.
        """
        del start_buffer_name
        candidate_infos = candidate["text"].split(":")
        self.match_text = candidate['match_text']
        eval_in_emacs("blink-search-grep-pdf-preview",
                      self.get_real_path(candidate_infos[0]),
                      int(candidate_infos[1]),
                      candidate['match_text'])

    def clean(self):
        """Kill rga and cancel the pending preview."""
        self.kill_sub_process()
        eval_in_emacs("blink-search-grep-pdf-clean")
