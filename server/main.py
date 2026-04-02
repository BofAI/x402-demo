import io
import logging
import os
import threading
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from PIL import Image, ImageDraw, ImageFont

from bankofai.x402.config import NetworkConfig
from bankofai.x402.facilitator import FacilitatorClient
from bankofai.x402.fastapi import x402_protected
from bankofai.x402.mechanisms.evm.exact import ExactEvmServerMechanism
from bankofai.x402.mechanisms.evm.exact_permit import ExactPermitEvmServerMechanism
from bankofai.x402.mechanisms.tron.exact_gasfree.server import ExactGasFreeServerMechanism
from bankofai.x402.mechanisms.tron.exact_permit import ExactPermitTronServerMechanism
from bankofai.x402.server import X402Server
from bankofai.x402.tokens import TokenRegistry

load_dotenv(Path(__file__).parent.parent / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logging.getLogger("bankofai.x402").setLevel(logging.DEBUG)
logging.getLogger("bankofai.x402.server").setLevel(logging.DEBUG)
logging.getLogger("bankofai.x402.fastapi").setLevel(logging.DEBUG)
logging.getLogger("bankofai.x402.utils").setLevel(logging.DEBUG)
logging.getLogger("uvicorn.access").setLevel(logging.INFO)

logger = logging.getLogger(__name__)

app = FastAPI(title="X402 Server", description="Protected resource server")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

PAY_TO_ADDRESS = os.getenv("PAY_TO_ADDRESS")
BSC_PAY_TO_ADDRESS = os.getenv("BSC_PAY_TO_ADDRESS") or os.getenv("BSC_PAY_TO", "")
if not PAY_TO_ADDRESS:
    raise ValueError("PAY_TO_ADDRESS environment variable is required")

gasfree_api_key_nile = os.getenv("GASFREE_API_KEY_NILE") or os.getenv("GASFREE_API_KEY")
gasfree_api_secret_nile = os.getenv("GASFREE_API_SECRET_NILE") or os.getenv("GASFREE_API_SECRET")
gasfree_enabled_nile = bool(gasfree_api_key_nile and gasfree_api_secret_nile)

gasfree_api_key_mainnet = os.getenv("GASFREE_API_KEY_MAINNET") or os.getenv("GASFREE_API_KEY")
gasfree_api_secret_mainnet = os.getenv("GASFREE_API_SECRET_MAINNET") or os.getenv("GASFREE_API_SECRET")
gasfree_enabled_mainnet = bool(gasfree_api_key_mainnet and gasfree_api_secret_mainnet)

CURRENT_NETWORK = NetworkConfig.TRON_NILE

FACILITATOR_URL = os.getenv("FACILITATOR_URL", "http://localhost:8001")
FACILITATOR_API_KEY = os.getenv("FACILITATOR_API_KEY", "")
SERVER_HOST = os.getenv("SERVER_HOST", "0.0.0.0")
SERVER_PORT = int(os.getenv("SERVER_PORT", "8000"))

PROTECTED_IMAGE_PATH = Path(__file__).parent / "protected.png"

_request_count_lock = threading.Lock()
_request_count = 0

server = X402Server()
if gasfree_enabled_nile:
    server.register(NetworkConfig.TRON_NILE, ExactGasFreeServerMechanism())
if gasfree_enabled_mainnet:
    server.register(NetworkConfig.TRON_MAINNET, ExactGasFreeServerMechanism())
if BSC_PAY_TO_ADDRESS:
    server.register(NetworkConfig.BSC_TESTNET, ExactPermitEvmServerMechanism())
    server.register(NetworkConfig.BSC_TESTNET, ExactEvmServerMechanism())
    server.register(NetworkConfig.BSC_MAINNET, ExactPermitEvmServerMechanism())
    server.register(NetworkConfig.BSC_MAINNET, ExactEvmServerMechanism())

facilitator_headers = {"X-API-KEY": FACILITATOR_API_KEY} if FACILITATOR_API_KEY else None
facilitator = FacilitatorClient(
    base_url=FACILITATOR_URL,
    headers=facilitator_headers,
)
server.set_facilitator(facilitator)

logger.info(
    "server configured current=%s facilitator=%s tron_pay_to=%s bsc_pay_to=%s",
    CURRENT_NETWORK,
    FACILITATOR_URL,
    PAY_TO_ADDRESS,
    BSC_PAY_TO_ADDRESS or "(disabled)",
)


def generate_protected_image(
    text: str, text_color: tuple[int, int, int, int] = (255, 255, 0, 255)
) -> io.BytesIO:
    with Image.open(PROTECTED_IMAGE_PATH) as base:
        image = base.convert("RGBA")
        draw = ImageDraw.Draw(image)

        try:
            font = ImageFont.truetype("DejaVuSans.ttf", 50)
        except Exception:
            font = ImageFont.load_default()

        x = 16
        y = 16
        padding = 6
        bbox = draw.textbbox((x, y), text, font=font)
        bg = (
            bbox[0] - padding,
            bbox[1] - padding,
            bbox[2] + padding,
            bbox[3] + padding,
        )
        draw.rectangle(bg, fill=(0, 0, 0, 160))
        draw.text(
            (x, y),
            text,
            fill=text_color,
            font=font,
            stroke_width=2,
            stroke_fill=(0, 0, 0, 255),
        )

        buf = io.BytesIO()
        image.save(buf, format="PNG")
        buf.seek(0)
        return buf


@app.get("/")
async def root():
    return {
        "service": "X402 Protected Resource Server",
        "status": "running",
        "pay_to": PAY_TO_ADDRESS,
        "bsc_pay_to": BSC_PAY_TO_ADDRESS or None,
        "facilitator": FACILITATOR_URL,
    }


NILE_PRICES = ["0.0001 USDT", "0.0001 USDD"]
NILE_SCHEMES = ["exact_permit", "exact_permit"]
if gasfree_enabled_nile:
    NILE_PRICES.append("0.0001 USDT")
    NILE_SCHEMES.append("exact_gasfree")


@app.get("/protected-nile")
@x402_protected(
    server=server,
    prices=NILE_PRICES,
    schemes=NILE_SCHEMES,
    network=CURRENT_NETWORK,
    pay_to=PAY_TO_ADDRESS,
)
async def protected_endpoint(request: Request):
    global _request_count
    if not PROTECTED_IMAGE_PATH.exists():
        return {"error": "Protected image not found"}

    with _request_count_lock:
        _request_count += 1
        request_count = _request_count

    buf = generate_protected_image(
        f"req: {request_count}", text_color=(255, 255, 0, 255)
    )
    return StreamingResponse(buf, media_type="image/png")


@app.get("/protected-shasta")
@x402_protected(
    server=server,
    prices=["0.0001 USDT"],
    schemes=["exact_permit"],
    network=NetworkConfig.TRON_SHASTA,
    pay_to=PAY_TO_ADDRESS,
)
async def protected_shasta_endpoint(request: Request):
    global _request_count
    if not PROTECTED_IMAGE_PATH.exists():
        return {"error": "Protected image not found"}

    with _request_count_lock:
        _request_count += 1
        request_count = _request_count

    buf = generate_protected_image(
        f"shasta req: {request_count}", text_color=(0, 255, 0, 255)
    )
    return StreamingResponse(buf, media_type="image/png")


MAINNET_PRICES = ["0.0001 USDT", "0.0001 USDD"]
MAINNET_SCHEMES = ["exact_permit", "exact_permit"]
if gasfree_enabled_mainnet:
    MAINNET_PRICES.append("0.0001 USDT")
    MAINNET_SCHEMES.append("exact_gasfree")


@app.get("/protected-mainnet")
@x402_protected(
    server=server,
    prices=MAINNET_PRICES,
    schemes=MAINNET_SCHEMES,
    network=NetworkConfig.TRON_MAINNET,
    pay_to=PAY_TO_ADDRESS,
)
async def protected_mainnet_endpoint(request: Request):
    global _request_count
    if not PROTECTED_IMAGE_PATH.exists():
        return {"error": "Protected image not found"}

    with _request_count_lock:
        _request_count += 1
        request_count = _request_count

    buf = generate_protected_image(
        f"mainnet req: {request_count}", text_color=(255, 0, 0, 255)
    )
    return StreamingResponse(buf, media_type="image/png")


if BSC_PAY_TO_ADDRESS:

    @app.get("/protected-bsc-testnet")
    @x402_protected(
        server=server,
        prices=["0.0001 USDT", "0.0001 DHLU"],
        schemes=["exact_permit", "exact"],
        network=NetworkConfig.BSC_TESTNET,
        pay_to=BSC_PAY_TO_ADDRESS,
    )
    async def protected_bsc_testnet_endpoint(request: Request):
        global _request_count
        if not PROTECTED_IMAGE_PATH.exists():
            return {"error": "Protected image not found"}

        with _request_count_lock:
            _request_count += 1
            request_count = _request_count

        buf = generate_protected_image(
            f"bsc testnet req: {request_count}",
            text_color=(0, 255, 255, 255),
        )
        return StreamingResponse(buf, media_type="image/png")


    @app.get("/protected-bsc-testnet-json")
    @x402_protected(
        server=server,
        prices=["0.0001 USDT", "0.0001 DHLU"],
        schemes=["exact_permit", "exact"],
        network=NetworkConfig.BSC_TESTNET,
        pay_to=BSC_PAY_TO_ADDRESS,
    )
    async def protected_bsc_testnet_json_endpoint(request: Request):
        global _request_count
        with _request_count_lock:
            _request_count += 1
            request_count = _request_count

        return {
            "ok": True,
            "network": NetworkConfig.BSC_TESTNET,
            "requestCount": request_count,
            "payTo": BSC_PAY_TO_ADDRESS,
        }


    @app.get("/protected-bsc-testnet-coinbase")
    @x402_protected(
        server=server,
        prices=["0.0001 DHLU"],
        schemes=["exact"],
        network=NetworkConfig.BSC_TESTNET,
        pay_to=BSC_PAY_TO_ADDRESS,
    )
    async def protected_bsc_testnet_coinbase_endpoint(request: Request):
        global _request_count
        with _request_count_lock:
            _request_count += 1
            request_count = _request_count

        return {
            "ok": True,
            "impl": "bankofai-demo-server",
            "network": NetworkConfig.BSC_TESTNET,
            "requestCount": request_count,
            "payTo": BSC_PAY_TO_ADDRESS,
        }


    @app.get("/protected-bsc-mainnet")
    @x402_protected(
        server=server,
        prices=["0.0001 EPS"],
        schemes=["exact_permit"],
        network=NetworkConfig.BSC_MAINNET,
        pay_to=BSC_PAY_TO_ADDRESS,
    )
    async def protected_bsc_mainnet_endpoint(request: Request):
        global _request_count
        if not PROTECTED_IMAGE_PATH.exists():
            return {"error": "Protected image not found"}

        with _request_count_lock:
            _request_count += 1
            request_count = _request_count

        buf = generate_protected_image(
            f"bsc mainnet req: {request_count}",
            text_color=(255, 165, 0, 255),
        )
        return StreamingResponse(buf, media_type="image/png")


@app.get("/networks")
async def list_networks():
    registered = {}
    for network in sorted(server._mechanisms.keys()):
        tokens = TokenRegistry.get_network_tokens(network)
        registered[network] = {
            "tokens": sorted(tokens.keys()) if tokens else [],
        }
    return registered


if __name__ == "__main__":
    uvicorn.run(app, host=SERVER_HOST, port=SERVER_PORT, log_level="info")
