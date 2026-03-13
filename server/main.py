"""
Protected Resource Server (x402 v2 Python SDK)
Supports TRON Nile and BSC Testnet.
"""

import os
from pathlib import Path
import time

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn

from bankofai.x402 import x402ResourceServer
from bankofai.x402.http import HTTPFacilitatorClient, PaymentOption, FacilitatorConfig
from bankofai.x402.http.decorators.fastapi import x402_app
from bankofai.x402.mechanisms.evm.exact import register_exact_evm_server
from bankofai.x402.mechanisms.tron import register_exact_tron_server

# ---------------------------------------------------------------------------
# Load .env
# ---------------------------------------------------------------------------

load_dotenv(Path(__file__).parent / ".env")
load_dotenv(Path(__file__).parent.parent / ".env")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

TRON_PAY_TO = os.getenv("PAY_TO_ADDRESS", "")          # TRON Base58Check
BSC_PAY_TO = os.getenv("BSC_PAY_TO", "")               # EVM hex
FACILITATOR_URL = os.getenv("FACILITATOR_URL", "http://localhost:8001")
SERVER_PORT = int(os.getenv("SERVER_PORT", "8000"))
TRON_PRICE = os.getenv("TRON_PROTECTED_PRICE", "$0.0001")
FACILITATOR_SYNC_RETRIES = int(os.getenv("FACILITATOR_SYNC_RETRIES", "20"))
FACILITATOR_SYNC_RETRY_DELAY = float(os.getenv("FACILITATOR_SYNC_RETRY_DELAY", "1.0"))

BSC_TEST_ASSET = os.getenv("BSC_TEST_ASSET", "")
BSC_TEST_ASSET_NAME = os.getenv("BSC_TEST_ASSET_NAME", "DA HULU")
BSC_TEST_ASSET_VERSION = os.getenv("BSC_TEST_ASSET_VERSION", "1")
BSC_TEST_AMOUNT = os.getenv("BSC_TEST_AMOUNT", "1000")

if not TRON_PAY_TO and not BSC_PAY_TO:
    raise ValueError("PAY_TO_ADDRESS (TRON) or BSC_PAY_TO (EVM) environment variable is required")

# ---------------------------------------------------------------------------
# Initialize Resource Server (async)
# ---------------------------------------------------------------------------

facilitator_client = HTTPFacilitatorClient(FacilitatorConfig(url=FACILITATOR_URL))
# We must use the async x402ResourceServer for the async decorators to work!
resource_server = x402ResourceServer(facilitator_client)

if TRON_PAY_TO:
    register_exact_tron_server(resource_server, networks="tron:nile")
if BSC_PAY_TO:
    register_exact_evm_server(resource_server, networks="eip155:97")

x402 = x402_app(resource_server)

# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="X402 Protected Resource Server (v2)",
    description="Resource server using x402 Python v2 SDK decorators (TRON + EVM)",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

def build_payment_options():
    options = []
    if TRON_PAY_TO:
        options.append(
            PaymentOption(
                scheme="exact",
                network="tron:nile",
                pay_to=TRON_PAY_TO,
                price=TRON_PRICE,
                extra={"assetTransferMethod": "permit2"}
            )
        )
    if BSC_PAY_TO and BSC_TEST_ASSET:
        options.append(
            PaymentOption(
                scheme="exact",
                network="eip155:97",
                pay_to=BSC_PAY_TO,
                price={
                    "amount": BSC_TEST_AMOUNT,
                    "asset": BSC_TEST_ASSET,
                    "extra": {
                        "name": BSC_TEST_ASSET_NAME,
                        "version": BSC_TEST_ASSET_VERSION
                    }
                }
            )
        )
    return options

@app.on_event("startup")
async def startup() -> None:
    # Need to initialize the resource server
    resource_server.initialize()

@app.get("/")
async def index():
    return {
        "service": "X402 Protected Server (Python Decorator)",
        "features": "Decorators!"
    }

@app.get("/protected-nile")
@x402.pay(scheme="exact", network="tron:nile", pay_to=TRON_PAY_TO, price=TRON_PRICE, extra={"assetTransferMethod": "permit2"})
async def protected_nile(request: Request):
    return {
        "message": "Access granted! Payment verified on Nile.",
        "receipt": getattr(request.state, "payment_payload", None).model_dump(by_alias=True) if hasattr(request.state, "payment_payload") else None
    }

@app.get("/protected-multi")
@x402.pay(build_payment_options())
async def protected_multi():
    return {"message": "Access granted to multi-chain resource!"}

# Register the middleware hooks for the decorators!
x402.init_app(app)

def main():
    print("=" * 60)
    print("X402 Protected Resource Server - Decorator Edition")
    print("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=SERVER_PORT, log_level="info")

if __name__ == "__main__":
    main()
