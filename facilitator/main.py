"""
Facilitator Main Entry Point (x402 v2 Python SDK)
Supports both TRON Nile and BSC Testnet.
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
# Configuration
# ---------------------------------------------------------------------------

TRON_PRIVATE_KEY = os.getenv("TRON_FACILITATOR_PRIVATE_KEY", os.getenv("TRON_PRIVATE_KEY", ""))
TRON_GRID_API_KEY = os.getenv("TRON_GRID_API_KEY", "")
TRON_FULL_NODE = os.getenv("TRON_FULL_NODE", "https://nile.trongrid.io")

BSC_PRIVATE_KEY = os.getenv("BSC_PRIVATE_KEY", "")
BSC_TESTNET_RPC_URL = os.getenv("BSC_TESTNET_RPC_URL", "https://data-seed-prebsc-1-s1.binance.org:8545")

FACILITATOR_PORT = int(os.getenv("FACILITATOR_PORT", "8001"))

if not TRON_PRIVATE_KEY and not BSC_PRIVATE_KEY:
    raise ValueError("At least one of TRON_PRIVATE_KEY or BSC_PRIVATE_KEY is required")

# ---------------------------------------------------------------------------
# Initialize Facilitator
# ---------------------------------------------------------------------------

facilitator = x402FacilitatorSync()

# Register TRON Nile
if TRON_PRIVATE_KEY:
    tron_signer = FacilitatorTronSigner(private_key=TRON_PRIVATE_KEY, full_node=TRON_FULL_NODE)
    register_exact_tron_facilitator(facilitator, tron_signer, networks=["tron:nile"])
    print(f"  [TRON] Facilitator Address: {tron_signer.address}")

# Register BSC Testnet
if BSC_PRIVATE_KEY:
    bsc_signer = FacilitatorWeb3Signer(private_key=BSC_PRIVATE_KEY, rpc_url=BSC_TESTNET_RPC_URL)
    register_exact_evm_facilitator(facilitator, bsc_signer, networks="eip155:97")
    print(f"  [BSC]  Facilitator Address: {bsc_signer.address}")

print("=" * 60)
print("X402 Facilitator (Python / v2 SDK)")
print("=" * 60)
print(f"  Networks: " + ", ".join(filter(None, [
    "tron:nile" if TRON_PRIVATE_KEY else "",
    "eip155:97 (BSC Testnet)" if BSC_PRIVATE_KEY else "",
])))
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
