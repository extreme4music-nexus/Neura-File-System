#!/bin/bash
set -e

echo "==================================================="
echo " Neural & Lossless Hybrid Compression API Installer"
echo " Target OS: Linux (Ubuntu/Debian/RHEL/CentOS)"
echo "==================================================="

# 1. Check Python 3 installation
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] Python 3 could not be found. Please install Python 3.10+."
    exit 1
fi

# 2. Install required system packages if apt-get or dnf is available
echo "[1/4] Checking and installing system package dependencies..."
if command -v apt-get &> /dev/null; then
    sudo apt-get update -y
    sudo apt-get install -y python3-venv python3-pip
elif command -v dnf &> /dev/null; then
    sudo dnf install -y python3-pip
fi

# 3. Create Virtual Environment
echo "[2/4] Creating Virtual Environment (venv)..."
python3 -m venv venv

# 4. Activate Virtual Environment and Upgrade pip
echo "[3/4] Activating Virtual Environment..."
source venv/bin/activate
pip install --upgrade pip

# 5. Install PyTorch (CPU Version) and FastAPI Dependencies
echo "[4/4] Installing PyTorch (CPU Version), FastAPI, Uvicorn, and utilities..."
pip install torch --extra-index-url https://download.pytorch.org/whl/cpu
pip install fastapi "uvicorn[standard]" pydantic python-multipart

echo "==================================================="
echo " Installation Completed Successfully!"
echo "==================================================="
echo " To start the server, execute:"
echo "   source venv/bin/activate"
echo "   python3 server.py"
echo "==================================================="