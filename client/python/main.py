"""
X402 Client Demo (x402 v2 Python SDK)
Supports TRON Nile and BSC Testnet.
"""

import os
import json
import base64
import time
from pathlib import Path
from tempfile import gettempdir

from dotenv import load_dotenv
from eth_account import Account
from tronpy import Tron
from tronpy.keys import PrivateKey

from bankofai.x402 import x402ClientSync
from bankofai.x402.mechanisms.evm.constants import ERC20_ALLOWANCE_ABI
from bankofai.x402.mechanisms.evm.signers import FacilitatorWeb3Signer
from bankofai.x402.mechanisms.evm.constants import PERMIT2_ADDRESSES as EVM_PERMIT2_ADDRESSES
from bankofai.x402.mechanisms.tron.constants import PERMIT2_ADDRESSES
from bankofai.x402.mechanisms.evm import EthAccountSigner
from bankofai.x402.mechanisms.evm.exact import register_exact_evm_client
from bankofai.x402.mechanisms.tron import ClientTronSigner, register_exact_tron_client

# ---------------------------------------------------------------------------
# Load .env
# ---------------------------------------------------------------------------

load_dotenv(Path(__file__).parent / ".env")
load_dotenv(Path(__file__).parent.parent.parent / ".env")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

TRON_PRIVATE_KEY = os.getenv("TRON_CLIENT_PRIVATE_KEY", os.getenv("TRON_PRIVATE_KEY", ""))
BSC_PRIVATE_KEY = os.getenv("BSC_CLIENT_PRIVATE_KEY", os.getenv("BSC_PRIVATE_KEY", ""))
BSC_TESTNET_RPC_URL = os.getenv("BSC_TESTNET_RPC_URL", "")

SERVER_URL = os.getenv("SERVER_URL", "http://localhost:8000")
ENDPOINT = os.getenv("ENDPOINT", "/protected")
PREFERRED_NETWORK = os.getenv("PREFERRED_NETWORK")

if not PREFERRED_NETWORK:
    if TRON_PRIVATE_KEY:
        PREFERRED_NETWORK = "tron:nile"
        ENDPOINT = "/protected-nile"
    else:
        PREFERRED_NETWORK = "eip155:97"
        ENDPOINT = "/protected-bsc-testnet"

if not TRON_PRIVATE_KEY and not BSC_PRIVATE_KEY:
    raise ValueError("At least one of TRON_CLIENT_PRIVATE_KEY or BSC_CLIENT_PRIVATE_KEY is required")

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


def select_requirement(payment_required):
    accepts = getattr(payment_required, "accepts", None) or []
    if not accepts:
        raise ValueError("No payment requirements available")

    if PREFERRED_NETWORK:
        for requirement in accepts:
            if requirement.network == PREFERRED_NETWORK:
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


def print_tron_permit2_allowance(payment_payload, tron_address: str | None) -> dict | None:
    if not tron_address:
        return None

    accepted = getattr(payment_payload, "accepted", None)
    if not accepted or accepted.network != "tron:nile":
        return None

    extra = accepted.extra or {}
    if extra.get("assetTransferMethod") != "permit2":
        return None

    permit2_address = PERMIT2_ADDRESSES.get("tron:nile")
    if not permit2_address:
        return None

    try:
        client = Tron(network="nile")
        contract = client.get_contract(accepted.asset)
        allowance = int(contract.functions.allowance(tron_address, permit2_address))
        required = int(str(accepted.amount))
        result = {
            "owner": tron_address,
            "token": accepted.asset,
            "permit2": permit2_address,
            "current": allowance,
            "required": required,
            "needs_approve": allowance < required,
        }
        print("\nTRON Permit2 allowance:")
        print(f"  owner:        {result['owner']}")
        print(f"  token:        {result['token']}")
        print(f"  permit2:      {result['permit2']}")
        print(f"  current:      {result['current']}")
        print(f"  required:     {result['required']}")
        if result["needs_approve"]:
            print("  status:       NEEDS_APPROVE")
            print("  note:         Python demo client does not auto-approve before permit2 payment")
        else:
            print("  status:       OK")
        return result
    except Exception as exc:
        print(f"\nTRON Permit2 allowance check failed: {exc}")
        return None


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


