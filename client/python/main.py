"""
X402 Client Demo (x402 v2 Python SDK)
Supports TRON Nile and BSC Testnet.
"""

import os
import json
from pathlib import Path
from tempfile import gettempdir

from dotenv import load_dotenv
from eth_account import Account

from bankofai.x402 import x402ClientSync
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

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("X402 Client (Python / v2 SDK)")
    print("=" * 60)
    
    # Build client
    client = x402ClientSync()

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
        
        payment_payload = client.create_payment_payload(payment_required)
        print(f"Payment created: scheme={payment_payload.accepted.scheme} network={payment_payload.accepted.network}")

        # Step 3: Retry with payment header
        payment_headers = payment_client.encode_payment_signature_header(payment_payload)
        response = http.get(url, headers=payment_headers)

        print(f"\nFinal Status: {response.status_code}")
        content_type = response.headers.get("content-type", "")

        if "image/" in content_type:
            image_path = save_image_response(response.content, content_type)
            print(f"Image saved: {image_path}")
            return

        try:
            body = response.json()
            print(json.dumps(body, indent=2))
        except Exception:
            print(response.text[:500])


if __name__ == "__main__":
    main()
