#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "== x402-demo QA smoke =="

echo
echo "== TypeScript demo typecheck =="
npx --prefix facilitator-ts tsc -p facilitator-ts/tsconfig.json --noEmit
npx --prefix server-ts tsc -p server-ts/tsconfig.json --noEmit
npx --prefix client/typescript tsc -p client/typescript/tsconfig.json --noEmit

echo
echo "== Python facilitator API smoke =="
PYTHON_BIN="${PYTHON_BIN:-$SCRIPT_DIR/.venv/bin/python}"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="python"
fi

"$PYTHON_BIN" - <<'PY'
from bankofai.x402.mechanisms.evm.exact.facilitator import ExactEvmFacilitatorMechanism
from bankofai.x402.mechanisms.evm.exact_permit.facilitator import ExactPermitEvmFacilitatorMechanism
from bankofai.x402.mechanisms.tron.exact.facilitator import ExactTronFacilitatorMechanism
from bankofai.x402.mechanisms.tron.exact_gasfree.facilitator import ExactGasFreeFacilitatorMechanism
from bankofai.x402.mechanisms.tron.exact_permit import ExactPermitTronFacilitatorMechanism


class Signer:
    def get_address(self):
        return "TFeeAddress"

    async def verify_typed_data(self, *args, **kwargs):
        return True

    async def write_contract(self, *args, **kwargs):
        return "tx"

    async def check_balance(self, *args, **kwargs):
        return 10**18

    async def wait_for_transaction_receipt(self, *args, **kwargs):
        return {"status": "confirmed"}


class GasFreeClient:
    async def get_providers(self):
        return [{"address": "TFeeAddress"}]

    async def submit(self, *args, **kwargs):
        return "trace"

    async def wait_for_success(self, *args, **kwargs):
        return {"txnHash": "tx"}


signer = Signer()
mechanisms = [
    ExactEvmFacilitatorMechanism(signer),
    ExactPermitEvmFacilitatorMechanism(signer, base_fee={"USDT": 1}),
    ExactTronFacilitatorMechanism(signer),
    ExactPermitTronFacilitatorMechanism(signer, base_fee={"USDT": 1}),
    ExactGasFreeFacilitatorMechanism(
        signer,
        clients={"tron:nile": GasFreeClient()},
        base_fee={"USDT": 1},
    ),
]

for mechanism in mechanisms:
    assert callable(getattr(mechanism, "fee_quote"))
    assert callable(getattr(mechanism, "verify"))
    assert callable(getattr(mechanism, "settle"))
    print(f"{mechanism.__class__.__name__}: {mechanism.scheme()} fee_quote verify settle OK")
PY

echo
echo "QA smoke passed."
