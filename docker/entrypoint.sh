#!/usr/bin/env bash
set -euo pipefail

python docker/migrate.py

exec "$@"
