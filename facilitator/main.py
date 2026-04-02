"""
Facilitator Main Entry Point
Starts a FastAPI server for facilitator operations with full payment flow support.
"""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from eth_account import Account
from eth_account.messages import encode_defunct, encode_typed_data
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from bankofai.x402.config import NetworkConfig
from bankofai.x402.facilitator import X402Facilitator
from bankofai.x402.logging_config import setup_logging
from bankofai.x402.mechanisms.evm.exact import ExactEvmFacilitatorMechanism
from bankofai.x402.mechanisms.evm.exact_permit import ExactPermitEvmFacilitatorMechanism
from bankofai.x402.mechanisms.tron.exact_gasfree.facilitator import (
    ExactGasFreeFacilitatorMechanism,
)
from bankofai.x402.mechanisms.tron.exact_permit import ExactPermitTronFacilitatorMechanism
from bankofai.x402.signers.facilitator import EvmFacilitatorSigner, TronFacilitatorSigner
from bankofai.x402.tokens import TokenRegistry
from bankofai.x402.types import PaymentPayload, PaymentRequirements
from bankofai.x402.utils.gasfree import GasFreeAPIClient


class VerifyRequest(BaseModel):
    paymentPayload: PaymentPayload
    paymentRequirements: PaymentRequirements


class SettleRequest(BaseModel):
    paymentPayload: PaymentPayload
    paymentRequirements: PaymentRequirements


class FeeQuoteRequest(BaseModel):
    accepts: list[PaymentRequirements]
    paymentPermitContext: dict | None = None


setup_logging()
logger = logging.getLogger(__name__)
load_dotenv(Path(__file__).parent / ".env")
load_dotenv(Path(__file__).parent.parent / ".env")

FACILITATOR_HOST = os.getenv("FACILITATOR_HOST", "0.0.0.0")
FACILITATOR_PORT = int(os.getenv("FACILITATOR_PORT", "8001"))
TRON_NETWORKS = ["mainnet", "shasta", "nile"]

TRON_BASE_FEE = {
    "USDT": 100,
    "USDD": 100_000_000_000_000,
}
BSC_BASE_FEE = {
    "USDT": 100_000_000_000_000,
    "USDC": 100_000_000_000_000,
}
BSC_MAINNET_BASE_FEE = {
    "EPS": 100_000_000_000_000,
}

facilitator = X402Facilitator()

gasfree_api_key_nile = os.getenv("GASFREE_API_KEY_NILE") or os.getenv("GASFREE_API_KEY")
gasfree_api_secret_nile = os.getenv("GASFREE_API_SECRET_NILE") or os.getenv("GASFREE_API_SECRET")
gasfree_enabled_nile = bool(gasfree_api_key_nile and gasfree_api_secret_nile)

gasfree_api_key_mainnet = os.getenv("GASFREE_API_KEY_MAINNET") or os.getenv("GASFREE_API_KEY")
gasfree_api_secret_mainnet = os.getenv("GASFREE_API_SECRET_MAINNET") or os.getenv("GASFREE_API_SECRET")
gasfree_enabled_mainnet = bool(gasfree_api_key_mainnet and gasfree_api_secret_mainnet)

gasfree_clients: dict[str, GasFreeAPIClient] = {}
if gasfree_enabled_nile:
    gasfree_clients["tron:nile"] = GasFreeAPIClient(
        NetworkConfig.get_gasfree_api_base_url("tron:nile"),
        api_key=gasfree_api_key_nile,
        api_secret=gasfree_api_secret_nile,
    )
if gasfree_enabled_mainnet:
    gasfree_clients["tron:mainnet"] = GasFreeAPIClient(
        NetworkConfig.get_gasfree_api_base_url("tron:mainnet"),
        api_key=gasfree_api_key_mainnet,
        api_secret=gasfree_api_secret_mainnet,
    )

all_networks = [f"tron:{n}" for n in TRON_NETWORKS] + [NetworkConfig.BSC_MAINNET, NetworkConfig.BSC_TESTNET]


