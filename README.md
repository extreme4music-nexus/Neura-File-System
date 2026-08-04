# NeuraFS

## 🚀 What's New in NeuraFS v1.1.0 - Speed & Parallel Neural Overhaul

### ⚡ Key Improvements & Performance Fixes

1. **Adaptive Neural Early Stopping & Sub-chunk Windowing**
   - **Problem Resolved:** Previously, fitting audio tracks through SIREN models could run for extended periods without explicit threshold caps.
   - **Fix:** Implemented 2-second time-window sub-chunking ($88,200$ samples/window) combined with Multi-Resolution STFT Loss. Parameterization now automatically triggers **Early Stopping** when loss convergence $\Delta L < 10^{-4}$ is reached. Typical song compression time dropped from nearly an hour down to **a few seconds / minutes**.

2. **Parallel Neural Compression Engine (`Parallel Multi-threading`)**
   - Implemented a multi-threaded `ThreadPoolExecutor` worker pipeline that fits all audio channels and sub-chunks concurrently across available CPU logical cores or GPU hardware streams.
   - Preserves **100% parallel execution** without race conditions.

3. **Hardware Acceleration Controls (CPU / GPU CUDA Selector)**
   - Added user controls for hardware execution target:
     - `CPU` (Default Multi-threaded Execution)
     - `GPU (CUDA)` (PyTorch CUDA acceleration when hardware is present)
   - Toggle switch for `Parallel Neural Compression` state.

4. **Task Cancellation API (Single & Global Cancel)**
   - Users can now stop individual tasks via the UI subband terminal dropdown (`✕` button) or stop all running background tasks instantly (`Stop All` button).

**NeuraFS** is a specialized, metric-driven Virtual File System (VFS) and long-term archival engine designed for transparent, high-fidelity studio audio and media preservation.

Rather than competing with consumer streaming codecs (such as MP3, AAC, or Opus), NeuraFS leverages **Implicit Neural Representations (INR)** and **Subband Neural Fitting**. It prioritizes long-term reconstruction fidelity over processing speed, delivering an encapsulated neural archival container (`.hcs`).

---

# NeuraFS — Implicit Neural Archive Engine (v1.0.0)


## 🌟 Key Features

* **Approximate Subband Decomposition:** Decomposes input signals into $N$ logarithmic subbands using zero-phase Butterworth filterbanks accompanied by a residual compensation layer.
* **Native Sample Rate Preservation:** Parameterizes and resynthesizes audio at its exact native sample rate (e.g., 44.1kHz, 48kHz, 96kHz) without unwanted resampling.
* **Smart Precision Allocation (`auto` Mode):** Evaluates stereo signal complexity to automatically decide between **Archive Mode (FP32)** for dense audio/transients and **Compact Mode (FP16)** for tonal/simpler structures.
* **32-Bit Float Resynthesis:** Supports IEEE 32-bit floating-point WAV export in Archive Mode, preserving full dynamic range without integer truncation.
* **Stereo Multi-Metric Analysis:** Computes Stereo Spectral Flatness and Crest Factor to dynamically scale neural network capacity (`hidden_dim` up to `256`).
* **Multi-Resolution STFT Loss & Early Stopping:** Evaluates spectral fidelity across multiple FFT resolutions ($N_{\text{fft}} \in \{256, 512, 2048\}$) with adaptive convergence stopping ($\Delta \text{Loss} < 10^{-5}$).
* **Closed Container Isolation:** Encapsulates SIREN neural parameters within `.hcs` containers, storing neural parameterizations instead of explicit PCM sample sequences.
* **Local Studio VFS Dashboard:** Single-user web interface featuring live subband logs, Monaco Code Editor, PDF viewer, and RAM-buffered streaming.

---

## 🏗️ Architecture Overview
[ Input Audio Signal ]
│
▼
[ Stereo Multi-Metric Analyzer ] ──► Computes Stereo Flatness & Crest Factor
│
▼
[ Subband Decomposition ]        ──► Subband Filterbank + Residual Compensation
│
├── Band 1 (Low Freq)   ──► [ SIREN Agent 1 ] ──► Multi-Resolution STFT Loss
├── Band 2 (Mid Freq)   ──► [ SIREN Agent 2 ] ──► Multi-Resolution STFT Loss
└── Band N (High Freq)  ──► [ SIREN Agent N ] ──► Multi-Resolution STFT Loss
│
▼
[ FP32 / FP16 Parameter Serialization ]
│
▼
[ Encapsulated .hcs Container ]


---

## 📁 Repository Structure

* `api/server.py` — Core Python FastAPI engine for signal analysis, PyTorch SIREN fitting, Multi-Resolution STFT Loss, and parallel multiprocessing.
* `sdk/hyper-compress-sdk.js` — Node.js SDK for `.hcs` package layout, header metadata, and Python orchestration.
* `sdk/app.js` — Single-user local VFS server managing storage paths and RAM streaming.
* `public/index.html` — Web UI dashboard supporting Archival / Compact / Auto mode selection and real-time processing logs.
* `start.sh` — Automated Linux installer and startup script.
* `start.bat` — Automated Windows installer and startup script.

---

## 📜 License

Distributed under the MIT License. See `LICENSE.md` for details.
