import os
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import uvicorn

from bankofai.x402 import AssetAmount, x402ResourceServer
from bankofai.x402.http import HTTPFacilitatorClient, PaymentOption, FacilitatorConfig
from bankofai.x402.http.middleware.fastapi import PaymentMiddlewareASGI
from bankofai.x402.http.types import RouteConfig
from bankofai.x402.mechanisms.evm.exact import ExactEvmServerScheme
from bankofai.x402.mechanisms.tron import ExactTronServerScheme

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from python_sdk_info import format_installed_x402_sdk_info

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
FACILITATOR_URL = os.getenv("FACILITATOR_URL", "http://localhost:8001")
SERVER_PORT = int(os.getenv("SERVER_PORT", "8000"))

DEMO_IMAGE_PATH = Path(__file__).resolve().parent / "protected.png"
DEMO_IMAGE_MEDIA_TYPE = "image/png"

if not DEMO_IMAGE_PATH.exists():
    raise FileNotFoundError(f"Missing demo image: {DEMO_IMAGE_PATH}")

# ---------------------------------------------------------------------------
# Network Configurations
# ---------------------------------------------------------------------------
# To add a new network, just append a new entry here. No other code changes needed.
#
# Required fields:
#   network_id     - chain identifier (e.g. "tron:nile", "eip155:97")
#   scheme_class   - server scheme class to register
#   pay_to_env     - env var name for the pay-to address
#   route_suffix   - URL path suffix (route becomes /protected-{suffix})
#   description    - human-readable route description
#   payment_kwargs - extra kwargs passed to PaymentOption (price, assets, etc.)
#
NETWORK_CONFIGS = [
    {
        "network_id": "tron:nile",
        "scheme_class": ExactTronServerScheme,
        "pay_to_env": "TRON_NILE_PAY_TO",
        "route_suffix": "nile",
        "description": "TRON Nile protected demo image",
        "payment_kwargs": {
            "price": {
                "amount": os.getenv("TRON_PROTECTED_PRICE", "0.01"),
                "asset": "TXYZopYRdj2D9XRtbG411XZZ3kM5VkAeBf",
                "extra": {
                    "name": "Tether USD",
                    "version": "1",
                    "assetTransferMethod": "permit2",
                },
            },
        },
    },
    {
        "network_id": "eip155:97",
        "scheme_class": ExactEvmServerScheme,
        "pay_to_env": "BSC_TESTNET_PAY_TO",
        "route_suffix": "bsc-testnet",
        "description": "BSC testnet protected demo image",
        "payment_kwargs": {
            "price": os.getenv("BSC_TEST_PRICE", "0.01"),
            "assets": [
                a.strip()
                for a in os.getenv("BSC_TEST_ASSETS", "USDT,USDC").split(",")
                if a.strip()
            ],
        },
    },
    # --- Mainnet ---
    {
        "network_id": "tron:mainnet",
        "scheme_class": ExactTronServerScheme,
        "pay_to_env": "TRON_MAINNET_PAY_TO",
        "route_suffix": "tron-mainnet",
        "description": "TRON Mainnet protected demo image",
        "payment_kwargs": {
            "price": {
                "amount": os.getenv("TRON_MAINNET_PRICE", "0.01"),
                "asset": "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
                "extra": {
                    "name": "Tether USD",
                    "version": "1",
                    "assetTransferMethod": "permit2",
                },
            },
        },
    },
    {
        "network_id": "eip155:56",
        "scheme_class": ExactEvmServerScheme,
        "pay_to_env": "BSC_MAINNET_PAY_TO",
        "route_suffix": "bsc-mainnet",
        "description": "BSC Mainnet protected demo image",
        "payment_kwargs": {
            "price": os.getenv("BSC_MAINNET_PRICE", "0.01"),
            "asset": "0x55d398326f99059fF775485246999027B3197955",
        },
    },
]