class LocalEvmWallet:
    def __init__(self, private_key: str) -> None:
        key = private_key if private_key.startswith("0x") else f"0x{private_key}"
        self._account = Account.from_key(key)

    async def get_address(self) -> str:
        return self._account.address

    async def sign_message(self, message: bytes) -> str:
        signed = self._account.sign_message(encode_defunct(primitive=message))
        return signed.signature.hex()

    async def sign_typed_data(self, full_data: dict) -> str:
        signed = Account.sign_message(
            encode_typed_data(full_message=full_data),
            private_key=self._account.key,
        )
        return signed.signature.hex()

    async def sign_transaction(self, tx: dict) -> str:
        signed = self._account.sign_transaction(tx)
        raw_tx = signed.raw_transaction.hex()
        return raw_tx[2:] if raw_tx.startswith("0x") else raw_tx


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        tron_signer = await TronFacilitatorSigner.create()

        for network in TRON_NETWORKS:
            mechanism = ExactPermitTronFacilitatorMechanism(
                tron_signer,
                base_fee=TRON_BASE_FEE,
            )
            facilitator.register([f"tron:{network}"], mechanism)

            if network == "nile" and gasfree_enabled_nile:
                gasfree_mechanism = ExactGasFreeFacilitatorMechanism(
                    tron_signer,
                    clients=gasfree_clients,
                    base_fee=TRON_BASE_FEE,
                )
                facilitator.register([f"tron:{network}"], gasfree_mechanism)
            if network == "mainnet" and gasfree_enabled_mainnet:
                gasfree_mechanism = ExactGasFreeFacilitatorMechanism(
                    tron_signer,
                    clients=gasfree_clients,
                    base_fee=TRON_BASE_FEE,
                )
                facilitator.register([f"tron:{network}"], gasfree_mechanism)
    except Exception as exc:
        logger.warning("Skipping TRON facilitator registration: %s", exc)

    bsc_wallet = LocalEvmWallet(os.environ["BSC_FACILITATOR_PRIVATE_KEY"])
    bsc_signer = EvmFacilitatorSigner(bsc_wallet)
    bsc_signer.set_address(await bsc_wallet.get_address())
    bsc_facilitator_address = bsc_signer.get_address()

    bsc_exact_mechanism = ExactPermitEvmFacilitatorMechanism(
        bsc_signer,
        fee_to=bsc_facilitator_address,
        base_fee=BSC_BASE_FEE,
    )
    facilitator.register([NetworkConfig.BSC_TESTNET], bsc_exact_mechanism)

    bsc_native_mechanism = ExactEvmFacilitatorMechanism(bsc_signer)
    facilitator.register([NetworkConfig.BSC_TESTNET], bsc_native_mechanism)

    bsc_mainnet_exact_mechanism = ExactPermitEvmFacilitatorMechanism(
        bsc_signer,
        fee_to=bsc_facilitator_address,
        base_fee=BSC_MAINNET_BASE_FEE,
    )
    facilitator.register([NetworkConfig.BSC_MAINNET], bsc_mainnet_exact_mechanism)

    bsc_mainnet_native_mechanism = ExactEvmFacilitatorMechanism(bsc_signer)
    facilitator.register([NetworkConfig.BSC_MAINNET], bsc_mainnet_native_mechanism)

    print(f"BSC Facilitator Address: {bsc_facilitator_address}")
    yield


app = FastAPI(
    title="X402 Facilitator",
    description="Facilitator service for X402 payment protocol",
    version="1.0.0",
    lifespan=lifespan,
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
    return facilitator.supported()


@app.post("/fee/quote")
async def fee_quote(request: FeeQuoteRequest):
    try:
        return await facilitator.fee_quote(request.accepts, request.paymentPermitContext)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/verify")
async def verify(request: VerifyRequest):
    try:
        return await facilitator.verify(request.paymentPayload, request.paymentRequirements)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/settle")
async def settle(request: SettleRequest):
    try:
        return await facilitator.settle(request.paymentPayload, request.paymentRequirements)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/networks")
async def networks():
    result = {}
    for network_key in all_networks:
        tokens = TokenRegistry.get_network_tokens(network_key)
        result[network_key] = sorted(tokens.keys()) if tokens else []
    return result


if __name__ == "__main__":
    uvicorn.run(
        app,
        host=FACILITATOR_HOST,
        port=FACILITATOR_PORT,
        log_level="info",
    )
