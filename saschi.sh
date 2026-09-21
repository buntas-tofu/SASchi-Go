#!/usr/bin/env sh
# SASchi-Go launcher (POSIX shell twin of saschi.bat).
# Prefers a local .venv python, falls back to python3 on PATH.
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PY="$ROOT/.venv/bin/python"
if [ ! -x "$PY" ]; then
    PY=python3
fi

cd "$ROOT"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
exec "$PY" -m saschi "$@"
