"""
X402 Client Demo (x402 v2 Python SDK)

Only two inputs needed:
  PRIVATE_KEY   - (required) hex private key, works for both TRON and EVM chains
  SERVER_URL    - full URL of the protected resource (default: http://localhost:8000/protected-nile)
  X402_TIMEOUT  - HTTP timeout in seconds (default: 120)

A single session.get() call handles the full 402 flow automatically:
  GET → 402 → create payment → retry with payment headers → final response
"""

import json
import os
from pathlib import Path
from tempfile import gettempdir

from dotenv import load_dotenv
from eth_account import Account

from bankofai.x402 import x402ClientSync
from bankofai.x402.mechanisms.evm import EthAccountSigner
from bankofai.x402.mechanisms.evm.exact import register_exact_evm_client
from bankofai.x402.mechanisms.tron import ClientTronSigner, register_exact_tron_client
from bankofai.x402.http.clients.requests import x402_requests

# ---------------------------------------------------------------------------
# Load .env
# ---------------------------------------------------------------------------
load_dotenv(Path(__file__).parent / ".env")
load_dotenv(Path(__file__).parent.parent.parent / ".env")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


def build_client(private_key: str) -> x402ClientSync:
    """Register both TRON and EVM signers; the SDK auto-selects by network."""
    client = x402ClientSync()

    tron_signer = ClientTronSigner(private_key=private_key)
    register_exact_tron_client(client, tron_signer)

    pk = private_key if private_key.startswith("0x") else "0x" + private_key
    evm_signer = EthAccountSigner(Account.from_key(pk))
    register_exact_evm_client(client, evm_signer)

    return client


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    private_key = os.getenv("PRIVATE_KEY", "")
    server_url = os.getenv("SERVER_URL", "http://localhost:8000/protected-nile")
    timeout = float(os.getenv("X402_TIMEOUT", "120"))

    if not private_key:
        raise ValueError("PRIVATE_KEY environment variable is required")

    print("=" * 60)
    print("X402 Client (Python / v2 SDK)")
    print("=" * 60)

    client = build_client(private_key)
    session = x402_requests(client)
    session.timeout = timeout

    print(f"  Target: {server_url}")
    print("=" * 60)

    # Single call — auto handles 402 → payment → retry
    print(f"\nGET {server_url}...")
    response = session.get(server_url)

    print(f"Status: {response.status_code}")
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
