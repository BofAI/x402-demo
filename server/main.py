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
from bankofai.x402.http.middleware.fastapi import FastAPIAdapter
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

BSC_TEST_ASSET = os.getenv("BSC_TEST_ASSET", "")
BSC_TEST_ASSET_NAME = os.getenv("BSC_TEST_ASSET_NAME", "DA HULU")
BSC_TEST_ASSET_VERSION = os.getenv("BSC_TEST_ASSET_VERSION", "1")
BSC_TEST_AMOUNT = os.getenv("BSC_TEST_AMOUNT", "1000")

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

routes: RoutesConfig = {}

if TRON_PAY_TO:
    tron_accept = PaymentOption(
        scheme="exact",
        network="tron:nile",
        pay_to=TRON_PAY_TO,
        price=TRON_PRICE,
    )
    routes["/protected-nile"] = RouteConfig(accepts=tron_accept)

if BSC_PAY_TO and BSC_TEST_ASSET:
    bsc_accept = PaymentOption(
        scheme="exact",
        network="eip155:97",
        pay_to=BSC_PAY_TO,
        price={
            "amount": BSC_TEST_AMOUNT,
            "asset": BSC_TEST_ASSET,
            "extra": {
                "name": BSC_TEST_ASSET_NAME,
                "version": BSC_TEST_ASSET_VERSION,
            },
        },
    )
    routes["/protected-bsc-testnet"] = RouteConfig(accepts=bsc_accept)

if TRON_PAY_TO and BSC_PAY_TO and BSC_TEST_ASSET:
    routes["/protected-multi"] = RouteConfig(accepts=[tron_accept, bsc_accept])
elif TRON_PAY_TO:
    routes["/protected"] = RouteConfig(accepts=tron_accept)
elif BSC_PAY_TO and BSC_TEST_ASSET:
    routes["/protected"] = RouteConfig(accepts=bsc_accept)

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
        "endpoints": list(routes.keys()),
        "facilitator": FACILITATOR_URL,
        "price": {
            "tron:nile": TRON_PRICE if TRON_PAY_TO else None,
            "eip155:97": BSC_TEST_AMOUNT if BSC_PAY_TO and BSC_TEST_ASSET else None,
        },
    }


def protected_resource(request: Request):
    """Payment-protected resource."""
    adapter = FastAPIAdapter(request)
    ctx = HTTPRequestContext(
        adapter=adapter,
        path=adapter.get_path(),
        method=adapter.get_method(),
        payment_header=adapter.get_header("Authorization") or adapter.get_header("x-402-payment")
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


@app.get("/protected")
@app.get("/protected-nile")
@app.get("/protected-bsc-testnet")
@app.get("/protected-multi")
def protected_resource_route(request: Request):
    return protected_resource(request)


# ---------------------------------------------------------------------------
# Start
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("X402 Protected Resource Server (Python / v2 SDK)")
    print("=" * 60)
    print(f"  Port:        {SERVER_PORT}")
    print(f"  Facilitator: {FACILITATOR_URL}")
    print(f"  TRON Price:  {TRON_PRICE if TRON_PAY_TO else '(disabled)'}")
    print(
        f"  BSC Price:   "
        f"{BSC_TEST_AMOUNT} {BSC_TEST_ASSET_NAME if BSC_PAY_TO and BSC_TEST_ASSET else '(disabled)'}"
    )
    print(f"  TRON Pay To: {TRON_PAY_TO}")
    print(f"  BSC Pay To:  {BSC_PAY_TO}")
    print(f"  Endpoints:   {', '.join(routes.keys())}")
    print("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=SERVER_PORT, log_level="info")


if __name__ == "__main__":
    main()