# ---------------------------------------------------------------------------
# Build from config — no manual wiring needed below this line
# ---------------------------------------------------------------------------
facilitator_client = HTTPFacilitatorClient(FacilitatorConfig(url=FACILITATOR_URL))
resource_server = x402ResourceServer(facilitator_client)

active_networks = []
all_payment_options = []
routes = {}

for cfg in NETWORK_CONFIGS:
    pay_to = os.getenv(cfg["pay_to_env"], "")
    if not pay_to:
        logger.warning(f"Skipping {cfg['network_id']}: {cfg['pay_to_env']} not set")
        continue

    logger.info(f"Registering scheme for {cfg['network_id']}...")
    resource_server.register(cfg["network_id"], cfg["scheme_class"]())

    option = PaymentOption(
        scheme="exact",
        network=cfg["network_id"],
        pay_to=pay_to,
        **cfg["payment_kwargs"],
    )

    suffix = cfg["route_suffix"]
    routes[f"GET /protected-{suffix}"] = RouteConfig(
        accepts=[option],
        mime_type=DEMO_IMAGE_MEDIA_TYPE,
        description=cfg["description"],
    )

    all_payment_options.append(option)
    active_networks.append(cfg)
    logger.debug(f"  PayTo={pay_to}, route=/protected-{suffix}")

if not active_networks:
    raise ValueError(
        "No networks configured. Set at least one pay-to address env var: "
        + ", ".join(c["pay_to_env"] for c in NETWORK_CONFIGS)
    )

# Multi-chain route (combines all active networks)
if len(all_payment_options) > 1:
    routes["GET /protected-multi"] = RouteConfig(
        accepts=all_payment_options,
        mime_type=DEMO_IMAGE_MEDIA_TYPE,
        description="Multi-chain protected demo image",
    )

resource_server.initialize()

logger.info(
    f"Starting x402-demo server on port {SERVER_PORT} "
    f"with {len(active_networks)} network(s): "
    + ", ".join(c["network_id"] for c in active_networks)
)

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

app.add_middleware(PaymentMiddlewareASGI, routes=routes, server=resource_server)

# ---------------------------------------------------------------------------
# Route Handlers (dynamically generated from config)
# ---------------------------------------------------------------------------
@app.get("/")
async def index():
    return {
        "service": "X402 Protected Server (ASGI Edition)",
        "resource": "Protected demo image",
        "networks": [c["network_id"] for c in active_networks],
        "routes": list(routes.keys()),
    }


def _make_handler(suffix: str, network_id: str):
    """Factory to create a route handler with proper closure."""
    async def handler():
        logger.info(f"Client accessed /protected-{suffix} after valid {network_id} payment!")
        return FileResponse(
            DEMO_IMAGE_PATH,
            media_type=DEMO_IMAGE_MEDIA_TYPE,
            filename=DEMO_IMAGE_PATH.name,
        )
    handler.__name__ = f"protected_{suffix.replace('-', '_')}"
    return handler


for cfg in active_networks:
    suffix = cfg["route_suffix"]
    app.get(f"/protected-{suffix}")(_make_handler(suffix, cfg["network_id"]))

if len(all_payment_options) > 1:
    @app.get("/protected-multi")
    async def protected_multi():
        logger.info("Client accessed /protected-multi after valid multi-chain payment!")
        return FileResponse(
            DEMO_IMAGE_PATH,
            media_type=DEMO_IMAGE_MEDIA_TYPE,
            filename=DEMO_IMAGE_PATH.name,
        )


def main():
    print("=" * 60)
    print("X402 Protected Resource Server")
    print("=" * 60)
    for line in format_installed_x402_sdk_info():
        print(line)
    print(f"\nListening on http://0.0.0.0:{SERVER_PORT}")
    print(f"\nActive endpoints ({len(active_networks)} network(s)):")
    print(f"  GET /")
    for route_key, route_cfg in routes.items():
        print(f"  {route_key}  [{route_cfg.description}]")
    print("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=SERVER_PORT, log_level="info")


if __name__ == "__main__":
    main()
