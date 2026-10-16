#!/usr/bin/env python3
"""The test suite of blink-search.

The tests are run from the root of the repository, because the modules under
test import `core' and `backend' as top-level packages:

    uv run --frozen python -m unittest discover -s test -p 'test_*.py' -t .

scripts/check-test.sh runs the ERT suites as well.
"""
