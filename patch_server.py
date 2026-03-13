with open("server/main.py", "r") as f:
    text = f.read()
lines = text.split("\n")

imports = """
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn

from bankofai.x402 import x402ResourceServer
from bankofai.x402.http import HTTPFacilitatorClient, PaymentOption
from bankofai.x402.http.decorators.fastapi import x402_app
from bankofai.x402.mechanisms.evm.exact import register_exact_evm_server
from bankofai.x402.mechanisms.tron import register_exact_tron_server
"""
new_content = "\n".join(lines[:10]) + imports + "\n".join(lines[30:57])

init_block = """
# ---------------------------------------------------------------------------
# Initialize Resource Server (async)
# ---------------------------------------------------------------------------

facilitator_client = HTTPFacilitatorClient(FACILITATOR_URL)
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
    await resource_server.initialize()

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
"""

new_content += init_block

with open("server/main.py", "w") as f:
    f.write(new_content)
