#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REQ_FILE="$ROOT_DIR/requirements.txt"
VENV_DIR="$ROOT_DIR/.venv"
PY_BIN="$VENV_DIR/bin/python"
LOCAL_X402_PY_DIR="$(cd "$ROOT_DIR/../x402/python/x402" 2>/dev/null && pwd || true)"

echo "Installing legacy/demo Python dependencies for x402-demo." >&2
echo "If you want the primary TypeScript v2 path, use: npm run bootstrap:local-sdk" >&2
echo "" >&2

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

# Note: Local x402 SDK at ../x402/python/x402 installs as package 'x402',
# but this demo requires 'bankofai.x402' from the pinned Git tag in requirements.txt.
echo "Installing bankofai.x402 from pinned Git tag (requirements.txt)..." >&2
"$PY_BIN" -m pip install --no-cache-dir --force-reinstall -r "$REQ_FILE"

echo "Validating bankofai.x402 sync exports..." >&2
"$PY_BIN" - <<'PY'
from bankofai import x402

required = ("x402ClientSync", "x402ResourceServerSync", "x402FacilitatorSync")
missing = [name for name in required if not hasattr(x402, name)]
if missing:
    raise SystemExit(
        "Installed bankofai.x402 is missing expected sync exports: "
        + ", ".join(missing)
    )
print("bankofai.x402 sync exports are available.")
PY

# TypeScript client dependencies
TS_DIR="$ROOT_DIR/client/typescript"
if [[ -f "$TS_DIR/package.json" ]]; then
  echo ""
  echo "Installing TypeScript client dependencies..." >&2
  (cd "$TS_DIR" && npm install)
fi
