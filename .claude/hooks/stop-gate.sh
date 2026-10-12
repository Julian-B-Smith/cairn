#!/usr/bin/env bash
# Stop / SubagentStop shim — PROJECT-OWNED, and deliberately almost empty.
# The closing gate itself is kit-owned: `.kit/stop-gate.sh`, vendored and
# checksummed by kit_sync.py (kit 2.9.0). Do not copy its logic here: a local
# copy is how the leak gate drifted into ten implementations.
#
# The gate's third test (is this the tree ./verify judged?) only LOGS by
# default. To make it block in this repo before the fleet default flips,
# uncomment the next line and record the change in DECISIONS.md (GATE-CHANGE):
# export KIT_STOP_GATE_MODE=deny
GATE="${CLAUDE_PROJECT_DIR:-.}/.kit/stop-gate.sh"
if [ ! -r "$GATE" ]; then
  # A missing gate must not fail open: exit 127 from `exec` does not block.
  # Block once per stop cycle, then let the session end.
  grep -q '"stop_hook_active": *true' && exit 0
  echo "Harness gate: .kit/stop-gate.sh is missing, so nothing is checking this session's work. Run kit_sync.py." >&2
  exit 2
fi
exec bash "$GATE"
