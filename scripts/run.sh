#!/usr/bin/env bash
# Starts the service (the M1 contract): it listens on $PORT, or 8080 if it is unset.
set -euo pipefail
cd "$(dirname "$0")/.."
exec python3 src/server.py
