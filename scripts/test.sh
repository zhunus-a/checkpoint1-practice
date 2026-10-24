#!/usr/bin/env bash
# Runs the unit tests (the M1 contract): exits 0 only if every test passed,
# and prints one summary line, TESTS: passed/total.
set -euo pipefail
cd "$(dirname "$0")/.."

status=0
python3 -m unittest discover -s tests -v 2>&1 | tee test-output.txt || status=$?

total=$(sed -n 's/^Ran \([0-9][0-9]*\) tests\{0,1\} in .*/\1/p' test-output.txt)
passed=$(grep -c ' \.\.\. ok$' test-output.txt || true)
echo "TESTS: ${passed}/${total:-0}"
exit "$status"
