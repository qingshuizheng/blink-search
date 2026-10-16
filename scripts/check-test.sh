#!/bin/sh
# Run every test that does not need a real Emacs frame or a real search tool.
#
#   scripts/check-test.sh          # ERT suites + the Python tests
#   scripts/check-test.sh --all    # placeholder for the tests that need tools
#
# The ERT suites are read straight from the sources (`load-prefer-newer'), so a
# stale .elc left over from debugging cannot make them pass or fail wrongly.
# The Python tests run through `uv run --frozen' when `uv' is available, which
# is what provides epc/sexpdata, and through python3 otherwise.
set -eu
cd "$(dirname "$0")/.."

EMACS=${EMACS:-emacs}

run_ert() {
    "$EMACS" -Q --batch --eval "(setq load-prefer-newer t)" \
        -L . -L test -l "$1" -f ert-run-tests-batch-and-exit
}

# The protocol gate imports the Python half, which needs epc and sexpdata,
# so it runs through the same interpreter as the tests.
run_script() {
    if command -v uv >/dev/null 2>&1; then
        uv run --frozen --quiet python "$@"
    else
        python3 "$@"
    fi
}

run_python() {
    run_script -m unittest "$@"
}

echo "== docstrings: names they mention still exist (scripts/docstring-report.py)"
python3 scripts/docstring-report.py >/dev/null

echo "== protocol: the two halves declare the same version (scripts/check-protocol.py)"
run_script scripts/check-protocol.py

for suite in test/*-test.el; do
    [ -f "$suite" ] || continue
    echo "== ERT: $suite"
    run_ert "$suite"
done

echo "== Python: pure tests"
run_python discover -s test -p 'test_*.py' -t .

if [ "${1:-}" = "--all" ]; then
    echo "== Python: tests that need the external tools (rg/fd/rga)"
    run_python discover -s test -p 'test_tools_*.py' -t .
fi
