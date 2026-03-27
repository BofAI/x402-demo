# X402 Demo

## Overview

The **X402 Demo** provides a practical demonstration of integrating the **x402 payment protocol** with the TRON and BSC blockchains. It showcases how decentralized micropayments can enable pay-per-access workflows — including gasless transactions via GasFree and multi-agent orchestration via A2A.

### Payment Workflow

The demo simulates a payment workflow involving three conceptual agents:
1. The **Client** requests access to a protected resource from the **Server**.
2. Upon receiving a `402 Payment Required` challenge, the Client signs a cryptographic permit (TIP-712 for TRON, EIP-712 for BSC).
3. The **Facilitator** validates the signed permit and settles the transaction on-chain.
4. Once payment is confirmed, the Server delivers the requested resource.

---

## Table of Contents
1. [Core Components](#core-components)
2. [Supported Networks & Tokens](#supported-networks--tokens)
3. [Environment Setup](#environment-setup)
4. [Quick Start](#quick-start)
5. [A2A Agent Demo](#a2a-agent-demo)
6. [License](#license)
7. [Additional Documentation](#additional-documentation)

---

## Core Components

### Server (Resource Provider)
- Hosts protected resources requiring blockchain-based payments.
- Validates cryptographic payment receipts via the Facilitator.
- Supports per-endpoint pricing with multiple payment schemes (`exact_permit`, `exact_gasfree`).

### Facilitator (Payment Processor)
- Validates signed payment permits and settles transactions on-chain.
- Supports both standard permit-based payments and **GasFree** gasless transactions on TRON.
- Can be self-hosted or use the official hosted service at `https://facilitator.bankofai.io`.

### Client (Resource Requester)
- **Python CLI** — Automates permit signing and resource retrieval.
- **TypeScript CLI** — Feature parity with the Python client, built on `tronweb` and `viem`.
- **Web Client (A2A)** — Interactive React UI with TronLink wallet integration, powered by Google ADK.

---

## Supported Networks & Tokens

| Network | Chain ID | Tokens | Payment Schemes |
|---------|----------|--------|-----------------|
| TRON Nile (testnet) | `tron:nile` | USDT, USDD | `exact_permit`, `exact_gasfree` |
| TRON Shasta (testnet) | `tron:shasta` | USDT | `exact_permit` |
| TRON Mainnet | `tron:mainnet` | USDT, USDD | `exact_permit`, `exact_gasfree` (USDT only) |
| BSC Testnet (optional) | `eip155:97` | USDT, USDC, DHLU | `exact_permit`, `exact` |
| BSC Mainnet (optional) | `eip155:56` | USDC, USDT, EPS | `exact_permit`, `exact` |

> BSC support requires `BSC_PRIVATE_KEY` to be configured.

### GasFree (Gasless Transactions)

GasFree eliminates transaction fees for TRON payments. When enabled, the client can use a custom selection policy (`PreferGasFreeUSDTPolicy`) to automatically prefer gasless transactions. In this demo, GasFree is available on Nile and Mainnet (USDT only) when the corresponding `GASFREE_API_KEY_*` / `GASFREE_API_SECRET_*` values are set.

---

## Environment Setup

### Prerequisites
- **Python 3.9+** (for local execution)
- **Node.js 18+** (for TypeScript client)
- **Docker** (optional, for containerized deployment)

### Agent Wallet Setup

The Python and TypeScript clients use `TronClientSigner.create()` / `EvmClientSigner.create()` (and the facilitator uses `TronFacilitatorSigner.create()` / `EvmFacilitatorSigner.create()`) instead of reading raw private keys directly. These signers are provided by the `@bankofai/agent-wallet` package and load credentials via the **agent-wallet** key store.

**First-time setup:**
```bash
npx agent-wallet init
```
This interactive CLI stores your TRON and EVM private keys in a local encrypted keystore so that `*.create()` calls can resolve them at runtime. Re-run `npx agent-wallet init` whenever you rotate keys.

> **Upgrading from an older version?** If you previously set `TRON_PRIVATE_KEY` / `BSC_PRIVATE_KEY` directly in `.env`, run `npx agent-wallet init` to migrate those keys into the keystore. The raw env-var references are no longer used by the signer classes.

### Configuration

Copy `.env.sample` to `.env` and fill in your values:

```env
# Required
TRON_PRIVATE_KEY=<your_tron_private_key>
PAY_TO_ADDRESS=<server_recipient_tron_address>

# Optional: TronGrid API key for mainnet RPC access
TRON_GRID_API_KEY=<your_trongrid_api_key>

# Optional: BSC support
BSC_PRIVATE_KEY=<your_evm_private_key>
BSC_PAY_TO_ADDRESS=<server_recipient_evm_address>

# Optional: GasFree gasless transactions (per-network)
GASFREE_API_KEY_NILE=<key>
GASFREE_API_SECRET_NILE=<secret>
GASFREE_API_KEY_MAINNET=<key>
GASFREE_API_SECRET_MAINNET=<secret>

# Optional: Facilitator authentication
FACILITATOR_API_KEY=<your_api_key>

# Service URLs (defaults)
SERVER_URL=http://localhost:8000
FACILITATOR_URL=http://localhost:8001
HTTP_TIMEOUT_SECONDS=60
```

See [`.env.sample`](.env.sample) for the full list of configuration options.

---

## Quick Start

### Step 1: Start Services

Start the Facilitator and Server to enable the x402 payment protocol:

**Using Scripts:**
```bash
# Start Facilitator
./start.sh facilitator

# Start Server (in a new terminal)
./start.sh server
```

**Using Docker:**
```bash
docker-compose up -d
```

### Step 2: Run a Client

**Python CLI:**
```bash
./start.sh client
```

**TypeScript CLI:**
```bash
./start.sh client-ts
```

### Step 3: Access via Openclaw Agent

Once services are running, the **openclaw** agent can automatically detect the `402 Payment Required` challenge, sign the necessary permits, settle the payment via the facilitator, and retrieve the resource.

> Ensure the **openclaw** agent has the [openclaw-extension](https://github.com/BofAI/openclaw-extension) enabled to handle x402 protocol operations.

<img src="./assets/openclaw.jpg" alt="openclaw Agent" width="600">

---

## A2A Agent Demo

The A2A (Agent-to-Agent) demo extends x402 with multi-agent orchestration using Google ADK:

- **Merchant Agent** (`a2a-server`) — An LLM-powered agent (Gemini) that requires payment before fulfilling requests.
- **Client Agent** (`a2a-client`) — A web UI where users interact with the Merchant Agent, signing payments locally via TronLink.

### Running the A2A Demo

```bash
# Set GOOGLE_API_KEY in .env first

# Start Merchant Agent (port 10000)
./start.sh a2a-server

# Start Client Agent UI (port 8080)
./start.sh a2a-client
```

See [`a2a/README.md`](a2a/README.md) for detailed architecture and configuration.

---

## Project Structure

```
├── server/              # Protected resource server (FastAPI)
├── facilitator/         # Payment processor (FastAPI)
├── client/
│   ├── python/          # Python CLI client
│   ├── typescript/      # TypeScript CLI client
│   └── web/             # React web client
├── a2a/                 # Agent-to-agent demo (Google ADK)
│   ├── server/          # Merchant agent
│   └── client_agent/    # Client agent UI
├── docker/              # Docker setup (supervisord)
├── docker-compose.yml   # Containerized deployment
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
- **A2A Demo:** [a2a/README.md](a2a/README.md)
