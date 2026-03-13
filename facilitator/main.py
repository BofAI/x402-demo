"""
Facilitator Main Entry Point (x402 v2 Python SDK)
Starts a FastAPI server for facilitator operations using the new v2 SDK.
Networks: EVM chains (BSC Testnet, Base Sepolia, etc.)
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

# ---------------------------------------------------------------------------
# Load .env
# ---------------------------------------------------------------------------

load_dotenv(Path(__file__).parent / ".env")
load_dotenv(Path(__file__).parent.parent / ".env")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BSC_PRIVATE_KEY = os.getenv("BSC_PRIVATE_KEY", "")
BSC_TESTNET_RPC_URL = os.getenv("BSC_TESTNET_RPC_URL", "https://data-seed-prebsc-1-s1.binance.org:8545")
FACILITATOR_PORT = int(os.getenv("FACILITATOR_PORT", "8011"))

if not BSC_PRIVATE_KEY:
    raise ValueError("BSC_PRIVATE_KEY environment variable is required")

# ---------------------------------------------------------------------------
# Initialize Facilitator
# ---------------------------------------------------------------------------

facilitator = x402FacilitatorSync()

# Register BSC Testnet EVM exact scheme
bsc_signer = FacilitatorWeb3Signer(
    private_key=BSC_PRIVATE_KEY,
    rpc_url=BSC_TESTNET_RPC_URL,
)
register_exact_evm_facilitator(facilitator, bsc_signer, networks="eip155:97")

print("=" * 60)
print("X402 Facilitator (Python / v2 SDK)")
print("=" * 60)
print(f"  Facilitator Address: {bsc_signer.address}")
print(f"  Registered Networks: eip155:97 (BSC Testnet)")
print("=" * 60)

# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="X402 Facilitator (v2)",
    description="Payment facilitator using x402 Python v2 SDK",
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
    return facilitator.supported()


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
    print(f"  GET  http://0.0.0.0:{FACILITATOR_PORT}/supported")
    print(f"  POST http://0.0.0.0:{FACILITATOR_PORT}/verify")
    print(f"  POST http://0.0.0.0:{FACILITATOR_PORT}/settle\n")
    uvicorn.run(app, host="0.0.0.0", port=FACILITATOR_PORT, log_level="info")


if __name__ == "__main__":
    main()
