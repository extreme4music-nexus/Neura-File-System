#!/bin/bash
set -e

echo "==================================================="
echo " HyperCompress Node.js Web Manager Setup"
echo " Target OS: Linux (Ubuntu/Debian/RHEL/CentOS)"
echo "==================================================="

# 1. Check Node.js installation
if ! command -v node &> /dev/null; then
    echo "[ERROR] Node.js is not installed. Please install Node.js v18+."
    exit 1
fi

# 2. Create Directory Structure
echo "[1/3] Initializing directory hierarchy..."
mkdir -p storage/compressed/media
mkdir -p storage/compressed/documents
mkdir -p public
mkdir -p temp

# 3. Initialize Node Package
if [ ! -f "package.json" ]; then
    echo "[2/3] Initializing Node.js package.json..."
    npm init -y
fi

# 4. Install Dependencies
echo "[3/3] Installing Express and Multer dependencies..."
npm install express multer

echo "==================================================="
echo " Node.js Environment Setup Completed Successfully!"
echo "==================================================="
echo " Ensure your public/index.html and app.js files are in place."
echo " To launch the web server, run:"
echo "   node app.js"
echo "==================================================="