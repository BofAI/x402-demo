# Client Documentation

## Overview

The current acceptance path uses the TypeScript v2 client in [`ts/client.ts`](./ts/client.ts).
It requests a protected demo endpoint, handles the `402 Payment Required` challenge, signs the
selected payment requirement, and retries the request with the payment payload. Successful demo
requests return the protected `openclaw.jpg` asset.

## Supported Demo Paths

- `tron:nile` via `/protected-nile`
- `eip155:97` via `/protected-bsc-testnet` when BSC env vars are configured
- multi-network selection via `/protected-multi`

The client can choose from multiple payment options returned by a single endpoint. Set
`PREFERRED_NETWORK` to select a specific network from the `accepts` list.

## Environment Variables

Required for the default TRON flow:

```env
SERVER_URL=http://localhost:8000
ENDPOINT=/protected-nile
TRON_CLIENT_PRIVATE_KEY=<your_nile_client_private_key>
FACILITATOR_URL=http://localhost:8001
```

Optional for the BSC demo flow:

```env
BSC_CLIENT_PRIVATE_KEY=<your_bsc_testnet_client_private_key>
BSC_TESTNET_RPC_URL=<your_bsc_testnet_rpc>
PREFERRED_NETWORK=eip155:97
```

## Usage

Start the client:

```bash
./start.sh ts-client
```

Run against the optional BSC endpoint:

```bash
ENDPOINT=/protected-bsc-testnet ./start.sh ts-client
```

Run against the shared multi-network endpoint and let the client pick BSC:

```bash
ENDPOINT=/protected-multi PREFERRED_NETWORK=eip155:97 ./start.sh ts-client
```

Run against the shared multi-network endpoint and let the client pick TRON:

```bash
ENDPOINT=/protected-multi PREFERRED_NETWORK=tron:nile ./start.sh ts-client
```

## Expected Flow

1. `GET` the protected endpoint.
2. Receive a `402 Payment Required` response with one or more `accepts`.
3. Select a requirement, create a payment payload, and replay the request.
4. Receive `200 OK` plus a `payment-response` header containing settlement details and a JPEG body.
5. Save the returned image to a temporary file path.

## Troubleshooting

- If the client reports `No payment requirements available`, check that the server synced with
  the facilitator.
- If BSC requests fail, verify the facilitator wallet has testnet BNB and use a stable RPC.
- If `PREFERRED_NETWORK` is set but missing from `accepts`, the client falls back to the first
  advertised option.
