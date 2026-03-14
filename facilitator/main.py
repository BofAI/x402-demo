"""
Facilitator Main Entry Point (x402 v2 Python SDK)

Data-driven network registration — add new chains by appending to NETWORKS.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from bankofai.x402 import x402FacilitatorSync, PaymentPayload, PaymentRequirements
from bankofai.x402.mechanisms.evm import FacilitatorWeb3Signer
from bankofai.x402.mechanisms.evm.exact import register_exact_evm_facilitator
from bankofai.x402.mechanisms.tron import FacilitatorTronSigner, register_exact_tron_facilitator

# ---------------------------------------------------------------------------
# Load .env
# ---------------------------------------------------------------------------

load_dotenv(Path(__file__).parent / ".env")
load_dotenv(Path(__file__).parent.parent / ".env")

# ---------------------------------------------------------------------------
# Network Configuration
# ---------------------------------------------------------------------------

NETWORKS = [
    # TRON
    {
        "type": "tron",
        "network": "tron:mainnet",
        "label": "TRON Mainnet",
        "rpc_url": os.getenv("TRON_MAINNET_RPC_URL", "https://api.trongrid.io"),
        "private_key_env": "TRON_MAINNET_PRIVATE_KEY",
    },
    {
        "type": "tron",
        "network": "tron:nile",
        "label": "TRON Nile",
        "rpc_url": os.getenv("TRON_NILE_RPC_URL", "https://nile.trongrid.io"),
        "private_key_env": "TRON_NILE_PRIVATE_KEY",
    },
    # BSC
    {
        "type": "evm",
        "network": "eip155:56",
        "label": "BSC Mainnet",
        "rpc_url": os.getenv("BSC_MAINNET_RPC_URL", "https://bsc-dataseed.binance.org"),
        "private_key_env": "BSC_MAINNET_PRIVATE_KEY",
    },
    {
        "type": "evm",
        "network": "eip155:97",
        "label": "BSC Testnet",
        "rpc_url": os.getenv("BSC_TESTNET_RPC_URL", "https://data-seed-prebsc-1-s1.binance.org:8545"),
        "private_key_env": "BSC_TESTNET_PRIVATE_KEY",
    },
]

FACILITATOR_PORT = int(os.getenv("FACILITATOR_PORT", "8001"))

# ---------------------------------------------------------------------------
# Initialize Facilitator
# ---------------------------------------------------------------------------

facilitator = x402FacilitatorSync()
registered_networks: list[str] = []

for net in NETWORKS:
    private_key = os.getenv(net["private_key_env"], "")
    if not private_key:
        continue

    if net["type"] == "tron":
        signer = FacilitatorTronSigner(private_key=private_key, full_node=net["rpc_url"])
        register_exact_tron_facilitator(facilitator, signer, networks=[net["network"]])
        print(f"  [{net['label']}] Facilitator Address: {signer.address}")

    elif net["type"] == "evm":
        signer = FacilitatorWeb3Signer(private_key=private_key, rpc_url=net["rpc_url"])
        register_exact_evm_facilitator(facilitator, signer, networks=net["network"])
        print(f"  [{net['label']}] Facilitator Address: {signer.address}")

    registered_networks.append(f"{net['network']} ({net['label']})")

if not registered_networks:
    raise ValueError(
        "No networks registered. Set at least one private key: "
        + ", ".join(net["private_key_env"] for net in NETWORKS)
    )

print("=" * 60)
print("X402 Facilitator (Python / v2 SDK)")
print("=" * 60)
print(f"  Networks: {', '.join(registered_networks)}")
print("=" * 60)

# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="X402 Facilitator (v2)",
    description="Payment facilitator using x402 Python v2 SDK (TRON + EVM)",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/supported")
def supported():
    """Get supported payment kinds."""
    return facilitator.get_supported()


@app.post("/verify")
def verify(body: dict):
    """Verify a payment payload."""
    try:
        payload = PaymentPayload.model_validate(body["paymentPayload"])
        requirements = PaymentRequirements.model_validate(body["paymentRequirements"])
        result = facilitator.verify(payload, requirements)
        return result.model_dump(by_alias=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/settle")
def settle(body: dict):
    """Settle a payment on-chain."""
    try:
        payload = PaymentPayload.model_validate(body["paymentPayload"])
        requirements = PaymentRequirements.model_validate(body["paymentRequirements"])
        result = facilitator.settle(payload, requirements)
        return result.model_dump(by_alias=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Start
# ---------------------------------------------------------------------------

def main():
    print(f"\nStarting X402 Facilitator on port {FACILITATOR_PORT}...")
    uvicorn.run(app, host="0.0.0.0", port=FACILITATOR_PORT, log_level="info")


if __name__ == "__main__":
    main()
