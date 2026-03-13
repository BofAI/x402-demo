import os
import logging
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from bankofai.x402 import x402ResourceServer
from bankofai.x402.http import HTTPFacilitatorClient, PaymentOption, FacilitatorConfig
from bankofai.x402.http.middleware.fastapi import PaymentMiddlewareASGI
from bankofai.x402.http.types import RouteConfig
from bankofai.x402.mechanisms.evm.exact import ExactEvmServerScheme
from bankofai.x402.mechanisms.tron import ExactTronServerScheme
from bankofai.x402.schemas import AssetAmount

# ---------------------------------------------------------------------------
# Logging Configuration
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("x402-demo-server")

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
TRON_PRICE = os.getenv("TRON_PROTECTED_PRICE", "100")

BSC_TEST_ASSET = os.getenv("BSC_TEST_ASSET", "")
BSC_TEST_ASSET_NAME = os.getenv("BSC_TEST_ASSET_NAME", "DA HULU")
BSC_TEST_ASSET_VERSION = os.getenv("BSC_TEST_ASSET_VERSION", "1")
BSC_TEST_AMOUNT = os.getenv("BSC_TEST_AMOUNT", "1000")

if not TRON_PAY_TO and not BSC_PAY_TO:
    raise ValueError("PAY_TO_ADDRESS (TRON) or BSC_PAY_TO (EVM) environment variable is required")

logger.info(f"Starting x402-demo server on port {SERVER_PORT}")
logger.debug(f"TRON PayTo: {TRON_PAY_TO}")
logger.debug(f"EVM/BSC PayTo: {BSC_PAY_TO}")

# ---------------------------------------------------------------------------
# Initialize Resource Server 
# ---------------------------------------------------------------------------
facilitator_client = HTTPFacilitatorClient(FacilitatorConfig(url=FACILITATOR_URL))
resource_server = x402ResourceServer(facilitator_client)

if TRON_PAY_TO:
    logger.info("Registering TRON exact payment scheme...")
    resource_server.register("tron:nile", ExactTronServerScheme())
if BSC_PAY_TO:
    logger.info("Registering EVM exact payment scheme...")
    resource_server.register("eip155:97", ExactEvmServerScheme())

# Initialize server immediately
resource_server.initialize()

# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="X402 Protected Resource Server (v2)",
    description="Resource server using x402 Python v2 ASGI Middleware",
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

# ---------------------------------------------------------------------------
# Configure x402 Routes
# ---------------------------------------------------------------------------
accepts_nile = []
if TRON_PAY_TO:
    accepts_nile.append(
        PaymentOption(
            scheme="exact",
            network="tron:nile",
            pay_to=TRON_PAY_TO,
            price=AssetAmount(
                amount=TRON_PRICE,
                asset="TXYZopYRdj2D9XRtbG411XZZ3kM5VkAeBf",
                extra={
                    "name": "Tether USD",
                    "version": "1",
                    "assetTransferMethod": "permit2"
                }
            )
        )
    )

accepts_multi = [*accepts_nile]
if BSC_PAY_TO and BSC_TEST_ASSET:
    accepts_multi.append(
        PaymentOption(
            scheme="exact",
            network="eip155:97",
            pay_to=BSC_PAY_TO,
            price=AssetAmount(
                amount=BSC_TEST_AMOUNT,
                asset=BSC_TEST_ASSET,
                extra={
                    "name": BSC_TEST_ASSET_NAME,
                    "version": BSC_TEST_ASSET_VERSION
                }
            )
        )
    )

routes = {
    "GET /protected-nile": RouteConfig(
        accepts=accepts_nile,
        mime_type="application/json",
        description="TRON Nile Only Protected Content",
    ),
    "GET /protected-multi": RouteConfig(
        accepts=accepts_multi,
        mime_type="application/json",
        description="Multi-chain Protected Content",
    )
}

# Attach global middleware
logger.info("Applying x402 ASGI Middleware onto FastAPI app routes")
app.add_middleware(PaymentMiddlewareASGI, routes=routes, server=resource_server)

# ---------------------------------------------------------------------------
# Route Handlers
# ---------------------------------------------------------------------------
@app.get("/")
async def index():
    logger.debug("Received request on root / index")
    return {
        "service": "X402 Protected Server (ASGI Edition)",
        "features": "Native Route Matching & Detailed Logging!"
    }

@app.get("/protected-nile")
async def protected_nile(request: Request):
    logger.info("Client successfully accessed /protected-nile after valid TRON payment!")
    return {
        "message": "Access granted! Payment verified on Nile.",
        "receipt": getattr(request.state, "payment_payload", None).model_dump(by_alias=True) if hasattr(request.state, "payment_payload") else None
    }

@app.get("/protected-multi")
async def protected_multi():
    logger.info("Client successfully accessed /protected-multi after valid Multi-chain payment!")
    return {"message": "Access granted to multi-chain resource!"}

def main():
    print("=" * 60)
    print("X402 Protected Resource Server - Decorator Edition")
    print("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=SERVER_PORT, log_level="info")

if __name__ == "__main__":
    main()
