#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REQ_FILE="$ROOT_DIR/requirements.txt"
VENV_DIR="$ROOT_DIR/.venv"
PY_BIN="$VENV_DIR/bin/python"
LOCAL_X402_DIR="${X402_SDK_DIR:-$ROOT_DIR/../x402}"
LOCAL_PY_SDK_DIR="$LOCAL_X402_DIR/python/x402"
LOCAL_TS_SDK_DIR="$LOCAL_X402_DIR/typescript/packages/x402"
STAMP_FILE="$ROOT_DIR/.x402-demo-deps-stamp"

if [[ ! -f "$REQ_FILE" ]]; then
  echo "requirements.txt not found: $REQ_FILE" >&2
  exit 1
fi

if [[ ! -x "$PY_BIN" ]]; then
  echo "Creating virtual environment at: $VENV_DIR" >&2
  python3 -m venv "$VENV_DIR"
fi

echo "Using Python: $PY_BIN" >&2
"$PY_BIN" -m pip install --upgrade pip
"$PY_BIN" -m pip install -r "$REQ_FILE"

if [[ -d "$LOCAL_PY_SDK_DIR" ]]; then
  echo "" >&2
  echo "Installing local Python SDK from: $LOCAL_PY_SDK_DIR" >&2
  "$PY_BIN" -m pip install -e "${LOCAL_PY_SDK_DIR}[tron,evm,fastapi]"
fi

if [[ -d "$LOCAL_TS_SDK_DIR" ]]; then
  echo "" >&2
  echo "Building local TypeScript SDK from: $LOCAL_TS_SDK_DIR" >&2
  (cd "$LOCAL_TS_SDK_DIR" && npm install && npm run build)
fi

# TypeScript client dependencies
TS_DIR="$ROOT_DIR/client/typescript"
if [[ -f "$TS_DIR/package.json" ]]; then
  echo ""
  echo "Installing TypeScript client dependencies..." >&2
  (cd "$TS_DIR" && npm install)
fi

if git -C "$LOCAL_X402_DIR" rev-parse HEAD >/dev/null 2>&1; then
  git -C "$LOCAL_X402_DIR" rev-parse HEAD > "$STAMP_FILE"
else
  printf '%s\n' "manual" > "$STAMP_FILE"
fi
