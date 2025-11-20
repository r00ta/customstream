#!/bin/bash
# Build script for CustomStream snap

set -e

echo "Building CustomStream snap..."
echo ""

# Check if snapcraft is installed
if ! command -v snapcraft &> /dev/null; then
    echo "Error: snapcraft is not installed."
    echo "Install it with: sudo snap install snapcraft --classic"
    exit 1
fi

# Clean previous build artifacts
echo "Cleaning previous build artifacts..."
snapcraft clean

# Build the snap
echo "Building snap package..."
snapcraft

# Show build result
echo ""
echo "Build complete!"
echo ""
ls -lh *.snap 2>/dev/null || echo "Snap file not found"
echo ""
echo "To install locally:"
echo "  sudo snap install customstream_*.snap --dangerous"
echo ""
echo "To test in a VM or container first:"
echo "  lxc launch ubuntu:22.04 customstream-test"
echo "  lxc file push customstream_*.snap customstream-test/root/"
echo "  lxc exec customstream-test -- snap install /root/customstream_*.snap --dangerous"
echo ""
