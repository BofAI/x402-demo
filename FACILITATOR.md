# Facilitator Documentation

## Overview

The TypeScript facilitator in [`ts/facilitator.ts`](./ts/facilitator.ts) verifies payment payloads
and settles them on-chain for the demo.

The default path is `tron:nile exact`. If BSC env vars are present, the same facilitator also
registers `eip155:97 exact`.

## Supported Networks

- `tron:nile`
- `eip155:97` when BSC testnet configuration is provided

## Environment Variables

Required TRON configuration:

```env
TRON_FACILITATOR_PRIVATE_KEY=<your_nile_facilitator_private_key>
FACILITATOR_PORT=8011
```

Optional BSC configuration:

```env
BSC_FACILITATOR_PRIVATE_KEY=<your_bsc_testnet_facilitator_private_key>
BSC_TESTNET_RPC_URL=<your_bsc_testnet_rpc>
```

Optional retry tuning used by both the demo server and MCP server:

```env
FACILITATOR_RETRY_MS=3000
```

## API Endpoints

| Endpoint | Method | Description |
| --- | --- | --- |
| `/` | `GET` | Health check |
| `/supported` | `GET` | Advertised supported schemes and networks |
| `/verify` | `POST` | Verifies a payment payload against requirements |
| `/settle` | `POST` | Settles a verified payment on-chain |

## Usage

```bash
./start.sh ts-facilitator
```

The facilitator logs each verify/settle step and prints the settlement transaction hash when
successful.

## Operational Notes

- BSC settlement submissions are serialized in-process to avoid nonce collisions from concurrent
  requests.
- The facilitator must have chain-native gas funds:
  - TRON facilitator: TRX
  - BSC facilitator: testnet BNB

## Troubleshooting

- If `/supported` is empty or missing BSC, verify the optional BSC env vars are filled.
- If settlement fails on BSC, first check RPC stability and facilitator gas balance.
- If TRON requests fail under rate limits, set `TRON_GRID_API_KEY`.
