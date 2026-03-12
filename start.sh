#!/bin/bash
set -e

# X402 Demo - Unified Startup Script
# Usage: ./start.sh <component>

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

COMPONENT=$1

ensure_ts_demo_deps() {
    if [ -x "node_modules/.bin/tsx" ] && [ -d "node_modules/@bankofai/x402-core" ] && [ -d "node_modules/@bankofai/x402-tron" ] && [ -d "node_modules/@bankofai/x402-evm" ]; then
        return
    fi

    echo "Bootstrapping local SDK packages for x402-demo..."
    bash ./scripts/bootstrap-local-sdk.sh
}

if [ -z "$COMPONENT" ]; then
    echo "Usage: ./start.sh <component>"
    echo ""
    echo "Components:"
    echo "  server       - Protected resource server (Python/FastAPI)"
    echo "  facilitator  - Payment facilitator service (Python/FastAPI)"
    echo "  client       - Payment client (Python)"
    echo "  client-ts    - Payment client (TypeScript, deprecated SDK)"
    echo "  ts-server    - Protected resource server (TypeScript/Express, new SDK)"
    echo "  ts-facilitator - Payment facilitator (TypeScript/Express, new SDK)"
    echo "  ts-client    - Payment client (TypeScript, new SDK)"
    echo "  ts-mcp-server - MCP server (TypeScript/SSE, new SDK)"
    echo "  ts-mcp-client - MCP client (TypeScript/SSE, new SDK)"
    echo "  a2a-server   - A2A Merchant Server"
    echo "  a2a-client   - A2A Client Agent Web UI"
    exit 1
fi

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "❌ Error: .env file not found"
    echo ""
    echo "Please copy .env.sample to .env and fill in:"
    echo "  TRON_CLIENT_PRIVATE_KEY=your_nile_client_private_key"
    echo "  TRON_FACILITATOR_PRIVATE_KEY=your_nile_facilitator_private_key"
    echo "  PAY_TO_ADDRESS=your_tron_address"
    exit 1
fi

case "$COMPONENT" in
    server)
        echo "=========================================="
        echo "Starting X402 Protected Resource Server"
        echo "=========================================="
        cd server
        python main.py
        ;;
    facilitator)
        echo "=========================================="
        echo "Starting X402 Facilitator"
        echo "=========================================="
        cd facilitator
        python main.py
        ;;
    client)
        echo "=========================================="
        echo "Starting X402 Client (Python)"
        echo "=========================================="
        cd client/python
        python main.py
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
    ts-server)
        echo "=========================================="
        echo "Starting X402 Server (TypeScript / New SDK)"
        echo "=========================================="
        echo "Networks: TRON Nile (+ optional BSC Testnet)"
        ensure_ts_demo_deps
        npx tsx ts/server.ts
        ;;
    ts-facilitator)
        echo "=========================================="
        echo "Starting X402 Facilitator (TypeScript / New SDK)"
        echo "=========================================="
        echo "Networks: TRON Nile (+ optional BSC Testnet)"
        ensure_ts_demo_deps
        npx tsx ts/facilitator.ts
        ;;
    ts-client)
        echo "=========================================="
        echo "Starting X402 Client (TypeScript / New SDK)"
        echo "=========================================="
        echo "Networks: TRON Nile (+ optional BSC Testnet)"
        ensure_ts_demo_deps
        npx tsx ts/client.ts
        ;;
    ts-mcp-server)
        echo "=========================================="
        echo "Starting X402 MCP Server (TypeScript / New SDK)"
        echo "=========================================="
        echo "Network: TRON Nile"
        ensure_ts_demo_deps
        npx tsx ts/mcp-server.ts
        ;;
    ts-mcp-client)
        echo "=========================================="
        echo "Starting X402 MCP Client (TypeScript / New SDK)"
        echo "=========================================="
        echo "Network: TRON Nile"
        ensure_ts_demo_deps
        npx tsx ts/mcp-client.ts
        ;;
    a2a-server)
        echo "=========================================="
        echo "Starting A2A Merchant Server"
        echo "=========================================="
        cd a2a
        export SERVER_HOST="${SERVER_HOST:-0.0.0.0}"
        export SERVER_PORT="${SERVER_PORT:-8010}"
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
        echo "Valid: server, facilitator, client, client-ts, ts-server, ts-facilitator, ts-client, ts-mcp-server, ts-mcp-client, a2a-server, a2a-client"
        exit 1
        ;;
esac
