"""
Facilitator Main Entry Point
Starts a FastAPI server for facilitator operations with full payment flow support.
"""

import asyncio
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from bankofai.x402.logging_config import setup_logging
from bankofai.x402.facilitator import X402Facilitator
from bankofai.x402.mechanisms.tron.exact_gasfree.facilitator import (
    ExactGasFreeFacilitatorMechanism,
)
from bankofai.x402.utils.gasfree import GasFreeAPIClient
from bankofai.x402.mechanisms.tron.exact_permit import ExactPermitTronFacilitatorMechanism
from bankofai.x402.mechanisms.evm.exact_permit import ExactPermitEvmFacilitatorMechanism
from bankofai.x402.mechanisms.evm.exact import ExactEvmFacilitatorMechanism
from bankofai.x402.signers.facilitator import TronFacilitatorSigner, EvmFacilitatorSigner
from bankofai.x402.config import NetworkConfig
from bankofai.x402.tokens import TokenRegistry
from bankofai.x402.types import (
    PaymentPayload,
    PaymentRequirements,
)
from pydantic import BaseModel


class VerifyRequest(BaseModel):
    """Verify request model"""
    paymentPayload: PaymentPayload
    paymentRequirements: PaymentRequirements


class SettleRequest(BaseModel):
    """Settle request model"""
    paymentPayload: PaymentPayload
    paymentRequirements: PaymentRequirements


class FeeQuoteRequest(BaseModel):
    """Fee quote request model"""
    accepts: list[PaymentRequirements]
    paymentPermitContext: dict | None = None

# Setup logging
setup_logging()

# Load environment variables
load_dotenv(Path(__file__).parent / ".env")
load_dotenv(Path(__file__).parent.parent / ".env")

# Facilitator configuration
FACILITATOR_HOST = "0.0.0.0"
FACILITATOR_PORT = 8001
# TRON supported networks
TRON_NETWORKS = ["mainnet", "shasta", "nile"]

# Fee config per token (smallest unit)
TRON_BASE_FEE = {
    "USDT": 100,       # 0.0001 USDT (6 decimals)
    "USDD": 100_000_000_000_000,  # 0.0001 USDD (18 decimals)
}
BSC_BASE_FEE = {
    "USDT": 100_000_000_000_000,      # 0.0001 USDT (18 decimals on BSC testnet)
    "USDC": 100_000_000_000_000,      # 0.0001 USDC (18 decimals on BSC testnet)
}
BSC_MAINNET_BASE_FEE = {
    "EPS": 100_000_000_000_000,       # 0.0001 EPS (18 decimals on BSC mainnet)
}

# Initialize X402Facilitator
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Register all mechanisms with async wallet initialization."""
    tron_signer = await TronFacilitatorSigner.create()

    # Register TRON mechanisms
    for network in TRON_NETWORKS:
        mechanism = ExactPermitTronFacilitatorMechanism(
            tron_signer,
            base_fee=TRON_BASE_FEE,
        )
        facilitator.register([f"tron:{network}"], mechanism)

        # Add GasFree support for Nile and Mainnet (USDT only; enforced by server pricing)
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

    bsc_signer = await EvmFacilitatorSigner.create()
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

    print(f"BSC  Facilitator Address: {bsc_facilitator_address}")
    print(f"BSC  Base Fee: {BSC_BASE_FEE}")

    print("=" * 80)
    print("X402 Payment Facilitator - Configuration")
    print("=" * 80)
    print(f"TRON Base Fee: {TRON_BASE_FEE}")
    print(f"GasFree Nile Enabled: {gasfree_enabled_nile}")
    print(f"GasFree Mainnet Enabled: {gasfree_enabled_mainnet}")
    print(f"Supported Networks: {', '.join(all_networks)}")

    print(f"\nNetwork Details:")
    for network_key in all_networks:
        print(f"  {network_key}:")
        print(f"    PaymentPermit: {NetworkConfig.get_payment_permit_address(network_key)}")
        tokens = TokenRegistry.get_network_tokens(network_key)
        if tokens:
            for symbol, info in tokens.items():
                print(f"    {symbol}: {info.address} (decimals={info.decimals})")
    print("=" * 80)
    yield


# Initialize FastAPI app
app = FastAPI(
    title="X402 Facilitator",
    description="Facilitator service for X402 payment protocol",
    version="1.0.0",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/supported")
def supported():
    """Get supported capabilities"""
    return facilitator.supported()


@app.post("/fee/quote")
async def fee_quote(request: FeeQuoteRequest):
    """
    Get fee quote for payment requirements
    
    Args:
        request: Fee quote request with payment requirements
        
    Returns:
        Fee quote response with fee details
    """
    try:
        return await facilitator.fee_quote(request.accepts, request.paymentPermitContext)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/verify")
async def verify(request: VerifyRequest):
    """
    Verify payment payload
    
    Args:
        request: Verify request with payment payload and requirements
        
    Returns:
        Verification result
    """
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"[VERIFY REQUEST] Payload: {request.paymentPayload.model_dump(by_alias=True)}")
    
    try:
        result = await facilitator.verify(request.paymentPayload, request.paymentRequirements)
        logger.info(f"[VERIFY RESULT] {result.model_dump(by_alias=True)}")
        return result
    except Exception as e:
        logger.error(f"[VERIFY ERROR] {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/settle")
async def settle(request: SettleRequest):
    """
    Settle payment on-chain
    
    Args:
        request: Settle request with payment payload and requirements
        
    Returns:
        Settlement result with transaction hash
    """
    try:
        return await facilitator.settle(request.paymentPayload, request.paymentRequirements)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def main():
    """Start the facilitator server"""
    print("\n" + "=" * 80)
    print("Starting X402 Facilitator Server")
    print("=" * 80)
    print(f"Host: {FACILITATOR_HOST}")
    print(f"Port: {FACILITATOR_PORT}")
    print(f"Supported Networks: {', '.join(all_networks)}")
    print("=" * 80)
    print("\nEndpoints:")
    print(f"  GET  http://{FACILITATOR_HOST}:{FACILITATOR_PORT}/supported")
    print(f"  POST http://{FACILITATOR_HOST}:{FACILITATOR_PORT}/fee/quote")
    print(f"  POST http://{FACILITATOR_HOST}:{FACILITATOR_PORT}/verify")
    print(f"  POST http://{FACILITATOR_HOST}:{FACILITATOR_PORT}/settle")
    print("=" * 80 + "\n")
    
    uvicorn.run(
        app,
        host=FACILITATOR_HOST,
        port=FACILITATOR_PORT,
        log_level="info",
    )


if __name__ == "__main__":
    main()
