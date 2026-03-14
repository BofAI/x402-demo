# X402 Demo

## Overview

The **X402 Demo** provides a practical demonstration of integrating the **x402 payment protocol** with TRON and BSC. The primary accepted path remains the **TypeScript v2 demo on TRON Nile**, and the same app can optionally expose a **BSC testnet** endpoint using the new SDK stack:

- `@bankofai/x402-core`
- `@bankofai/x402-tron`
- `@bankofai/x402-evm`
- `@bankofai/x402-mcp`

Legacy Python, old TypeScript client examples, and broader A2A experiments remain in the repository, but they are not part of the current TypeScript acceptance path.

## Start Here

If you are new to this repository, use the **TypeScript v2 path only**:

1. Copy [`.env.sample`](./.env.sample) to `.env`
2. Run `npm run bootstrap:local-sdk`
3. Start:
   - `./start.sh ts-facilitator`
   - `./start.sh ts-server`
   - `./start.sh ts-client`

Use the Python folders only if you explicitly need to inspect or maintain the legacy/demo flow.
They are still useful as references, but they are **not** the primary setup path for new developers.

### Payment Workflow

The demo simulates a payment workflow involving three conceptual agents:
1. The **Client** requests access to a protected resource from the **Server**.
2. Upon receiving a `402 Payment Required` challenge, the Client signs the selected payment payload for the advertised transfer method (`eip3009` or `permit2`).
3. The **Facilitator** validates the signed payment payload and settles the transaction on-chain.
4. Once payment is confirmed, the Server delivers the protected demo image resource.

---

