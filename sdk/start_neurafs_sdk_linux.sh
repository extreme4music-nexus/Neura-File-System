#!/bin/bash
echo "==================================================="
echo " Starting HyperCompress Node.js Web Manager..."
echo "==================================================="

# Check if node_modules directory exists
if [ ! -d "node_modules" ]; then
    echo "[ERROR] node_modules directory not found!"
    echo "Please run setup_node_linux.sh first to install dependencies."
    exit 1
fi

# Launch Node.js Server
node app.js