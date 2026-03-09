#!/usr/bin/env bash
set -euo pipefail

# Initialize agent-wallet wallets for demo testing from .env private keys.
# Usage:
#   bash scripts/init_agent_wallet.sh

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEFAULT_TRON_AGENT_WALLET_NAME="x402-tron-test"
DEFAULT_BSC_AGENT_WALLET_NAME="x402-bsc-test"
DEFAULT_AGENT_WALLET_SECRETS_DIR="$ROOT_DIR/.agent-wallet"

TRON_AGENT_WALLET_NAME="$DEFAULT_TRON_AGENT_WALLET_NAME"
BSC_AGENT_WALLET_NAME="$DEFAULT_BSC_AGENT_WALLET_NAME"
AGENT_WALLET_SECRETS_DIR="$DEFAULT_AGENT_WALLET_SECRETS_DIR"

prompt_secret() {
  local prompt="$1"
  local __out_var="$2"
  local value=""

  while [[ -z "$value" ]]; do
    read -r -s -p "$prompt" value
    echo ""
    value="${value//[[:space:]]/}"
  done

  printf -v "$__out_var" '%s' "$value"
}

AGENT_WALLET_PASSWORD=""
TRON_PRIVATE_KEY=""
BSC_PRIVATE_KEY=""
prompt_secret "Enter AGENT_WALLET_PASSWORD (will encrypt keys): " AGENT_WALLET_PASSWORD
prompt_secret "Enter TRON private key (hex, no 0x prefix needed): " TRON_PRIVATE_KEY
prompt_secret "Enter BSC/EVM private key (hex, no 0x prefix needed): " BSC_PRIVATE_KEY

AGENT_WALLET_SECRETS_DIR="${AGENT_WALLET_SECRETS_DIR/#\~/$HOME}"

echo ""
echo "================================================================================"
echo "Agent wallet init (defaults)"
echo "================================================================================"
echo "Secrets dir : $AGENT_WALLET_SECRETS_DIR"
echo "TRON wallet : $TRON_AGENT_WALLET_NAME"
echo "BSC  wallet : $BSC_AGENT_WALLET_NAME"
echo "================================================================================"

if ! command -v agent-wallet >/dev/null 2>&1; then
  echo "❌ agent-wallet CLI not found in current environment." >&2
  echo "Run ./install_deps.sh first (with the agent-wallet source dependency installed)." >&2
  exit 1
fi

export AGENT_WALLET_PASSWORD
export AGENT_WALLET_DIR="$AGENT_WALLET_SECRETS_DIR"
export TRON_AGENT_WALLET_NAME
export BSC_AGENT_WALLET_NAME
export TRON_PRIVATE_KEY
export BSC_PRIVATE_KEY

python - <<'PY'
import os
import stat
from pathlib import Path

from agent_wallet.core.base import WalletType
from agent_wallet.secret.kv_store import SecureKVStore
from agent_wallet.storage.config import WalletConfig, WalletsTopology, load_config, save_config


def load_config_safe(secrets_dir: str) -> WalletsTopology:
    try:
        return load_config(secrets_dir)
    except FileNotFoundError:
        return WalletsTopology(wallets={})


def derive_address(wallet_type: WalletType, private_key: bytes) -> str:
    if wallet_type == WalletType.EVM_LOCAL:
        from eth_account import Account

        return Account.from_key(private_key).address
    if wallet_type == WalletType.TRON_LOCAL:
        from tronpy.keys import PrivateKey

        return PrivateKey(private_key).public_key.to_base58check_address()
    return ""


secrets_dir = os.environ["AGENT_WALLET_DIR"]
password = os.environ["AGENT_WALLET_PASSWORD"]
tron_name = os.environ.get("TRON_AGENT_WALLET_NAME", "x402-tron-test")
evm_name = os.environ.get("BSC_AGENT_WALLET_NAME", "x402-bsc-test")
tron_key_hex = os.environ["TRON_PRIVATE_KEY"].strip().removeprefix("0x")
evm_key_hex = os.environ["BSC_PRIVATE_KEY"].strip().removeprefix("0x")

secrets_path = Path(secrets_dir)
secrets_path.mkdir(parents=True, exist_ok=True)
try:
    os.chmod(secrets_path, stat.S_IRWXU)
except PermissionError:
    pass

kv = SecureKVStore(secrets_dir, password)

master_file = secrets_path / "master.json"
if not master_file.exists():
    print(f"Initializing agent-wallet secrets dir: {secrets_dir}")
    kv.init_master()
    save_config(secrets_dir, WalletsTopology(wallets={}))

config = load_config_safe(secrets_dir)

tron_addr = None
evm_addr = None


def ensure_wallet(name: str, wtype: WalletType, key_hex: str) -> None:
    global tron_addr, evm_addr
    if name in config.wallets:
        print(f"Wallet already exists: {name}")
        addr = config.wallets[name].address
        if wtype == WalletType.TRON_LOCAL:
            tron_addr = addr
        elif wtype == WalletType.EVM_LOCAL:
            evm_addr = addr
        return

    try:
        key_bytes = bytes.fromhex(key_hex)
    except ValueError:
        raise SystemExit(f"Invalid hex private key for wallet '{name}'")

    kv.save_private_key(name, key_bytes)
    address = derive_address(wtype, key_bytes)
    config.wallets[name] = WalletConfig.model_validate(
        {"type": wtype.value, "identity_file": name, "address": address}
    )
    save_config(secrets_dir, config)
    if wtype == WalletType.TRON_LOCAL:
        tron_addr = address
    elif wtype == WalletType.EVM_LOCAL:
        evm_addr = address
    print(f"Added wallet: {name} ({wtype.value}) -> {address}")


ensure_wallet(tron_name, WalletType.TRON_LOCAL, tron_key_hex)
ensure_wallet(evm_name, WalletType.EVM_LOCAL, evm_key_hex)

bold = "\033[1m"
green = "\033[32m"
cyan = "\033[36m"
yellow = "\033[33m"
reset = "\033[0m"

print("\n" + "=" * 80)
print(f"{bold}{green}Agent wallet initialization complete{reset}")
print("=" * 80)
print(f"{bold}Secrets dir:{reset} {cyan}{secrets_dir}{reset}")
print(f"{bold}TRON wallet:{reset} {yellow}{tron_name}{reset}  {bold}address:{reset} {cyan}{tron_addr or '—'}{reset}")
print(f"{bold}BSC  wallet:{reset} {yellow}{evm_name}{reset}  {bold}address:{reset} {cyan}{evm_addr or '—'}{reset}")
print("\n" + f"{bold}Use these .env values for testing:{reset}")
print(f"{green}SIGNER_INIT_MODE=agent_wallet{reset}")
print(f"{green}TRON_AGENT_WALLET_NAME={tron_name}{reset}")
print(f"{green}BSC_AGENT_WALLET_NAME={evm_name}{reset}")
print("=" * 80)
PY
