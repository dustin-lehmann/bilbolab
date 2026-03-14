#!/bin/bash
# Quick start script for Network Monitor

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/../.."

echo "====================================="
echo "  Network Monitor - Quick Start"
echo "====================================="

# Check if frontend is built
if [ ! -d "$SCRIPT_DIR/frontend/dist" ]; then
    echo ""
    echo "Frontend not built. Building now..."
    cd "$SCRIPT_DIR/frontend"

    if [ ! -d "node_modules" ]; then
        echo "Installing npm dependencies..."
        npm install
    fi

    echo "Building frontend..."
    npm run build

    cd "$SCRIPT_DIR/../.."
fi

echo ""
echo "Starting Network Monitor..."
echo "Access at: http://localhost:8500"
echo "Access at: http://network.local:8500 (mDNS)"
echo ""
echo "Press Ctrl+C to stop"
echo ""

python extensions/network_monitor/network_monitor_app.py "$@"
