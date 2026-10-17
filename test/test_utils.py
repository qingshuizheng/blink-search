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

from core.utils import convert_emacs_var, handle_arg_types, to_lisp_list  # noqa: E402


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


class EmacsVariableAnswerTest(unittest.TestCase):
    """The shape Emacs answers `get-emacs-var' with.

    A mistake here does not raise at the point of the mistake: it hands a
    bool to a backend that goes on to treat it as a path, and the search dies
    inside the EPC call with the menu left empty.  That is how the start
    directory reached `os.path.expanduser' as False.
    """

    def test_a_string_answer_stays_a_string(self):
        """An ordinary value is returned as it is."""
        self.assertEqual(convert_emacs_var(["/tmp/project", "nil"]), "/tmp/project")

    def test_a_boolean_answer_becomes_a_bool(self):
        """The flag is what turns t and nil into True and False."""
        self.assertIs(convert_emacs_var([True, "t"]), True)
        self.assertIs(convert_emacs_var([None, "nil"]), None)

    def test_an_empty_answer_is_false(self):
        """python-epc turns an empty list into False, and so does this.

        A variable Emacs cannot find is answered with an empty value; the
        caller has to be able to tell that from a string, which is why it is
        not turned into "" or None.
        """
        self.assertIs(convert_emacs_var([]), False)

    def test_a_truncated_answer_does_not_raise(self):
        """An answer of one element is still a value, not an IndexError."""
        self.assertEqual(convert_emacs_var(["only"]), "only")

    def test_a_list_of_answers_is_converted_in_order(self):
        """`get_emacs_vars' answers align with the names it was asked for."""
        answers = [["/tmp/a", "nil"], [], [True, "t"]]
        self.assertEqual([convert_emacs_var(a) for a in answers], ["/tmp/a", False, True])


class LispListTest(unittest.TestCase):
    """A list has to arrive in Emacs as a list, not as a vector."""

    def test_a_list_is_written_as_a_list(self):
        """`sexpdata' writes a Python list as `[...]', which Emacs reads
        as a vector whose single element is the list, so a method that
        declared a list argument got a list of one element instead.
        """
        self.assertIn("(", form("f", ["a", "b"]))
        self.assertNotIn("[", form("f", ["a", "b"]))
        self.assertEqual(form("f", ["a", "b"]), "(f '(\"a\" \"b\"))")

    def test_a_nested_list_is_a_list_at_every_depth(self):
        """The rows of the menu are a list of lists."""
        rows = [{"backend": "Find File", "candidate": {"text": "a", "matches": [[1, 2]]}}]
        text = form("f", rows)
        self.assertNotIn("[", text, text)
        # one `quote' per list argument, none left as a vector
        self.assertEqual(text.count("'"), 1, text)

    def test_a_tuple_is_a_list_too(self):
        """A tuple is the other way to ask for a Lisp list."""
        self.assertEqual(form("f", ("a", "b")), "(f '(\"a\" \"b\"))")

    def test_the_search_form_keeps_its_arguments_apart(self):
        """The search arguments are three values, not one vector.

        This is the bug that made every backend raise "'list' object has no
        attribute 'replace'": the three arguments arrived as one list, so
        the keyword the backends search for was a list of them.
        """
        text = form("search", "blink", 10, ["Buffer List"])
        self.assertEqual(text, '(search "blink" 10 \'("Buffer List"))')
        parsed = sexpdata.loads(text)
        self.assertEqual(len(parsed), 4)
        self.assertEqual(parsed[1], "blink")
        self.assertEqual(parsed[2], 10)


class ToLispListTest(unittest.TestCase):
    """The recursive conversion itself."""

    def test_a_list_becomes_a_tuple(self):
        """The top level list is converted."""
        self.assertEqual(to_lisp_list([1, 2]), (1, 2))

    def test_the_conversion_recurses(self):
        """A list inside a list is converted as well."""
        self.assertEqual(to_lisp_list([[1], "a"]), ((1,), "a"))

    def test_other_values_are_left_alone(self):
        """Strings, numbers and dictionaries keep their type."""
        for value in ("a", 1, {"k": "v"}, None, True):
            self.assertEqual(to_lisp_list(value), value)
