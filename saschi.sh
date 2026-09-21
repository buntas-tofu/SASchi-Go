#!/usr/bin/env bash
# SASchi-Go launcher. Drops into the rich interface. Pass a .sas file to open it in context.
set -euo pipefail
cd "$(dirname "$0")"
exec python3 -m saschi.tui "$@"
