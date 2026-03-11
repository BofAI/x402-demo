# X402 Demo

## Overview

The **X402 Demo** provides a practical demonstration of integrating the **x402 payment protocol** with TRON. The current TypeScript demo is scoped to **TRON Nile** and uses the new SDK stack (`x402-core`, `x402-fetch`, `x402-tron`).

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
- Supports per-endpoint pricing using the `exact` scheme on `tron:nile`.

### Facilitator (Payment Processor)
- Validates signed payment permits and settles transactions on-chain.
- Validates and settles TRON `exact` payments (`tip712` / `permit2`) on Nile.

### Client (Resource Requester)
- **TypeScript CLI** — Uses `x402Client` and `ExactTronScheme` from the new SDK.
- **Python CLI / A2A** — Legacy/demo components remain in the repo but are not part of the new SDK Nile acceptance path.

---

## Supported Network

| Network | Chain ID | Payment Scheme | Transfer Methods |
|---------|----------|----------------|------------------|
| TRON Nile (testnet) | `tron:nile` | `exact` | `tip712`, `permit2` |

---

## Environment Setup

### Prerequisites
- **Python 3.9+** (for local execution)
- **Node.js 18+** (for TypeScript client)
- **Docker** (optional, for containerized deployment)

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
SERVER_PORT=8010
FACILITATOR_PORT=8011
SERVER_URL=http://localhost:8010
FACILITATOR_URL=http://localhost:8011
ENDPOINT=/protected-nile
```

---

## Quick Start

### Step 1: Start Services

Start the Nile facilitator and server:

Before first run, install the local SDK shim:

```bash
npm run bootstrap:local-sdk
```

**Using Scripts:**
```bash
# Start Facilitator
./start.sh facilitator

# Start Server (in a new terminal)
./start.sh server
```

### Step 2: Run a Client

**TypeScript CLI:**
```bash
./start.sh ts-client
```

## Project Structure

```
├── ts/                  # TypeScript server / facilitator / client
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
