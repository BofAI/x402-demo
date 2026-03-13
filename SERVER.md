# Server Documentation

## Overview

The TypeScript resource server in [`ts/server.ts`](./ts/server.ts) exposes payment-protected
endpoints using `x402ResourceServer`.

It currently supports:

- `tron:nile` on `/protected-nile`
- `eip155:97` on `/protected-bsc-testnet` when BSC env vars are configured
- a combined `/protected-multi` endpoint that advertises both networks in one `402` response

## Environment Variables

Required:

```env
PAY_TO_ADDRESS=<your_tron_pay_to_address>
FACILITATOR_URL=http://localhost:8001
SERVER_PORT=8000
```

Optional BSC endpoint configuration:

```env
BSC_PAY_TO=<your_bsc_recipient_address>
BSC_TESTNET_RPC_URL=<your_bsc_testnet_rpc>
BSC_TEST_ASSET=<your_bsc_test_asset>
BSC_TEST_ASSET_NAME=DA HULU
BSC_TEST_ASSET_VERSION=1
BSC_TEST_AMOUNT=1000
```

Optional retry tuning:

```env
FACILITATOR_RETRY_MS=3000
```

## Endpoints

| Endpoint | Method | Description |
| --- | --- | --- |
| `/` | `GET` | Server metadata and registered demo endpoints |
| `/protected-nile` | `GET` | TRON Nile protected resource |
| `/protected-bsc-testnet` | `GET` | BSC testnet protected resource |
| `/protected-multi` | `GET` | One endpoint advertising both TRON and BSC payment options |

## Usage

```bash
./start.sh ts-server
```

The server now retries facilitator synchronization on startup instead of requiring a manual
restart when the facilitator comes up late.

## Payment Flow

1. Unpaid request returns `402 Payment Required`.
2. The response contains one or more `accepts` entries.
3. The client sends a payment payload in `x-402-payment` or `payment-signature`.
4. The server verifies and settles through the facilitator, then returns the protected JSON body.

## Troubleshooting

- If startup is blocked, check that the facilitator is reachable at `FACILITATOR_URL`.
- If `/protected-multi` only shows one network, verify the optional BSC env vars are present.
- If BSC payments are slow or flaky, switch to a less rate-limited RPC endpoint.
