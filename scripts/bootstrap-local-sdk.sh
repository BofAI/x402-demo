#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$DEMO_DIR/../x402" && pwd)"
PACKAGES_DIR="$REPO_ROOT/typescript/packages"
LOCAL_X402_VERSION="$(node -e 'console.log(require(process.argv[1]).version)' "$PACKAGES_DIR/core/package.json")"
TMP_DIR="$(mktemp -d)"
TARBALLS=()

cleanup() {
  if [[ -f "$TMP_DIR/package.json.backup" ]]; then
    mv "$TMP_DIR/package.json.backup" "$DEMO_DIR/package.json"
  fi
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

if ! command -v node >/dev/null 2>&1; then
  echo "Error: node is required" >&2
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "Error: npm is required" >&2
  exit 1
fi

if ! command -v pnpm >/dev/null 2>&1; then
  echo "Error: pnpm is required" >&2
  exit 1
fi

mkdir -p "$TMP_DIR/stage"

patch_workspace_versions() {
  local package_json="$1"
  node -e '
    const fs = require("fs");
    const file = process.argv[1];
    const version = process.argv[2];
    const pkg = JSON.parse(fs.readFileSync(file, "utf8"));
    const patch = (deps) => {
      if (!deps) return;
      for (const [name, value] of Object.entries(deps)) {
        if (typeof value === "string") {
          deps[name] = value.replace(/workspace:\*/g, version).replace(/workspace:~/g, version);
        }
      }
    };
    patch(pkg.dependencies);
    patch(pkg.devDependencies);
    patch(pkg.peerDependencies);
    fs.writeFileSync(file, JSON.stringify(pkg, null, 2) + "\n");
  ' "$package_json" "$LOCAL_X402_VERSION"
}

pack_local_sdk() {
  local relative_path="$1"
  local alias_name="$2"
  local src="$PACKAGES_DIR/$relative_path"
  local dst="$TMP_DIR/stage/$alias_name"

  (cd "$src" && pnpm build >/dev/null)
  cp -R "$src" "$dst"
  rm -f "$dst"/*.tgz
  patch_workspace_versions "$dst/package.json"
  local tarball
  tarball="$(cd "$dst" && npm pack)"
  TARBALLS+=("$dst/$tarball")
}

echo "[bootstrap] Packing local SDK packages..."
pack_local_sdk "core" "core"
pack_local_sdk "extensions" "extensions"
pack_local_sdk "mechanisms/tron" "tron"
pack_local_sdk "mechanisms/evm" "evm"
pack_local_sdk "mcp" "mcp"

echo "[bootstrap] Installing demo runtime dependencies..."
cd "$DEMO_DIR"
rm -rf node_modules
cp package.json "$TMP_DIR/package.json.backup"
node -e '
  const fs = require("fs");
  const file = process.argv[1];
  const pkg = JSON.parse(fs.readFileSync(file, "utf8"));
  const x402Deps = [
    "@bankofai/x402-core",
    "@bankofai/x402-extensions",
    "@bankofai/x402-tron",
    "@bankofai/x402-evm",
    "@bankofai/x402-mcp",
  ];
  pkg.dependencies ||= {};
  for (const name of x402Deps) {
    if (pkg.dependencies[name]) {
      pkg.dependencies[name] = "*";
    }
  }
  fs.writeFileSync(file, JSON.stringify(pkg, null, 2) + "\n");
' "$DEMO_DIR/package.json"
npm install --no-save --no-package-lock \
  cors@^2.8.5 \
  dotenv@^16.4.5 \
  express@^4.21.0 \
  @modelcontextprotocol/sdk@^1.12.1 \
  tronweb@^6.0.0 \
  viem@^2.45.2 \
  zod@^3.24.2 \
  @types/cors@^2.8.17 \
  @types/express@^5.0.0 \
  @types/node@^22.0.0 \
  tsx@^4.19.0 \
  typescript@^5.7.0 \
  "${TARBALLS[@]}"

mv "$TMP_DIR/package.json.backup" "$DEMO_DIR/package.json"
echo "[bootstrap] Done. Local SDK packages are installed into x402-demo/node_modules."
