"""
Protected Resource Server (x402 v2 Python SDK)
Supports TRON Nile and BSC Testnet.
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
FACILITATOR_URL = os.getenv("FACILITATOR_URL", "http://localhost:8011")
SERVER_PORT = int(os.getenv("SERVER_PORT", "8010"))
PRICE = os.getenv("PROTECTED_PRICE", "$0.01")

if not TRON_PAY_TO and not BSC_PAY_TO:
    raise ValueError("PAY_TO_ADDRESS (TRON) or BSC_PAY_TO (EVM) environment variable is required")

# ---------------------------------------------------------------------------
# Initialize Resource Server (sync)
# ---------------------------------------------------------------------------

facilitator_client = HTTPFacilitatorClientSync(FacilitatorConfig(url=FACILITATOR_URL))
resource_server = x402ResourceServerSync(facilitator_client)

# Register both schemes (only active networks will be used depending on facilitator)
if TRON_PAY_TO:
    register_exact_tron_server(resource_server, networks="tron:nile")
if BSC_PAY_TO:
    register_exact_evm_server(resource_server, networks="eip155:97")

resource_server.initialize()

# ---------------------------------------------------------------------------
# Routes configuration
# ---------------------------------------------------------------------------

accepts = []
if TRON_PAY_TO:
    accepts.append(
        PaymentOption(scheme="exact", network="tron:nile", pay_to=TRON_PAY_TO, price=PRICE)
    )
if BSC_PAY_TO:
    accepts.append(
        PaymentOption(scheme="exact", network="eip155:97", pay_to=BSC_PAY_TO, price=PRICE)
    )

routes = RoutesConfig(
    routes=[
        RouteConfig(path="/protected", methods=["GET"], accepts=accepts),
    ]
)
http_server = x402HTTPResourceServerSync(resource_server, routes)

# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="X402 Protected Resource Server (v2)",
    description="Resource server using x402 Python v2 SDK (TRON + EVM)",
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
        "networks": list(filter(None, [
            "tron:nile" if TRON_PAY_TO else "",
            "eip155:97 (BSC Testnet)" if BSC_PAY_TO else "",
        ])),
        "endpoints": ["/protected - GET (payment required)"],
        "facilitator": FACILITATOR_URL,
        "price": PRICE,
    }


@app.get("/protected")
def protected_resource(request: Request):
    """Payment-protected resource."""
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

    return {
        "message": "Access granted! Payment verified.",
        "networks": ["tron:nile", "eip155:97"],
    }


# ---------------------------------------------------------------------------
# Start
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("X402 Protected Resource Server (Python / v2 SDK)")
    print("=" * 60)
    print(f"  Port:        {SERVER_PORT}")
    print(f"  Facilitator: {FACILITATOR_URL}")
    print(f"  Price:       {PRICE}")
    print(f"  TRON Pay To: {TRON_PAY_TO}")
    print(f"  BSC Pay To:  {BSC_PAY_TO}")
    print("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=SERVER_PORT, log_level="info")


if __name__ == "__main__":
    main()
