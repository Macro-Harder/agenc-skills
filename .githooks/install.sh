#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"
git config core.hooksPath .githooks
chmod +x .githooks/pre-commit .githooks/pre-push
echo "xai-receipt-gate hooks installed: core.hooksPath=.githooks in $REPO_ROOT"
if [ ! -f /workspace/desk-lib/xai-receipt-gate ]; then
  echo "Warning: /workspace/desk-lib/xai-receipt-gate is missing"
fi
