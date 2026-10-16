#!/usr/bin/env python3
"""Tests for the helpers that carry data between the two halves.

`eval_in_emacs' builds a Lisp form that Emacs `eval's, so every argument has
to survive that evaluation.  A candidate list that arrives as a list of
keywords instead, or that Emacs tries to call as a function, is a menu that
stays empty with no error anywhere -- which is exactly what these tests are
here to stop from coming back.

The forms this module checks are also checked against a real Emacs reader in
the ERT suite; these tests keep the Python side honest on its own.

Run with:
    uv run --frozen python -m unittest test.test_utils
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sexpdata  # noqa: E402

from core.utils import handle_arg_types  # noqa: E402


def form(method, *args) -> str:
    """Build the Lisp form `eval_in_emacs' would send for METHOD and ARGS."""
    return sexpdata.dumps([sexpdata.Symbol(method)] + [handle_arg_types(arg) for arg in args])


class ArgumentEncodingTest(unittest.TestCase):
    """What each kind of argument turns into on the wire."""

    def test_a_string_is_a_string(self):
        """A keyword reaches Emacs as a string, not as a symbol."""
        self.assertEqual(form("f", "blink"), '(f "blink")')

    def test_a_number_is_a_number(self):
        """A row count reaches Emacs as a number."""
        self.assertEqual(form("f", 10), "(f 10)")

    def test_a_candidate_list_is_quoted(self):
        """The rows are data: Emacs must not try to call them.

        The first element of a row is the keyword `:backend', so an unquoted
        list would be evaluated as `(:backend "Find File" ...)' and fail with
        `invalid-function'.
        """
        rows = [{"backend": "Find File", "candidate": "README.md"}]
        self.assertEqual(form("f", rows), '(f \'((:backend "Find File" :candidate "README.md")))')

    def test_a_backend_list_is_quoted(self):
        """The list of backend names is data as well."""
        self.assertEqual(form("f", ["Elisp Symbol", "Find File"]),
                         '(f \'("Elisp Symbol" "Find File"))')

    def test_an_empty_list_is_quoted(self):
        """An empty list is still a list, not nil."""
        self.assertEqual(form("f", []), "(f '())")

    def test_a_quoted_string_names_a_function(self):
        """A leading quote asks Emacs for the symbol, not the string."""
        self.assertEqual(form("f", "'kill-new"), "(f kill-new)")

    def test_a_full_update_form_reads_back_as_data(self):
        """The update form the menu is built from parses to the same data.

        This is the check the whole module exists for: reading the form back
        has to give a list of plists, because that is what
        `blink-search-render' walks.
        """
        rows = [{"backend": "Find File", "candidate": "README.md"},
                {"backend": "Elisp Symbol",
                 "candidate": {"text": "blink-search-mode", "matches": [[3, 9]]}}]
        text = form("blink-search-update-items", rows, 0, ["README.md"], 1, "Find File", 1, 2, 3)

        parsed = sexpdata.loads(text)
        self.assertEqual(parsed[0], sexpdata.Symbol("blink-search-update-items"))
        # `Quoted' reads the `\'' back as the quote form, so indexing it gives
        # the data Emacs would see after evaluating that quote.
        quoted_rows = parsed[1]
        self.assertIsInstance(quoted_rows, sexpdata.Quoted)
        rows_as_data = quoted_rows[0]
        self.assertEqual(len(rows_as_data), len(rows))
        self.assertEqual(rows_as_data[0][0], sexpdata.Symbol(":backend"))
        self.assertEqual(rows_as_data[0][1], "Find File")
        self.assertEqual(rows_as_data[0][2], sexpdata.Symbol(":candidate"))

    def test_a_plain_string_argument_stays_unquoted(self):
        """A string argument is read back as a string, not as a form."""
        parsed = sexpdata.loads(form("f", "a value"))
        self.assertEqual(parsed[1], "a value")


if __name__ == "__main__":
    unittest.main()