def ensure_tron_permit2_approval(requirement, tron_private_key: str, owner_address: str) -> None:
    extra = requirement.extra or {}
    if extra.get("assetTransferMethod") != "permit2":
        return

    permit2_address = PERMIT2_ADDRESSES.get(requirement.network)
    if not permit2_address:
        raise ValueError(f"No Permit2 configured for {requirement.network}")

    client = Tron(network="nile")
    contract = client.get_contract(requirement.asset)
    allowance = int(contract.functions.allowance(owner_address, permit2_address))
    required = int(str(requirement.amount))
    if allowance >= required:
        return

    print(f"\nAuto-approving TRON Permit2: {allowance} < {required}")
    private_key = PrivateKey(bytes.fromhex(tron_private_key.removeprefix("0x")))
    tx = (
        contract.functions.approve(permit2_address, MAX_UINT256)
        .with_owner(owner_address)
        .fee_limit(1_000_000_000)
        .build()
        .sign(private_key)
    )
    result = tx.broadcast()
    txid = str(result.txid)
    print(f"  approval tx: {txid}")
    for _ in range(30):
        try:
            info = client.get_transaction_info(txid)
            if info.get("receipt", {}).get("result") == "SUCCESS":
                return
            if info.get("receipt", {}).get("result"):
                raise RuntimeError(f"TRON approval transaction failed: {txid}")
        except Exception:
            pass
        time.sleep(1)
    raise RuntimeError(f"TRON approval transaction not confirmed: {txid}")


def ensure_evm_permit2_approval(requirement, evm_private_key: str, owner_address: str) -> None:
    extra = requirement.extra or {}
    if extra.get("assetTransferMethod") != "permit2":
        return

    if not BSC_TESTNET_RPC_URL:
        raise ValueError("BSC_TESTNET_RPC_URL is required for EVM permit2 approval")

    permit2_address = EVM_PERMIT2_ADDRESSES.get(requirement.network)
    if not permit2_address:
        raise ValueError(f"No Permit2 configured for {requirement.network}")

    signer = FacilitatorWeb3Signer(evm_private_key, BSC_TESTNET_RPC_URL)
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

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("X402 Client (Python / v2 SDK)")
    print("=" * 60)
    
    # Build client
    client = x402ClientSync()
    tron_signer = None

    if TRON_PRIVATE_KEY:
        tron_signer = ClientTronSigner(private_key=TRON_PRIVATE_KEY)
        register_exact_tron_client(client, tron_signer)
        print(f"  TRON Address: {tron_signer.address}")

    if BSC_PRIVATE_KEY:
        pk = BSC_PRIVATE_KEY if BSC_PRIVATE_KEY.startswith("0x") else "0x" + BSC_PRIVATE_KEY
        account = Account.from_key(pk)
        evm_signer = EthAccountSigner(account)
        register_exact_evm_client(client, evm_signer)
        print(f"  EVM Address:  {account.address}")

    print(f"  Target:       {SERVER_URL}{ENDPOINT}")
    print(f"  Network:      {PREFERRED_NETWORK}")
    print("=" * 60)

    import httpx
    from bankofai.x402.http import (
        x402HTTPClientSync,
        PaymentRoundTripper,
    )

    with httpx.Client(timeout=120.0) as http:
        payment_client = x402HTTPClientSync(client)

        url = f"{SERVER_URL}{ENDPOINT}"
        print(f"\nGET {url}...")
        
        # Step 1: Initial request
        response = http.get(url)
        
        if response.status_code != 402:
            print(f"Status: {response.status_code}")
            print(response.text[:500])
            return

        print("\n402 Payment Required received")
        
        # Step 2: Create payment payload
        # Handle both v2 and v1 via the helper
        get_header = lambda h: response.headers.get(h)
        payment_required = payment_client.get_payment_required_response(get_header, response.content)
        print_accepts(payment_required)
        selected = select_requirement(payment_required)
        if selected.network.startswith("tron:") and tron_signer:
            ensure_tron_permit2_approval(selected, TRON_PRIVATE_KEY, tron_signer.address)
        elif selected.network.startswith("eip155:") and BSC_PRIVATE_KEY:
            if not BSC_PRIVATE_KEY.startswith("0x"):
                normalized_bsc_private_key = "0x" + BSC_PRIVATE_KEY
            else:
                normalized_bsc_private_key = BSC_PRIVATE_KEY
            ensure_evm_permit2_approval(
                selected,
                normalized_bsc_private_key,
                Account.from_key(normalized_bsc_private_key).address,
            )
        
        payment_payload = client.create_payment_payload(payment_required)
        print(f"Payment created: scheme={payment_payload.accepted.scheme} network={payment_payload.accepted.network}")
        allowance_info = print_tron_permit2_allowance(
            payment_payload, tron_signer.address if tron_signer else None
        )

        # Step 3: Retry with payment header
        payment_headers = payment_client.encode_payment_signature_header(payment_payload)
        print(f"\nRetry headers:  {', '.join(payment_headers.keys())}")
        response = http.get(url, headers=payment_headers)

        print(f"\nFinal Status: {response.status_code}")
        print(f"Content-Type:  {response.headers.get('content-type', '')}")
        payment_response = print_payment_response_header(response)
        print("\nResponse body:")
        print_response_body(response)
        if (
            response.status_code == 402
            and allowance_info
            and allowance_info.get("needs_approve")
            and isinstance(payment_response, dict)
            and payment_response.get("errorReason") == "invalid_transaction_state"
        ):
            print("\nLikely cause:")
            print("  Permit2 allowance is below the required amount.")
            print("  Python demo client does not auto-approve before replaying the payment request.")


if __name__ == "__main__":
    main()
