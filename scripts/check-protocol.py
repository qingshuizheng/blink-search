#!/usr/bin/env python3
"""Check that the version and the methods of the protocol match on both sides.

blink-search is one repository with two runtimes: Emacs (Elisp) and the Python
search process.  They talk over EPC, and nothing in either language stops one
side from being changed without the other.  This script is the gate for that.

    scripts/check-protocol.py

Three things are checked:

1. The protocol version each side declares is the same number.
2. Every EPC method the Elisp half calls exists on the Python side, as a
   method of the search process or as one of the update methods that are
   built from the backend modules.
3. The two method tables in blink-search-protocol.el and the method table in
   core/protocol.py name the methods that both sides actually have.

The tables are read with a real Elisp reader (`read' in batch Emacs), because
a regular expression cannot follow the nested lists a Lisp form is made of.
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
ELISP_FILE = ROOT / "blink-search-protocol.el"
PYTHON_FILE = ROOT / "core" / "protocol.py"
PYTHON_ENTRY_FILE = ROOT / "blink_search.py"

#: Methods that belong to EPC itself, or that every Emacs has, and not to
#: blink-search: they are called but are not part of any table.
IGNORED = {"eval-in-emacs", "get-emacs-var", "get-emacs-vars", "kill-new", "message"}

ELISP_VERSION_RE = re.compile(r'\(defconst\s+blink-search-protocol-version\s+"([^"]+)"')
PYTHON_VERSION_RE = re.compile(r'^PROTOCOL_VERSION\s*=\s*"([^"]+)"', re.MULTILINE)
ELISP_CALL_RE = re.compile(r'blink-search-call-async\s+"([a-z_]+)"')
PYTHON_EPC_METHOD_RE = re.compile(r"^    def ([a-z_][a-z0-9_]*)\(", re.MULTILINE)

#: Read the two method tables out of the protocol file.  `car' of every entry
#: is the name; the rest of the entry is the description.
READ_TABLES = r"""
(progn
  (require 'blink-search-protocol)
  (dolist (table (list (cons "emacs" blink-search-protocol-emacs-methods)
                       (cons "python" blink-search-protocol-python-methods)))
    (dolist (entry (cdr table))
      (princ (format "%s\t%s\n" (car table) (car entry))))))
"""


def read(path: pathlib.Path) -> str:
    """Return the text of PATH, or an empty string when it does not exist."""
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def tracked(path: pathlib.Path) -> bool:
    """Return whether PATH is tracked or untracked-but-not-ignored by git."""
    out = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z", "--",
         str(path.relative_to(ROOT))],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout
    return bool(out.strip("\0"))


def elisp_tables() -> dict:
    """Return the two method tables of the protocol file, as two sets."""
    if not ELISP_FILE.exists():
        return {"emacs": set(), "python": set()}

    out = subprocess.run(
        ["emacs", "-Q", "--batch", "-L", str(ROOT), "--eval", READ_TABLES],
        capture_output=True, text=True, cwd=ROOT, check=False,
    )
    if out.returncode != 0:
        print("could not read the protocol tables:", file=sys.stderr)
        print(out.stderr, file=sys.stderr)
        return {"emacs": set(), "python": set()}

    tables = {"emacs": set(), "python": set()}
    for line in out.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) == 2 and parts[0] in tables:
            tables[parts[0]].add(parts[1])
    return tables


def main() -> int:
    """Compare the two halves and report the result."""
    if not ELISP_FILE.exists() or not PYTHON_FILE.exists():
        if tracked(ELISP_FILE) or tracked(PYTHON_FILE):
            print("one of the protocol files is tracked but missing", file=sys.stderr)
            return 1
        print("protocol files are not present yet, skipped")
        return 0

    elisp_version = ELISP_VERSION_RE.search(read(ELISP_FILE))
    python_version = PYTHON_VERSION_RE.search(read(PYTHON_FILE))
    if not elisp_version or not python_version:
        print("no protocol version declared", file=sys.stderr)
        return 1

    print("elisp  blink-search-protocol-version = {}".format(elisp_version.group(1)))
    print("python PROTOCOL_VERSION              = {}".format(python_version.group(1)))
    if elisp_version.group(1) != python_version.group(1):
        print("PROTOCOL MISMATCH: the two halves disagree", file=sys.stderr)
        return 1

    sys.path.insert(0, str(ROOT))
    from blink_search import import_backends  # pylint: disable=import-outside-toplevel
    from core.backend import update_names  # pylint: disable=import-outside-toplevel
    from core.protocol import EMACS_METHODS  # pylint: disable=import-outside-toplevel

    import_backends()
    python_methods = set(PYTHON_EPC_METHOD_RE.findall(read(PYTHON_ENTRY_FILE))) | set(update_names())
    elisp_called = elisp_calls()
    tables = elisp_tables()

    failures = 0

    for name in sorted(elisp_called - python_methods):
        print("the Elisp half calls {}, which the Python half does not have".format(name), file=sys.stderr)
        failures += 1

    for name in sorted(tables["python"] - python_methods):
        print("{} is declared in the protocol but not implemented".format(name), file=sys.stderr)
        failures += 1

    for name in sorted(tables["emacs"] - set(EMACS_METHODS)):
        print("{} is declared in the Elisp table but not in Python's".format(name), file=sys.stderr)
        failures += 1

    for name in sorted(set(EMACS_METHODS) - tables["emacs"]):
        print("{} is in Python's table but not in the Elisp one".format(name), file=sys.stderr)
        failures += 1

    if failures:
        print("PROTOCOL MISMATCH: {} problem(s)".format(failures), file=sys.stderr)
        return 1

    print("protocol: {} Elisp calls, {} Python methods, {} Emacs callbacks, all matched".format(
        len(elisp_called), len(python_methods), len(tables["emacs"])))
    return 0


def elisp_calls() -> set:
    """Return every method name the Elisp half calls on the Python half."""
    names = set()
    for path in sorted(ROOT.glob("*.el")) + sorted((ROOT / "backend").glob("*.el")):
        names |= set(ELISP_CALL_RE.findall(read(path)))
    return names


if __name__ == "__main__":
    sys.exit(main())
