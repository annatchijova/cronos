#!/usr/bin/env bash
# Copyright 2026 Anna Tchijova
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# CRONOS — Black Box Recorder for AI Agents
# Installation script
# Usage: bash install.sh

set -euo pipefail

G='\033[0;32m'; Y='\033[1;33m'; R='\033[0;31m'; N='\033[0m'
ok()   { echo -e "${G}  ✓${N} $1"; }
warn() { echo -e "${Y}  ⚠${N} $1"; }
err()  { echo -e "${R}  ✗${N} $1"; exit 1; }

echo ""
echo "CRONOS — Black Box Recorder for AI Agents"
echo "Installation"
echo ""

# Python version check (3.10+)
command -v python3 >/dev/null 2>&1 || err "python3 not found"
PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
# Let Python compare the version tuple — a shell "major>=3 AND minor>=10" test
# is wrong (it rejects e.g. 4.2, whose minor 2 is < 10).
python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" \
    || err "Python 3.10+ required (found $PY_VER)"
ok "Python $PY_VER"

# Virtual environment
if [ ! -d .venv ]; then
    python3 -m venv .venv
    ok ".venv created"
else
    ok ".venv already exists"
fi

# shellcheck source=/dev/null
source .venv/bin/activate
ok "Virtual environment activated"

pip install --quiet --upgrade pip
pip install --quiet -e ".[dev]"
ok "Dependencies installed (package installed in editable mode)"

# .env setup
if [ ! -f .env ]; then
    cat > .env <<'ENVEOF'
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_APP_TOKEN=xapp-your-app-token
SLACK_SIGNING_SECRET=your-signing-secret
ENVEOF
    warn ".env created — fill in your Slack credentials before running"
    warn "  Import slack_manifest.yml at api.slack.com/apps to get these values"
else
    ok ".env already exists"
fi

echo ""
echo "Installation complete."
echo ""
echo "Next steps:"
echo "  source .venv/bin/activate"
echo "  python3 main.py                   # local run (Socket Mode)"
echo "  pytest                             # run the test suite"
echo "  docker compose up                  # Docker"
