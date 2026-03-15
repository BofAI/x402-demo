#!/bin/bash
set -e

echo "=========================================="
echo "Building and starting x402-tron-demo"
echo "=========================================="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "❌ Error: .env file not found"
    echo ""
    echo "Please create .env from .env.sample:"
    echo "  cp .env.sample .env"
    exit 1
fi

# Remove stale container if it exists
CONTAINER_NAME="x402-tron-demo"
IMAGE_NAME="x402-tron-demo"
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "Removing existing container: ${CONTAINER_NAME}"
    docker rm -f "${CONTAINER_NAME}"
fi

# Build and start
echo ""
echo "Building Docker image..."
docker build -t "${IMAGE_NAME}" .

echo ""
echo "Starting container..."
docker run -d \
    --name "${CONTAINER_NAME}" \
    -p 8000:8000 \
    -v "${SCRIPT_DIR}/.env:/app/.env:ro" \
    -v "${SCRIPT_DIR}/logs:/app/logs" \
    "${IMAGE_NAME}"

echo ""
echo "=========================================="
echo "✅ Server started"
echo "=========================================="
echo "  Server API:  http://localhost:8000"
echo ""
echo "View logs:  docker logs -f ${CONTAINER_NAME}"
echo "Stop:       docker rm -f ${CONTAINER_NAME}"
echo "=========================================="
