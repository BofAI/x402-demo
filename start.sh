#!/bin/bash
set -e

# X402 TRON Demo - Unified Startup Script
# Usage: ./start.sh [server|facilitator|client|client-ts]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PY_BIN="python"
if [ -x "$SCRIPT_DIR/.venv/bin/python" ]; then
    PY_BIN="$SCRIPT_DIR/.venv/bin/python"
fi

# Default agent-wallet secrets dir to repo-local .agent-wallet (if present)
if [ -d "$SCRIPT_DIR/.agent-wallet" ] && [ -z "${AGENT_WALLET_SECRETS_DIR:-}" ]; then
    export AGENT_WALLET_SECRETS_DIR="$SCRIPT_DIR/.agent-wallet"
fi

COMPONENT=$1

if [ -z "$COMPONENT" ]; then
    echo "Usage: ./start.sh <component>"
    echo ""
    echo "Components:"
    echo "  server       - Protected resource server (Python/FastAPI)"
    echo "  facilitator  - Payment facilitator service (Python/FastAPI)"
    echo "  client       - Payment client (Python)"
    echo "  client-ts    - Payment client (TypeScript)"
    echo "  init-wallet  - Initialize agent-wallet test wallets from .env"
    echo "  a2a-server   - A2A Merchant Server"
    echo "  a2a-client   - A2A Client Agent Web UI"
    exit 1
fi

# Check if .env exists
if [ "$COMPONENT" != "init-wallet" ] && [ ! -f ".env" ]; then
    echo "❌ Error: .env file not found"
    echo ""
    echo "Please create .env file with:"
    echo "  TRON_PRIVATE_KEY=your_private_key"
    echo "  PAY_TO_ADDRESS=your_tron_address"
    exit 1
fi

case "$COMPONENT" in
    server)
        echo "=========================================="
        echo "Starting X402 Protected Resource Server"
        echo "=========================================="
        cd server
        "$PY_BIN" main.py
        ;;
    facilitator)
        echo "=========================================="
        echo "Starting X402 Facilitator"
        echo "=========================================="
        cd facilitator
        "$PY_BIN" main.py
        ;;
    client)
        echo "=========================================="
        echo "Starting X402 Client (Python)"
        echo "=========================================="
        cd client/python
        "$PY_BIN" main.py
        ;;
    client-ts)
        echo "=========================================="
        echo "Starting X402 Client (TypeScript)"
        echo "=========================================="
        cd client/typescript
        if [ ! -d "node_modules" ]; then
            echo "Installing dependencies..."
            npm install
        fi
        npm start
        ;;
    init-wallet)
        echo "=========================================="
        echo "Initializing Agent Wallets"
        echo "=========================================="
        if [ ! -f "scripts/init_agent_wallet.sh" ]; then
            echo "❌ Error: scripts/init_agent_wallet.sh not found"
            exit 1
        fi
        bash scripts/init_agent_wallet.sh
        ;;
    a2a-server)
        echo "=========================================="
        echo "Starting A2A Merchant Server"
        echo "=========================================="
        cd a2a
        export SERVER_HOST="${SERVER_HOST:-0.0.0.0}"
        export SERVER_PORT="${SERVER_PORT:-10000}"
        export TRON_NETWORK="${TRON_NETWORK:-tron:nile}"
        export FACILITATOR_URL="${FACILITATOR_URL:-https://facilitator.bankofai.io}"
        
        # Load root .env if it exists
        if [ -f "../.env" ]; then
            set -a
            source ../.env
            set +a
        fi
        
        uv run server --host "$SERVER_HOST" --port "$SERVER_PORT"
        ;;
    a2a-client)
        echo "=========================================="
        echo "Starting A2A Client Agent Web UI"
        echo "=========================================="
        cd a2a
        export CLIENT_PORT="${CLIENT_PORT:-8080}"
        
        # Load root .env if it exists
        if [ -f "../.env" ]; then
            set -a
            source ../.env
            set +a
        fi
        
        uv run adk web --port "$CLIENT_PORT"
        ;;
    *)
        echo "❌ Unknown component: $COMPONENT"
        echo "Valid: server, facilitator, client, client-ts, init-wallet, a2a-server, a2a-client"
        exit 1
        ;;
esac
