#!/usr/bin/env bash

echo "==================================================="
echo " NeuraFS v12.0.0 — Linux Environment Launcher"
echo "==================================================="

# 1. Check Python & Node.js availability
if ! command -v python3 &> /dev/null; then
    echo "[Error] Python 3 is not installed or not in PATH."
    exit 1
fi

if ! command -v node &> /dev/null; then
    echo "[Error] Node.js is not installed or not in PATH."
    exit 1
fi

# 2. Setup Python Virtual Environment
if [ ! -d "venv" ]; then
    echo "[Installer] Creating Python virtual environment..."
    python3 -m venv venv
fi

echo "[Installer] Activating Python environment..."
source venv/bin/activate

echo "[Installer] Checking/Installing Python dependencies..."
pip install --upgrade pip -q
pip install fastapi uvicorn torch scipy numpy pydub pydantic python-multipart -q

# 3. Setup Node.js Dependencies
if [ ! -d "node_modules" ]; then
    echo "[Installer] Installing Node.js dependencies..."
    npm install express multer
fi

# 4. Start Python Engine and Node.js Web Server concurrently
echo "==================================================="
echo " Starting NeuraFS Engine Services..."
echo " Python API: http://localhost:8000"
echo " Web VFS:    http://localhost:3000"
echo "==================================================="

python api/server.py &
PYTHON_PID=$!

node sdk/app.js &
NODE_PID=$!

cleanup() {
    echo ""
    echo "[NeuraFS] Shutting down services..."
    kill $PYTHON_PID 2>/dev/null
    kill $NODE_PID 2>/dev/null
    exit 0
}

trap cleanup SIGINT SIGTERM

wait