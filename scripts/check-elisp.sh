#!/bin/sh
# Byte-compile the elisp sources (and optionally report checkdoc problems).
#
#   scripts/check-elisp.sh                  # every tracked .el file
#   scripts/check-elisp.sh blink-search.el  # just these
#   CHECKDOC=1 scripts/check-elisp.sh       # also print checkdoc findings
#
# .elc output goes to $ELC_DIR (default /tmp/blink-search-elc) so the working
# tree stays clean.  The Elisp backends live in backend/, so that directory is
# on the load path as well.
set -eu
cd "$(dirname "$0")/.."

EMACS=${EMACS:-emacs}
ELC_DIR=${ELC_DIR:-/tmp/blink-search-elc}
LOAD_PATH="-L ."
if [ "$#" -gt 0 ]; then
    FILES=$*
else
    # Tracked files plus the ones that are new but not committed yet, so that a
    # file added by a refactor step is compiled by the same run that reviews it;
    # --exclude-standard keeps ignored files (byte code, .venv) out.  Sorted, so
    # that the warning profile does not depend on the order git happens to list
    # untracked files in.
    FILES=$(git ls-files --cached --others --exclude-standard '*.el' | sort \
            | while read -r f; do [ -f "$f" ] && echo "$f"; done | tr '\n' ' ')
fi
COUNT=$(echo "$FILES" | wc -w | tr -d ' ')

# elisp list of the file names, for --eval snippets
FILES_LISP=""
for f in $FILES; do FILES_LISP="$FILES_LISP \"$f\""; done

redir="(progn
  (make-directory \"$ELC_DIR\" t)
  (setq byte-compile-dest-file-function
        (lambda (f) (expand-file-name (concat (file-name-nondirectory f) \"c\")
                                      \"$ELC_DIR\"))))"

# A file whose last form is missing a closing paren still reads the forms
# before it, so its warning count silently drops instead of failing.  Walk the
# top level of every file first and stop on the first unbalanced one.
echo "== read every top-level form"
# shellcheck disable=SC2086
$EMACS -Q --batch $LOAD_PATH -l scripts/check-forms.el \
    --eval "(z/check-forms $FILES_LISP)"

# A definition whose body was lost still reads and still compiles: a `defun'
# that is only a docstring silently returns nil.  Walk the definitions before
# compiling anything.
echo "== every definition has a body"
# shellcheck disable=SC2086
$EMACS -Q --batch $LOAD_PATH -l scripts/check-bodies.el \
    --eval "(z/check-bodies $FILES_LISP)"

echo "== byte-compile $COUNT file(s) -> $ELC_DIR"
# shellcheck disable=SC2086
$EMACS -Q --batch $LOAD_PATH --eval "$redir" -f batch-byte-compile $FILES

# A file can compile cleanly in the batch above and still fail on its own: the
# batch is sorted, so a file that only defines a variable another file reads
# first may be compiled after it.  Compiling every file with only its requires
# on the load path is what catches that.
echo "== byte-compile each file on its own"
for f in $FILES; do
    if ! out=$($EMACS -Q --batch $LOAD_PATH --eval "$redir" -f batch-byte-compile "$f" 2>&1); then
        echo "FAILED: $f does not compile on its own"
        printf '%s\n' "$out" | grep -E 'Error:|Cannot open load file|Symbol' || printf '%s\n' "$out" | tail -5
        exit 1
    fi
done
echo "   every file compiles on its own"

# Third-party code kept verbatim so it can still be diffed against upstream: it
# is compiled like the rest of the tree, but its docstrings are not ours to
# rewrite, so checkdoc skips it.  scripts/docstring-report.py keeps the same
# list.
VENDORED="blink-search-epc.el"

if [ "${CHECKDOC:-0}" = 1 ]; then
    echo "== checkdoc"
    DOC_FILES=""
    for f in $FILES; do
        case "$(basename "$f")" in
            "$VENDORED") ;;
            *) DOC_FILES="$DOC_FILES \"$f\"" ;;
        esac
    done
    $EMACS -Q --batch $LOAD_PATH --eval "$redir" --eval \
        "(dolist (f (list $DOC_FILES)) (checkdoc-file f))"
fi
