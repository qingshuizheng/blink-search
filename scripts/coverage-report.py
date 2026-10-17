#!/usr/bin/env python3
"""Report which source files a test file mentions.

This is the "did the refactor leave a module behind" gate.  It is not line
coverage: it answers the coarser question of whether anything in `test/'
imports, requires or even names a module, which is what catches a backend or a
module that has no test at all.

    scripts/coverage-report.py            # the table
    scripts/coverage-report.py --check    # exit 1 when something is untested

A module counts as covered when a test file mentions

* its dotted name, for Python (`core.backend', `backend.search_pdf'), or
* its feature name, for Elisp (`blink-search-render'), or
* for scripts/, its file name (`check-protocol.py').

Some files are listed in EXEMPT with the reason, so that "no test" is a
decision somebody wrote down instead of an oversight.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

#: Files that are not covered on purpose, with the reason.
EXEMPT = {
    "blink-search-epc.el": "vendored fork of tkf/emacs-epc, checked by the elisp gate",
    "blink-search.el": "the front door: it only requires the other modules",
    "blink-search-process.el": "starts a process; its pieces are covered by core/session and core/navigator",
    "scripts/fake-emacs.py": "a debugging harness, not shipped code",
    "scripts/local-search.py": "a debugging harness, not shipped code",
    "scripts/docstring-report.py": "a reporting tool used by the gates themselves",
}

#: The gates themselves: they are what runs the tests, so requiring a test for
#: them is circular.  `check-test.sh' and `check-elisp.sh' exercise them on
#: every run, which is the check that matters.
EXEMPT_PREFIXES = ("scripts/check-", "scripts/coverage-report.py")


def repo_files(pattern: str) -> list[pathlib.Path]:
    """Return the repository files matching PATTERN, tests excluded."""
    out = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z", pattern],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout
    return [ROOT / name for name in out.split("\0") if name]


def test_text() -> str:
    """Return every test file concatenated, which is what is searched."""
    parts = []
    for pattern in ("test/*.py", "test/*.el"):
        for path in repo_files(pattern):
            parts.append(path.read_text(encoding="utf-8", errors="ignore"))
    return "\n".join(parts)


def module_names(path: pathlib.Path) -> list[str]:
    """Return the names a test could use to refer to PATH.

    A Python file is referred to by its dotted name, an Elisp file by its
    feature, and a script by its file name.
    """
    relative = path.relative_to(ROOT)
    names = []

    if path.suffix == ".py":
        dotted = str(relative.with_suffix("")).replace("/", ".")
        names.append(dotted)
        # `from core.backend import X` and `import backend.search_pdf` are both
        # how a test names it, so the dotted name is the pattern to search.
        names.append(dotted.rsplit(".", 1)[-1] + ".")
    elif path.suffix == ".el":
        names.append(relative.stem)
    else:
        names.append(relative.name)

    return names


def covered(path: pathlib.Path, text: str) -> bool:
    """Return whether any test file names PATH."""
    for name in module_names(path):
        if re.search(r"(?<![\w.-])" + re.escape(name) + r"(?![\w-])", text):
            return True
    return False


def main() -> int:
    """Print the table and, with --check, fail on an untested file."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="exit 1 when a source file has no test")
    ap.add_argument("--list", action="store_true",
                    help="print one line per file instead of a table")
    args = ap.parse_args()

    text = test_text()
    # Every source kind in one list, deduplicated: `*.py' matches the
    # backend, core and scripts files as well, so asking git four times would
    # list them four times.
    sources = sorted(
        {path for pattern in ("*.el", "*.py", "backend/*.py", "core/*.py", "scripts/*")
         for path in repo_files(pattern)},
        key=lambda p: str(p.relative_to(ROOT)),
    )

    missing = []
    rows = []
    for path in sources:
        relative = str(path.relative_to(ROOT))
        if "/test/" in relative or relative.startswith("test/"):
            continue
        # The exempt list holds repo-relative paths, so both the relative
        # name and the base name are looked up: a vendored file is named by
        # its base name, a script by its path.
        if relative in EXEMPT or path.name in EXEMPT or relative.startswith(EXEMPT_PREFIXES):
            rows.append((relative, "exempt"))
            continue
        if covered(path, text):
            rows.append((relative, "tested"))
        else:
            rows.append((relative, "MISSING"))
            missing.append(relative)

    if args.list:
        for relative, state in rows:
            print("%-9s %s" % (state, relative))
    else:
        tested = sum(1 for _, state in rows if state == "tested")
        exempt = sum(1 for _, state in rows if state == "exempt")
        total = len(rows)
        print("source files %d   tested %d   exempt %d   missing %d"
              % (total, tested, exempt, len(missing)))
        print()
        print("%-9s %s" % ("state", "file"))
        for relative, state in rows:
            if state != "tested":
                print("%-9s %s" % (state, relative))

    if missing:
        print()
        print("no test names: %s" % ", ".join(missing), file=sys.stderr)
        if args.check:
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
