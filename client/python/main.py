#!/usr/bin/env python3
"""
X402 Demo - Terminal Client (Multi-Network)

Registers BOTH TRON and EVM mechanisms by default so the client can
handle 402 responses from any supported chain. The server decides
which network(s) to accept; the SDK picks the best affordable option.
"""

import asyncio
import logging
import os
import sys
import tempfile

import httpx
from dotenv import load_dotenv
from eth_account import Account
from eth_account.messages import encode_defunct, encode_typed_data

from bankofai.x402.clients import SufficientBalancePolicy, X402Client, X402HttpClient
from bankofai.x402.config import NetworkConfig
from bankofai.x402.mechanisms.evm.exact import ExactEvmClientMechanism
from bankofai.x402.mechanisms.evm.exact_permit import ExactPermitEvmClientMechanism
from bankofai.x402.mechanisms.tron.exact_gasfree.client import ExactGasFreeClientMechanism
from bankofai.x402.mechanisms.tron.exact_permit import ExactPermitTronClientMechanism
from bankofai.x402.signers.client import EvmClientSigner, TronClientSigner
from bankofai.x402.tokens import TokenRegistry
from bankofai.x402.types import PaymentRequirements
from bankofai.x402.utils.gasfree import GasFreeAPIClient


class PreferGasFreeUSDTPolicy:
    def __init__(self, client: X402Client) -> None:
        self._client = client

    async def apply(self, requirements: list[PaymentRequirements]) -> list[PaymentRequirements]:
        for req in requirements:
            token_info = TokenRegistry.find_by_address(req.network, req.asset)
            if req.scheme == "exact_gasfree" and token_info and token_info.symbol == "USDT":
                print(f"Policy selected {req.scheme} ({token_info.symbol})")
                return [req]
        return requirements


logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

load_dotenv()

RESOURCE_SERVER_URL = os.getenv("SERVER_URL", "http://localhost:8000")
ENDPOINT_PATH = os.getenv("ENDPOINT", "/protected-nile")
PREFERRED_NETWORK = os.getenv("PREFERRED_NETWORK")
BSC_CLIENT_PRIVATE_KEY = os.getenv("BSC_CLIENT_PRIVATE_KEY")
RESOURCE_URL = RESOURCE_SERVER_URL + ENDPOINT_PATH
HTTP_TIMEOUT_SECONDS = float(os.getenv("HTTP_TIMEOUT_SECONDS", "60"))


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


