"""
X402 Client Demo (x402 v2 Python SDK)

Primary input:
  PRIVATE_KEY  - hex private key used for whatever network the server offers

Compatibility fallbacks:
  TRON_CLIENT_PRIVATE_KEY / BSC_CLIENT_PRIVATE_KEY are still accepted if
  PRIVATE_KEY is not set.

The client auto-detects the required network from the server's 402 response,
registers the needed signer(s), and will auto-approve Permit2 when allowance
is insufficient before replaying the payment request.
"""

import base64
import json
import os
import sys
import time
from pathlib import Path
from tempfile import gettempdir

from dotenv import load_dotenv

from bankofai.x402 import x402ClientSync
from bankofai.x402.http import x402HTTPClientSync

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from python_sdk_info import format_installed_x402_sdk_info

# ---------------------------------------------------------------------------
# Load .env
# ---------------------------------------------------------------------------
load_dotenv(Path(__file__).parent / ".env")
load_dotenv(Path(__file__).parent.parent.parent / ".env")

MAX_UINT256 = 2**256 - 1
ERC20_APPROVE_ABI = [
    {
        "inputs": [
            {"name": "spender", "type": "address"},
            {"name": "amount", "type": "uint256"},
        ],
        "name": "approve",
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
        "type": "function",
    }
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_private_key() -> str:
    return (
        os.getenv("PRIVATE_KEY", "")
        or os.getenv("TRON_CLIENT_PRIVATE_KEY", "")
        or os.getenv("BSC_CLIENT_PRIVATE_KEY", "")
        or os.getenv("TRON_PRIVATE_KEY", "")
        or os.getenv("BSC_PRIVATE_KEY", "")
    )


def get_private_key_for_network(network: str) -> str:
    """Get private key for specific network."""
    if network.startswith("tron:"):
        return (
            os.getenv("TRON_CLIENT_PRIVATE_KEY", "")
            or os.getenv("TRON_PRIVATE_KEY", "")
            or get_private_key()
        )
    elif network.startswith("eip155:"):
        return (
            os.getenv("BSC_CLIENT_PRIVATE_KEY", "")
            or os.getenv("BSC_PRIVATE_KEY", "")
            or get_private_key()
        )
    return get_private_key()


def get_evm_rpc_url(network: str) -> str:
    if network == "eip155:56":
        return os.getenv("BSC_MAINNET_RPC_URL", "https://bsc-dataseed.binance.org")
    if network == "eip155:97":
        return os.getenv("BSC_TESTNET_RPC_URL", "https://data-seed-prebsc-1-s1.binance.org:8545")
    raise ValueError(f"Unsupported EVM network for approval: {network}")


def decode_base64_json(encoded: str) -> dict:
    padded = encoded + "=" * (-len(encoded) % 4)
    return json.loads(base64.b64decode(padded).decode("utf-8"))


def truncate_text(text: str, limit: int = 500) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def save_image_response(content: bytes, content_type: str) -> str:
    if "jpeg" in content_type or "jpg" in content_type:
        ext = "jpg"
    elif "webp" in content_type:
        ext = "webp"
    else:
        ext = "png"

    output_path = Path(gettempdir()) / f"x402_{os.getpid()}_{Path.cwd().name}.{ext}"
    output_path.write_bytes(content)
    return str(output_path)


def detect_networks(response_headers: dict, body: bytes) -> set[str]:
    """Extract required network(s) from the 402 response."""
    pr_header = response_headers.get("payment-required", "")
    if pr_header:
        data = json.loads(base64.b64decode(pr_header))
    else:
        data = json.loads(body)

    accepts = data.get("accepts", [])
    return {a["network"] for a in accepts if "network" in a}


def register_signers(client: x402ClientSync, networks: set[str]) -> dict[str, str]:
    """Register only the signers needed for the detected networks."""
    addresses: dict[str, str] = {}
    needs_tron = any(n.startswith("tron:") for n in networks)
    needs_evm = any(n.startswith("eip155:") for n in networks)

    if needs_tron:
        from bankofai.x402.mechanisms.tron import ClientTronSigner, register_exact_tron_client

        tron_private_key = get_private_key_for_network("tron:nile")
        tron_signer = ClientTronSigner(private_key=tron_private_key)
        register_exact_tron_client(client, tron_signer)
        addresses["tron"] = tron_signer.address
        print(f"  Registered TRON signer (address: {tron_signer.address})")

    if needs_evm:
        from eth_account import Account
        from bankofai.x402.mechanisms.evm import EthAccountSigner
        from bankofai.x402.mechanisms.evm.exact import register_exact_evm_client

        evm_private_key = get_private_key_for_network("eip155:97")
        pk = evm_private_key if evm_private_key.startswith("0x") else "0x" + evm_private_key
        account = Account.from_key(pk)
        register_exact_evm_client(client, EthAccountSigner(account))
        addresses["evm"] = account.address
        print(f"  Registered EVM signer  (address: {account.address})")

    if not needs_tron and not needs_evm:
        raise ValueError(f"Unsupported network(s): {networks}")

    return addresses


def select_requirement(payment_required):
    accepts = getattr(payment_required, "accepts", None) or []
    if not accepts:
        raise ValueError("No payment requirements available")

    preferred_network = os.getenv("PREFERRED_NETWORK", "")
    if preferred_network:
        for requirement in accepts:
            if requirement.network == preferred_network:
                return requirement

    return accepts[0]


def print_accepts(payment_required) -> None:
    accepts = getattr(payment_required, "accepts", None) or []
    print(f"  Accepts:      {len(accepts)} option(s)")
    for requirement in accepts:
        extra = getattr(requirement, "extra", None) or {}
        asset_transfer_method = extra.get("assetTransferMethod")
        extra_bits = []
        if asset_transfer_method:
            extra_bits.append(f"method={asset_transfer_method}")
        if extra.get("permit2FacilitatorAddress"):
            extra_bits.append(f"permit2FacilitatorAddress={extra['permit2FacilitatorAddress']}")
        suffix = f" ({', '.join(extra_bits)})" if extra_bits else ""
        print(
            "    - scheme=%s network=%s amount=%s asset=%s%s"
            % (
                requirement.scheme,
                requirement.network,
                requirement.amount,
                requirement.asset,
                suffix,
            )
        )


def ensure_tron_permit2_approval(requirement, private_key: str) -> None:
    from tronpy import Tron
    from tronpy.keys import PrivateKey
    from bankofai.x402.mechanisms.tron.constants import PERMIT2_ADDRESSES

    extra = requirement.extra or {}
    if extra.get("assetTransferMethod") != "permit2":
        return

    permit2_address = PERMIT2_ADDRESSES.get(requirement.network)
    if not permit2_address:
        raise ValueError(f"No Permit2 configured for {requirement.network}")

    network = "nile" if requirement.network == "tron:nile" else "mainnet"
    client = Tron(network=network)
    owner_key = PrivateKey(bytes.fromhex(private_key.removeprefix("0x")))
    owner_address = owner_key.public_key.to_base58check_address()
    contract = client.get_contract(requirement.asset)
    allowance = int(contract.functions.allowance(owner_address, permit2_address))
    required = int(str(requirement.amount))
    if allowance >= required:
        return

    print(f"\nAuto-approving TRON Permit2: {allowance} < {required}")
    tx = (
        contract.functions.approve(permit2_address, MAX_UINT256)
        .with_owner(owner_address)
        .fee_limit(1_000_000_000)
        .build()
        .sign(owner_key)
    )
    result = tx.broadcast()
    txid = str(result.txid)
    print(f"  approval tx: {txid}")
    for _ in range(30):
        try:
            info = client.get_transaction_info(txid)
            receipt_result = info.get("receipt", {}).get("result")
            if receipt_result == "SUCCESS":
                return
            if receipt_result:
                raise RuntimeError(f"TRON approval transaction failed: {txid}")
        except Exception:
            pass
        time.sleep(1)
    raise RuntimeError(f"TRON approval transaction not confirmed: {txid}")


def ensure_evm_permit2_approval(requirement, private_key: str) -> None:
    from eth_account import Account
    from bankofai.x402.mechanisms.evm.constants import (
        ERC20_ALLOWANCE_ABI,
        PERMIT2_ADDRESSES,
    )
    from bankofai.x402.mechanisms.evm.signers import FacilitatorWeb3Signer

    extra = requirement.extra or {}
    if extra.get("assetTransferMethod") != "permit2":
        return

    rpc_url = get_evm_rpc_url(requirement.network)
    permit2_address = PERMIT2_ADDRESSES.get(requirement.network)
    if not permit2_address:
        raise ValueError(f"No Permit2 configured for {requirement.network}")

    normalized_private_key = private_key if private_key.startswith("0x") else "0x" + private_key
    owner_address = Account.from_key(normalized_private_key).address
    signer = FacilitatorWeb3Signer(normalized_private_key, rpc_url)
    allowance = int(
        signer.read_contract(
            requirement.asset,
            ERC20_ALLOWANCE_ABI,
            "allowance",
            owner_address,
            permit2_address,
        )
    )
    required = int(str(requirement.amount))
    if allowance >= required:
        return

    print(f"\nAuto-approving EVM Permit2: {allowance} < {required}")
    tx_hash = signer.write_contract(
        requirement.asset,
        ERC20_APPROVE_ABI,
        "approve",
        permit2_address,
        MAX_UINT256,
    )
    print(f"  approval tx: {tx_hash}")
    receipt = signer.wait_for_transaction_receipt(tx_hash)
    if receipt.status != 1:
        raise RuntimeError(f"EVM approval transaction failed: {tx_hash}")


def print_payment_response_header(response) -> dict | None:
    header_value = response.headers.get("payment-response")
    if not header_value:
        print("\nPayment-Response: <missing>")
        return None

    print("\nPayment-Response header:")
    try:
        decoded = decode_base64_json(header_value)
        print(json.dumps(decoded, indent=2))
        return decoded
    except Exception:
        print(header_value)
        return None


def print_response_body(response) -> None:
    content_type = response.headers.get("content-type", "")

    if "image/" in content_type:
        image_path = save_image_response(response.content, content_type)
        print(f"Image saved: {image_path}")
        return

    body_text = response.text
    if not body_text.strip():
        print("{}")
        return

    try:
        print(json.dumps(response.json(), indent=2))
    except Exception:
        print(truncate_text(body_text))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    server_url = os.getenv("SERVER_URL", "http://localhost:8000/protected-nile")
    timeout = float(os.getenv("X402_TIMEOUT", "120"))

    print("=" * 60)
    print("X402 Client (Python / v2 SDK)")
    print("=" * 60)
    for line in format_installed_x402_sdk_info():
        print(line)
    print(f"  Target:       {server_url}")
    preferred_network = os.getenv("PREFERRED_NETWORK", "")
    if preferred_network:
        print(f"  Preferred:    {preferred_network}")
    print("=" * 60)

    import httpx

    with httpx.Client(timeout=timeout) as http:
        print(f"\nGET {server_url}...")
        response = http.get(server_url)

        if response.status_code != 402:
            print(f"Status: {response.status_code}")
            print(truncate_text(response.text))
            return

        print("\n402 Payment Required received")
        networks = detect_networks(dict(response.headers), response.content)
        print(f"  Networks offered: {', '.join(sorted(networks))}")

        client = x402ClientSync()
        register_signers(client, networks)
        payment_client = x402HTTPClientSync(client)

        get_header = lambda h: response.headers.get(h)
        payment_required = payment_client.get_payment_required_response(get_header, response.content)
        print_accepts(payment_required)

        selected = select_requirement(payment_required)
        if selected.network.startswith("tron:"):
            tron_private_key = get_private_key_for_network(selected.network)
            ensure_tron_permit2_approval(selected, tron_private_key)
        elif selected.network.startswith("eip155:"):
            evm_private_key = get_private_key_for_network(selected.network)
            ensure_evm_permit2_approval(selected, evm_private_key)

        payment_payload = client.create_payment_payload(payment_required)
        print(
            f"\nPayment created: scheme={payment_payload.accepted.scheme} "
            f"network={payment_payload.accepted.network}"
        )

        payment_headers = payment_client.encode_payment_signature_header(payment_payload)
        print(f"Retry headers:  {', '.join(payment_headers.keys())}")
        response = http.get(server_url, headers=payment_headers)

        print(f"\nFinal Status: {response.status_code}")
        print(f"Content-Type:  {response.headers.get('content-type', '')}")
        print_payment_response_header(response)
        print("\nResponse body:")
        print_response_body(response)


if __name__ == "__main__":
    main()
