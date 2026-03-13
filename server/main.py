"""
Protected Resource Server (x402 v2 Python SDK)
Uses FastAPI + x402HTTPResourceServer for payment-protected endpoints.
Network: EVM (BSC Testnet by default)
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn

from bankofai.x402 import x402ResourceServerSync
from bankofai.x402.http import (
    HTTPFacilitatorClientSync,
    FacilitatorConfig,
    x402HTTPResourceServerSync,
    PaymentOption,
    RoutesConfig,
    RouteConfig,
    HTTPRequestContext,
)
from bankofai.x402.mechanisms.evm.exact import register_exact_evm_server

# ---------------------------------------------------------------------------
# Load .env
# ---------------------------------------------------------------------------

load_dotenv(Path(__file__).parent / ".env")
load_dotenv(Path(__file__).parent.parent / ".env")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PAY_TO_ADDRESS = os.getenv("BSC_PAY_TO", os.getenv("PAY_TO_ADDRESS", ""))
BSC_TESTNET_RPC_URL = os.getenv("BSC_TESTNET_RPC_URL", "https://data-seed-prebsc-1-s1.binance.org:8545")
FACILITATOR_URL = os.getenv("FACILITATOR_URL", "http://localhost:8011")
SERVER_PORT = int(os.getenv("SERVER_PORT", "8010"))
PRICE = os.getenv("PROTECTED_PRICE", "$0.01")

if not PAY_TO_ADDRESS:
    raise ValueError("BSC_PAY_TO or PAY_TO_ADDRESS environment variable is required")

# ---------------------------------------------------------------------------
# Initialize Resource Server (sync)
# ---------------------------------------------------------------------------

facilitator_client = HTTPFacilitatorClientSync(FacilitatorConfig(url=FACILITATOR_URL))
resource_server = x402ResourceServerSync(facilitator_client)
register_exact_evm_server(resource_server, networks="eip155:97")
resource_server.initialize()

# ---------------------------------------------------------------------------
# Routes configuration
# ---------------------------------------------------------------------------

routes = RoutesConfig(
    routes=[
        RouteConfig(
            path="/protected",
            methods=["GET"],
            accepts=[
                PaymentOption(
                    scheme="exact",
                    network="eip155:97",
                    pay_to=PAY_TO_ADDRESS,
                    price=PRICE,
                )
            ],
        ),
    ]
)
http_server = x402HTTPResourceServerSync(resource_server, routes)

# ---------------------------------------------------------------------------
# Express App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="X402 Protected Resource Server (v2)",
    description="Resource server using x402 Python v2 SDK",
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


@app.get("/")
def index():
    return {
        "service": "X402 Protected Resource Server (Python / v2 SDK)",
        "networks": ["eip155:97 (BSC Testnet)"],
        "endpoints": ["/protected - GET (payment required)"],
        "facilitator": FACILITATOR_URL,
        "pay_to": PAY_TO_ADDRESS,
        "price": PRICE,
    }


@app.get("/protected")
def protected_resource(request: Request):
    """Payment-protected resource. Returns 402 if no valid payment."""
    ctx = HTTPRequestContext(
        path=request.url.path,
        method=request.method,
        headers=dict(request.headers),
        query_params=dict(request.query_params),
    )

    result = http_server.process_http_request(ctx)

    if result.type == "payment-error":
        resp = result.response
        return JSONResponse(
            status_code=resp.status,
            headers=resp.headers,
            content=resp.body,
        )

    # Payment verified — serve the protected content
    return {
        "message": "Access granted! Payment verified.",
        "network": "eip155:97",
        "pay_to": PAY_TO_ADDRESS,
    }


# ---------------------------------------------------------------------------
# Start
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("X402 Protected Resource Server (Python / v2 SDK)")
    print("=" * 60)
    print(f"  Port:        {SERVER_PORT}")
    print(f"  Pay To:      {PAY_TO_ADDRESS}")
    print(f"  Price:       {PRICE}")
    print(f"  Facilitator: {FACILITATOR_URL}")
    print(f"  Protected:   http://0.0.0.0:{SERVER_PORT}/protected")
    print("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=SERVER_PORT, log_level="info")


if __name__ == "__main__":
    main()
