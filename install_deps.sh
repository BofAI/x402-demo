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

if [[ -n "$LOCAL_X402_PY_DIR" && -f "$LOCAL_X402_PY_DIR/pyproject.toml" ]]; then
  echo "Installing local bankofai.x402 Python v2 SDK from: $LOCAL_X402_PY_DIR" >&2
  "$PY_BIN" -m pip install --no-cache-dir --force-reinstall "${LOCAL_X402_PY_DIR}[tron,evm]"

  echo "Installing remaining demo Python dependencies..." >&2
  "$PY_BIN" - <<'PY'
from pathlib import Path

req = Path("requirements.txt")
lines = req.read_text().splitlines()
filtered = [
    line
    for line in lines
    if line.strip()
    and not line.lstrip().startswith("#")
    and not line.startswith("bankofai.x402")
]
Path(".requirements.runtime.txt").write_text("\n".join(filtered) + "\n")
PY
  "$PY_BIN" -m pip install --no-cache-dir --force-reinstall -r "$ROOT_DIR/.requirements.runtime.txt"
  rm -f "$ROOT_DIR/.requirements.runtime.txt"
else
  # Fallback for users who only cloned x402-demo without the sibling x402 repo.
  # Force-refresh the dependency so stale site-packages installs do not hide
  # newly exported sync helpers like x402FacilitatorSync.
  "$PY_BIN" -m pip install --no-cache-dir --force-reinstall -r "$REQ_FILE"
fi

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
