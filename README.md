# NeuraFS (Neural File System) 🧠💾

**Neural representation-based storage engine. Stable (v1.0.0) **

NeuraFS is an experimental research prototype exploring the paradigm shift from traditional discrete file compression (like ZIP, MP3, MP4) to continuous **Implicit Neural Representations (INRs)**. Instead of storing bits of a file, NeuraFS trains a dynamic neural agent to memorize the data and stores its $FP16$ weights in a highly optimized binary container (`.hcs`).

---

## 🔬 Current Status: Experimental Research Prototype
**Please note:** This is a research project intended for DSP, Machine Learning, and Codec engineers. It is **not** a production-ready drop-in replacement for standard file systems. The goal is to prove that neural continuous representations can act as a viable, bit-perfect (or perceptually perfect) archival format.

## 💡 Core Concept
Instead of encoding an audio waveform or a video frame via traditional mathematical transforms (DCT, Wavelets), NeuraFS:
1. Decomposes the signal using adaptive subband filterbanks.
2. Trains a **SIREN (Sinusoidal Representation Network)** to map spatio-temporal coordinates $(x, y, t)$ to signal values.
3. Dynamically adjusts training epochs based on signal complexity (RMS, Spectral Flatness, ZCR) and psychoacoustic masking limits.
4. Serializes the neural weights into a decoupled `.hcs` (Hyper Compressed Subband) binary container.

## 🏗 Architecture
NeuraFS decouples the heavy lifting by running concurrent hybrid workflows (Audio on CPU cores, 3D Video on GPU).

```text
Input Media
     │
     ▼
Media Inspector (FFmpeg)
     │
     ├────────────────────────────────────────┐
     ▼                                        ▼
DSP Subband Decomposition (CPU)      3D Spatio-Temporal Batching (GPU)
     │                                        │
     ▼                                        ▼
SIREN Neural Agents (Warm-started, adaptive complexity training)
     │                                        │
     └──────────────────┬─────────────────────┘
                        ▼
            FP16 Weight Serialization
                        │
                        ▼
          HCS1 Binary Container (.hcs)
                        │
                        ▼
          Verification Metrics Agent
          (SI-SDR, LSD, Spectral Conv)


## 🚀 What's New in NeuraFS Beta (v1.0.1) - Speed & Parallel Neural Overhaul

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

# NeuraFS — Implicit Neural Archive Engine Beta (v1.0.0)


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

📊 Benchmarks
​Transparency is our priority. We measure not just compression ratios, but rigorous perceptual reconstruction metrics.
​To run the benchmark suite locally:
​Place test files in /storage/benchmark_tests/
​Run the engine: python api/server.py
​Run the benchmark tool: node sdk/benchmark.js
​Open http://localhost:4000/benchmark.html
​Check our Wiki/Discussions for the latest community benchmark tables across FLAC, MP4, and ZIP comparisons.
​🚧 Limitations
​Encoding Time: Training neural networks for every file introduces significant encoding latency compared to traditional algorithms.
​Compute Intensity: Requires substantial CPU/GPU resources for parallel processing.
​🤝 Contributing & Pull Request Rules
​We welcome contributions from developers interested in PyTorch, Signal Processing, Codecs, and Neural Fields!
​main branch: Stable releases only.
​Feature branches: All PRs must come from a feature branch.
​PR Requirements:
​Clear description of the problem solved.
​Benchmark results (if modifying DSP or SIREN architectures).
​Backward compatibility analysis (Do NOT break the .hcs binary serialization format without a version migration plan).
​🗺 Roadmap
​[x] Adaptive signal complexity training
​[x] HCS1 decoupled binary container
​[x] Multi-metric verification (SI-SDR, PSNR, LSD)
​[ ] Perfect Reconstruction Filter Banks (PRFB)
​[ ] Psychoacoustic perceptual loss implementation
​[ ] C++ / Rust bindings for faster decoding
​Developed by extreme4music-nexus.
---

## 📜 License

Distributed under the MIT License. See `LICENSE` for details.
