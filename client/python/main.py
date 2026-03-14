"""
X402 Client Demo (x402 v2 Python SDK)

Only two inputs needed:
  PRIVATE_KEY  - hex private key (works for both TRON and EVM chains)
  SERVER_URL   - full URL of the protected resource (e.g. http://localhost:8000/protected-nile)

The client auto-detects the required network from the server's 402 response
and dynamically registers only the needed signer.

Environment variables:
  PRIVATE_KEY   - (required) hex private key
  SERVER_URL    - full URL of the protected resource (default: http://localhost:8000/protected-nile)
  X402_TIMEOUT  - HTTP timeout in seconds (default: 120)
"""

import json
import os
from pathlib import Path
from tempfile import gettempdir

from dotenv import load_dotenv

from bankofai.x402 import x402ClientSync
from bankofai.x402.http import x402HTTPClientSync

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


def detect_networks(response_headers: dict, body: bytes) -> set[str]:
    """Extract required network(s) from the 402 response.

    The x402 middleware puts payment info in the Payment-Required header
    (base64-encoded JSON). Falls back to parsing the body if the header
    is absent.
    """
    import base64

    pr_header = response_headers.get("payment-required", "")
    if pr_header:
        data = json.loads(base64.b64decode(pr_header))
    else:
        data = json.loads(body)

    accepts = data.get("accepts", [])
    return {a["network"] for a in accepts if "network" in a}


def register_signers(client: x402ClientSync, networks: set[str], private_key: str) -> None:
    """Dynamically register only the signers needed for the detected networks."""
    needs_tron = any(n.startswith("tron:") for n in networks)
    needs_evm = any(n.startswith("eip155:") for n in networks)

    if needs_tron:
        from bankofai.x402.mechanisms.tron import ClientTronSigner, register_exact_tron_client
        tron_signer = ClientTronSigner(private_key=private_key)
        register_exact_tron_client(client, tron_signer)
        print(f"  Registered TRON signer (address: {tron_signer.address})")

    if needs_evm:
        from eth_account import Account
        from bankofai.x402.mechanisms.evm import EthAccountSigner
        from bankofai.x402.mechanisms.evm.exact import register_exact_evm_client
        pk = private_key if private_key.startswith("0x") else "0x" + private_key
        account = Account.from_key(pk)
        register_exact_evm_client(client, EthAccountSigner(account))
        print(f"  Registered EVM signer  (address: {account.address})")

    if not needs_tron and not needs_evm:
        raise ValueError(f"Unsupported network(s): {networks}")


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
    print(f"  Target: {server_url}")
    print("=" * 60)

    import httpx

    with httpx.Client(timeout=timeout) as http:
        # Step 1: GET the resource → expect 402
        print(f"\nGET {server_url}...")
        response = http.get(server_url)

        if response.status_code != 402:
            print(f"Status: {response.status_code}")
            print(response.text[:500])
            return

        print("\n402 Payment Required received")

        # Step 2: Detect network from 402 body, register only needed signer
        networks = detect_networks(dict(response.headers), response.content)
        print(f"  Networks offered: {', '.join(sorted(networks))}")

        client = x402ClientSync()
        register_signers(client, networks, private_key)

        # Step 3: Create payment and retry
        payment_client = x402HTTPClientSync(client)

        get_header = lambda h: response.headers.get(h)
        payment_required = payment_client.get_payment_required_response(get_header, response.content)

        payment_payload = client.create_payment_payload(payment_required)
        print(f"\nPayment created: scheme={payment_payload.accepted.scheme} network={payment_payload.accepted.network}")

        payment_headers = payment_client.encode_payment_signature_header(payment_payload)
        response = http.get(server_url, headers=payment_headers)

        print(f"Final Status: {response.status_code}")
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
