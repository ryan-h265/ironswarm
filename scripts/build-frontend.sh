#!/usr/bin/env bash
set -euo pipefail

# Build script for ironswarm web frontend
# This script builds the Vue.js frontend into static assets for distribution

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
FRONTEND_DIR="$PROJECT_ROOT/src/ironswarm/web/frontend"
STATIC_DIR="$PROJECT_ROOT/src/ironswarm/web/static"

echo "Building ironswarm web frontend..."

# Check for Node.js
if ! command -v node &> /dev/null; then
    echo "Error: Node.js is not installed"
    echo "   Please install Node.js 18+ from https://nodejs.org/"
    exit 1
fi

# Check Node.js version
NODE_VERSION=$(node --version | cut -d'v' -f2 | cut -d'.' -f1)
if [ "$NODE_VERSION" -lt 18 ]; then
    echo "Error: Node.js 18+ is required (found v$NODE_VERSION)"
    exit 1
fi

# Navigate to frontend directory
if [ ! -d "$FRONTEND_DIR" ]; then
    echo "Error: Frontend directory not found at $FRONTEND_DIR"
    exit 1
fi

cd "$FRONTEND_DIR"

# Clean install dependencies
echo "Installing dependencies..."
npm ci --quiet

# Build the frontend
echo "Building frontend..."
npm run build

# Verify build output
if [ ! -f "$STATIC_DIR/index.html" ]; then
    echo "Error: Build failed - index.html not found in $STATIC_DIR"
    exit 1
fi

# Count built assets
ASSET_COUNT=$(find "$STATIC_DIR/assets" -type f 2>/dev/null | wc -l || echo "0")
TOTAL_SIZE=$(du -sh "$STATIC_DIR" | cut -f1)

echo "  Frontend built successfully!"
echo "   Output: $STATIC_DIR"
echo "   Assets: $ASSET_COUNT files ($TOTAL_SIZE)"
