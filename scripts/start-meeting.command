#!/bin/zsh
set -eu
BUZZ_PROJECT_DIR="${0:A:h:h}"
cd "$BUZZ_PROJECT_DIR"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
exec uv run --no-sync python -m buzz.meeting
