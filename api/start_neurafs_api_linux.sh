#!/bin/bash
echo "==================================================="
echo " Starting HyperCompress Python FastAPI Engine..."
echo "==================================================="

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "[ERROR] Virtual environment (venv) not found!"
    echo "Please run install_linux.sh first to set up the environment."
    exit 1
fi

# Activate Virtual Environment and Launch Server
source venv/bin/activate
python3 server.py