## Table of Contents
1. [Core Components](#core-components)
2. [Supported Network](#supported-network)
3. [Environment Setup](#environment-setup)
4. [Quick Start](#quick-start)
5. [Project Structure](#project-structure)
6. [License](#license)
7. [Additional Documentation](#additional-documentation)

---

## Core Components

### Server (Resource Provider)
- Hosts protected resources requiring blockchain-based payments.
- Validates cryptographic payment receipts via the Facilitator.
- Supports per-endpoint pricing using the `exact` scheme on `tron:nile` and optional `eip155:97`.

### Facilitator (Payment Processor)
- Validates signed payment payloads and settles transactions on-chain.
- Validates and settles TRON `exact` payments (`eip3009` / `permit2`) on Nile.
- Validates and settles BSC testnet `exact` payments, including `permit2` for public `USDT` / `USDC`.

### Client (Resource Requester)
- **TypeScript CLI** — Uses `x402Client` and `ExactTronScheme` from the new SDK.
- **Python CLI / A2A** — Legacy/demo components remain in the repo but are not part of the new SDK acceptance path.

---

## Supported Network

| Network | Chain ID | Payment Scheme | Transfer Methods |
|---------|----------|----------------|------------------|
| TRON Nile (testnet) | `tron:nile` | `exact` | `eip3009`, `permit2` |
| BSC Testnet (optional) | `eip155:97` | `exact` | `permit2` |

Endpoints exposed by the TypeScript demo:
- `/protected-nile` — TRON-only
- `/protected-bsc-testnet` — BSC-only
- `/protected-multi` — advertises both networks in one `402` response

---

## Environment Setup

### Prerequisites
- **Node.js 18+** (for TypeScript client)
- **npm** (for bootstrap/install helpers)
- **Python 3.11+** only if you need the legacy Python demo components

### Configuration

Copy `.env.sample` to `.env` and fill in your values:

```env
# Required
TRON_CLIENT_PRIVATE_KEY=<your_nile_client_private_key>
TRON_FACILITATOR_PRIVATE_KEY=<your_nile_facilitator_private_key>
PAY_TO_ADDRESS=<server_recipient_tron_address>

# Optional
TRON_GRID_API_KEY=<your_trongrid_api_key>

# Service URLs (defaults)
SERVER_PORT=8000
FACILITATOR_PORT=8001
SERVER_URL=http://localhost:8000
FACILITATOR_URL=http://localhost:8001
ENDPOINT=/protected-nile
PREFERRED_NETWORK=

# Optional BSC endpoint
BSC_CLIENT_PRIVATE_KEY=<your_bsc_testnet_client_private_key>
BSC_FACILITATOR_PRIVATE_KEY=<your_bsc_testnet_facilitator_private_key>
BSC_PAY_TO=<your_bsc_recipient_address>
BSC_TESTNET_RPC_URL=<your_bsc_testnet_rpc>
BSC_TEST_PRICE=0.0001
BSC_TEST_ASSETS=USDT,USDC
```

For BSC demo runs, prefer a stable RPC provider. Public endpoints with strict rate limits can cause settlement to fail even when the payment payload is valid.

---

## Quick Start

### Step 1: Install the TypeScript v2 demo dependencies

```bash
npm run bootstrap:local-sdk
```

This installs the local v2 SDK packages used by:
- `ts/server.ts`
- `ts/facilitator.ts`
- `ts/client.ts`
- `ts/mcp-server.ts`
- `ts/mcp-client.ts`

### Step 2: Start Services

Start the facilitator and server:

```bash
# Start TypeScript Facilitator
./start.sh ts-facilitator

# Start TypeScript Server (in a new terminal)
./start.sh ts-server
```

If dependencies are missing, the TypeScript commands also trigger the local SDK bootstrap automatically.
The TypeScript server and MCP server retry facilitator synchronization on startup, so they no longer
require a manual restart if the facilitator comes up a few seconds later.

### Step 3: Run a Client

**TypeScript CLI:**
```bash
./start.sh ts-client
```

To exercise the optional BSC endpoint:

```bash
ENDPOINT=/protected-bsc-testnet ./start.sh ts-client
```

This path expects the BSC variables above to be filled and by default accepts public BSC testnet `USDT` and `USDC` via the built-in asset registry on `eip155:97`.

To exercise a single endpoint that advertises both TRON and BSC, use:

```bash
ENDPOINT=/protected-multi PREFERRED_NETWORK=tron:nile ./start.sh ts-client
```

or:

```bash
ENDPOINT=/protected-multi PREFERRED_NETWORK=eip155:97 ./start.sh ts-client
```

If `PREFERRED_NETWORK` is omitted, the client falls back to the first option in `accepts`.

### Optional: Run the MCP Demo

Start the MCP server against the same local facilitator:

```bash
./start.sh ts-mcp-server
```

Then run the MCP client smoke flow:

```bash
./start.sh ts-mcp-client
```

The MCP demo uses SSE transport on `http://localhost:4022/sse` and calls:
- `ping` (free)
- `get_weather` (paid via `tron:nile` `exact`)

## Legacy Python Path

The repository still contains Python demo components under:
- [`server/`](./server)
- [`facilitator/`](./facilitator)
- [`client/python/`](./client/python)

These use the Python `bankofai.x402` package plus `tronpy`, and are kept for compatibility/demo
purposes. Their routes now mirror the main demo endpoints (`/protected-nile`, `/protected-bsc-testnet`,
`/protected-multi`) so the network and token defaults stay aligned. If you intentionally want that path:

```bash
./install_deps.sh
./start.sh facilitator
./start.sh server
./start.sh client
```

If you only want the current v2 demo, **do not start here**. Use the TypeScript path above.

## Project Structure

```
├── ts/                  # TypeScript server / facilitator / client
├── ts/mcp-server.ts     # MCP SSE server with paid tools
├── ts/mcp-client.ts     # MCP client smoke test
├── scripts/             # Local SDK bootstrap helper
├── start.sh             # Unified startup script
└── .env.sample          # Environment variables template
```

---

## License

This project is open source under the **MIT License**. See the [LICENSE](LICENSE.md) file for more information.

---

## Additional Documentation

- **System Architecture:** [ARCHITECTURE.md](ARCHITECTURE.md)
- **Server Details:** [SERVER.md](SERVER.md)
- **Facilitator Details:** [FACILITATOR.md](FACILITATOR.md)
- **Client Details:** [CLIENT.md](CLIENT.md)
