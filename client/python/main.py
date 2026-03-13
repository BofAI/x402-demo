"""
X402 Client Demo (x402 v2 Python SDK)
Makes a payment-protected request to the resource server using EVM (BSC Testnet).
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from eth_account import Account

from bankofai.x402 import x402ClientSync
from bankofai.x402.mechanisms.evm import EthAccountSigner
from bankofai.x402.mechanisms.evm.exact import register_exact_evm_client

# ---------------------------------------------------------------------------
# Load .env
# ---------------------------------------------------------------------------

load_dotenv(Path(__file__).parent / ".env")
load_dotenv(Path(__file__).parent.parent / ".env")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BSC_PRIVATE_KEY = os.getenv("BSC_CLIENT_PRIVATE_KEY", os.getenv("BSC_PRIVATE_KEY", ""))
SERVER_URL = os.getenv("SERVER_URL", "http://localhost:8010")
ENDPOINT = os.getenv("ENDPOINT", "/protected")
PREFERRED_NETWORK = os.getenv("PREFERRED_NETWORK", "eip155:97")

if not BSC_PRIVATE_KEY:
    raise ValueError("BSC_CLIENT_PRIVATE_KEY or BSC_PRIVATE_KEY environment variable is required")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    # Normalize private key
    pk = BSC_PRIVATE_KEY if BSC_PRIVATE_KEY.startswith("0x") else "0x" + BSC_PRIVATE_KEY
    account = Account.from_key(pk)
    signer = EthAccountSigner(account)

    print("=" * 60)
    print("X402 Client (Python / v2 SDK)")
    print("=" * 60)
    print(f"  EVM Address: {account.address}")
    print(f"  Target:      {SERVER_URL}{ENDPOINT}")
    print(f"  Network:     {PREFERRED_NETWORK}")
    print("=" * 60)

    # Build client
    client = x402ClientSync()
    register_exact_evm_client(client, signer)

    import httpx
    from bankofai.x402.http import (
        x402HTTPClientSync,
        PaymentRoundTripper,
    )

    with httpx.Client() as http:
        payment_client = x402HTTPClientSync(http, client)

        url = f"{SERVER_URL}{ENDPOINT}"
        print(f"\nGET {url}...")
        response = payment_client.request("GET", url)

        print(f"\nStatus: {response.status_code}")
        try:
            body = response.json()
            import json
            print(json.dumps(body, indent=2))
        except Exception:
            print(response.text[:500])


if __name__ == "__main__":
    main()
