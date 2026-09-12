#!/bin/bash

# --- Video Utilities Build Script ---
# This script bundles the application into standalone binaries.
# Note: Cross-compiling for Windows from Linux requires 'wine' and a Windows Python environment.
# Native builds (Linux on Linux) are recommended.

mkdir -p build

echo "📦 Installing build dependencies..."
./.venv/bin/python -m pip install pyinstaller pillow flet flet-video

# --- LINUX BUILD ---
echo "🐧 Building LINUX binary..."
# Use --noconfirm and separate dist/build paths to avoid "Not a directory" errors
./.venv/bin/python -m PyInstaller --onefile --windowed --noconfirm \
    --add-data "assets:assets" \
    --name "ExpressiveVideoCompressor-Linux" \
    --distpath ./dist \
    --workpath ./build-work \
    --collect-all flet \
    --collect-all flet_video \
    --noupx --clean \
    main.py

# Move to final build folder
mkdir -p build
mv ./dist/ExpressiveVideoCompressor-Linux ./build/
rm -rf ./dist ./build-work ExpressiveVideoCompressor-Linux.spec

# --- WINDOWS BUILD (Using Custom Docker Image) ---
echo "🪟 Building WINDOWS binary (.exe) via Custom Docker..."
if command -v docker &> /dev/null
then
    # 1. Build the builder container
    echo "🏗️ Building custom Windows build environment (Python 3.11 + Flet 0.80.2)..."
    if docker build -t flet-windows-builder -f Dockerfile.windows .
    then
        # 2. Run the build
        echo "🔨 Compiling Windows executable..."
        if docker run --rm -v "$(pwd):/src" flet-windows-builder \
            "--onefile --windowed --noconfirm --add-data 'assets;assets' --name 'ExpressiveVideoCompressor-Windows' --distpath ./dist --workpath ./build-work --collect-all flet --collect-all flet_video --noupx --clean main.py"
        then
            mkdir -p build
            mv ./dist/ExpressiveVideoCompressor-Windows.exe ./build/
            rm -rf ./dist ./build-work ExpressiveVideoCompressor-Windows.spec
            echo "✅ Windows build complete!"
        else
            echo "❌ ERROR: Windows compilation failed!"
            exit 1
        fi
    else
        echo "❌ ERROR: Failed to build the Docker Windows environment!"
        exit 1
    fi
else
    echo "❌ Docker not found. Skipping Windows build."
fi

echo ""
echo "✨ Build process finished. Check the /build directory for files."
