## 📋 System Requirements

* **Operating System:** Linux (Ubuntu/Debian/Arch/Fedora) or Windows 10/11
* **Python:** 3.10 or higher
* **Node.js:** 18.x or higher (with `npm`)
* **FFmpeg:** Installed and added to system PATH (required for audio container parsing fallback)

---

## ⚡ Quick Start (Automated Scripts)

### On Linux:
1. Make the startup script executable:
   ```bash
   chmod +x start.sh
Run the script:

Bash
./start.sh
On Windows:
Double-click start.bat or run it via Command Prompt / PowerShell:

DOS
start.bat
The script will automatically set up the Python virtual environment, install dependencies, start both servers, and open your browser at http://localhost:3000.

🛠️ Manual Installation Guide
1. Python Neural Engine Setup (api/)
Bash
# Create virtual environment
python -m venv venv

# Activate environment
# On Linux/macOS:
source venv/bin/activate
# On Windows:
venv\Scripts\activate

# Upgrade pip & install dependencies
pip install --upgrade pip
pip install fastapi uvicorn torch scipy numpy pydub pydantic python-multipart
Start Python API server:

Bash
python api/server.py
(Runs on http://localhost:8000)

2. Node.js Web & VFS Server Setup (sdk/)
In a new terminal window:

Bash
npm install express multer
node sdk/app.js
(Runs on http://localhost:3000)

🌐 Accessing the System
Open your browser and navigate to:

Plaintext
http://localhost:3000