async def main():
    print("=" * 80)
    print("X402 Payment Client (Multi-Network)")
    print("=" * 80)

    tron_signer = None
    try:
        tron_signer = await TronClientSigner.create()
    except Exception as exc:
        if not PREFERRED_NETWORK or not PREFERRED_NETWORK.startswith("tron:"):
            print(f"Skipping TRON signer: {exc}")
        else:
            raise

    if BSC_CLIENT_PRIVATE_KEY:
        evm_wallet = LocalEvmWallet(BSC_CLIENT_PRIVATE_KEY)
        evm_signer = EvmClientSigner(evm_wallet)
        evm_signer.set_address(await evm_wallet.get_address())
    else:
        evm_signer = await EvmClientSigner.create()

    _gf_key_nile = os.getenv("GASFREE_API_KEY_NILE") or os.getenv("GASFREE_API_KEY")
    _gf_secret_nile = os.getenv("GASFREE_API_SECRET_NILE") or os.getenv("GASFREE_API_SECRET")
    _gf_key_shasta = os.getenv("GASFREE_API_KEY_SHASTA") or os.getenv("GASFREE_API_KEY")
    _gf_secret_shasta = os.getenv("GASFREE_API_SECRET_SHASTA") or os.getenv("GASFREE_API_SECRET")
    _gf_key_mainnet = os.getenv("GASFREE_API_KEY_MAINNET") or os.getenv("GASFREE_API_KEY")
    _gf_secret_mainnet = os.getenv("GASFREE_API_SECRET_MAINNET") or os.getenv("GASFREE_API_SECRET")
    gasfree_clients = {
        "tron:nile": GasFreeAPIClient(
            NetworkConfig.get_gasfree_api_base_url("tron:nile"),
            api_key=_gf_key_nile,
            api_secret=_gf_secret_nile,
        ),
        "tron:shasta": GasFreeAPIClient(
            NetworkConfig.get_gasfree_api_base_url("tron:shasta"),
            api_key=_gf_key_shasta,
            api_secret=_gf_secret_shasta,
        ),
        "tron:mainnet": GasFreeAPIClient(
            NetworkConfig.get_gasfree_api_base_url("tron:mainnet"),
            api_key=_gf_key_mainnet,
            api_secret=_gf_secret_mainnet,
        ),
    }

    x402_client = X402Client()
    if tron_signer is not None:
        x402_client.register("tron:*", ExactPermitTronClientMechanism(tron_signer))
        x402_client.register("tron:*", ExactGasFreeClientMechanism(tron_signer, clients=gasfree_clients))
    for bsc_network in [NetworkConfig.BSC_TESTNET, NetworkConfig.BSC_MAINNET]:
        x402_client.register(bsc_network, ExactPermitEvmClientMechanism(evm_signer))
        x402_client.register(bsc_network, ExactEvmClientMechanism(evm_signer))

    x402_client.register_policy(SufficientBalancePolicy)
    if PREFERRED_NETWORK:

        class PreferNetworkPolicy:
            def __init__(self, client: X402Client) -> None:
                self._client = client

            async def apply(
                self, requirements: list[PaymentRequirements]
            ) -> list[PaymentRequirements]:
                preferred = [req for req in requirements if req.network == PREFERRED_NETWORK]
                return preferred or requirements

        x402_client.register_policy(PreferNetworkPolicy)

    print("\nSupported Networks and Tokens:")
    for network_name in ["tron:mainnet", "tron:nile", "tron:shasta", "eip155:97"]:
        tokens = TokenRegistry.get_network_tokens(network_name)
        print(f"  {network_name}:")
        if not tokens:
            print("    (no tokens registered)")
        else:
            for symbol, info in tokens.items():
                print(f"    {symbol}: {info.address} (decimals={info.decimals})")
    print("=" * 80)
    if tron_signer is not None:
        print(f"TRON Address: {tron_signer.get_address()}")
    print(f"BSC Address:  {evm_signer.get_address()}")
    if PREFERRED_NETWORK:
        print(f"Preferred Network: {PREFERRED_NETWORK}")
    print(f"Endpoint: {ENDPOINT_PATH}")
    print("=" * 80)

    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as http_client:
            client = X402HttpClient(http_client, x402_client)

            print(f"\nRequesting: {RESOURCE_URL}")
            response = await client.get(RESOURCE_URL)
            print("\nSuccess")
            print(f"Status: {response.status_code}")
            print(f"Content-Type: {response.headers.get('content-type')}")
            print(f"Content-Length: {len(response.content)} bytes")

            payment_response = response.headers.get("payment-response")
            if payment_response:
                from bankofai.x402.encoding import decode_payment_payload
                from bankofai.x402.types import SettleResponse

                settle_response = decode_payment_payload(payment_response, SettleResponse)
                print("\nPayment Response:")
                print(f"  Success: {settle_response.success}")
                print(f"  Network: {settle_response.network}")
                print(f"  Transaction: {settle_response.transaction}")
                if settle_response.error_reason:
                    print(f"  Error: {settle_response.error_reason}")

            content_type = response.headers.get("content-type", "")
            if "application/json" in content_type:
                print(f"\nResponse: {response.json()}")
            elif "image/" in content_type:
                ext = "png"
                if "jpeg" in content_type or "jpg" in content_type:
                    ext = "jpg"
                elif "webp" in content_type:
                    ext = "webp"

                with tempfile.NamedTemporaryFile(
                    prefix="x402_", suffix=f".{ext}", delete=False, dir="/tmp"
                ) as f:
                    f.write(response.content)
                    saved_path = f.name
                print(f"\nReceived image file, saved to: {saved_path}")
            else:
                print(f"\nResponse (first 200 chars): {response.text[:200]}")

    except httpx.ReadTimeout:
        print()
        print("=" * 80)
        print("ERROR")
        print("=" * 80)
        print(
            "Error: HTTP request timed out. This can happen during on-chain settlement. "
            f"Try increasing HTTP_TIMEOUT_SECONDS (current: {HTTP_TIMEOUT_SECONDS})."
        )
        print()
        import traceback

        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        print(f"\nError: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
