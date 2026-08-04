import os
import io
import time
import base64
import lzma
import zlib
import threading
import numpy as np
import scipy.signal as signal
import scipy.io.wavfile as wavfile
import torch
import torch.nn as nn
from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional

app = FastAPI(title="NeuraFS Neural Archival Engine", version="12.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

tasks = {}

# -------------------------------------------------------------------
# SIREN (Sinusoidal Representation Networks) Architecture
# -------------------------------------------------------------------
class SineLayer(nn.Module):
    def __init__(self, in_features, out_features, bias=True, is_first=False, omega_0=30.0):
        super().__init__()
        self.omega_0 = omega_0
        self.is_first = is_first
        self.in_features = in_features
        self.linear = nn.Linear(in_features, out_features, bias=bias)
        self.init_weights()

    def init_weights(self):
        with torch.no_grad():
            if self.is_first:
                self.linear.weight.uniform_(-1 / self.in_features, 1 / self.in_features)
            else:
                self.linear.weight.uniform_(
                    -np.sqrt(6 / self.in_features) / self.omega_0,
                    np.sqrt(6 / self.in_features) / self.omega_0
                )

    def forward(self, input):
        return torch.sin(self.omega_0 * self.linear(input))

class SirenAgent(nn.Module):
    def __init__(self, in_features=1, hidden_features=128, hidden_layers=3, out_features=1, first_omega_0=30.0, hidden_omega_0=30.0):
        super().__init__()
        self.net = nn.ModuleList()
        self.net.append(SineLayer(in_features, hidden_features, is_first=True, omega_0=first_omega_0))
        for _ in range(hidden_layers):
            self.net.append(SineLayer(hidden_features, hidden_features, is_first=False, omega_0=hidden_omega_0))
        
        final_linear = nn.Linear(hidden_features, out_features)
        with torch.no_grad():
            final_linear.weight.uniform_(-np.sqrt(6 / hidden_features) / hidden_omega_0, np.sqrt(6 / hidden_features) / hidden_omega_0)
        self.net.append(final_linear)

    def forward(self, coords):
        x = coords
        for layer in self.net:
            x = layer(x)
        return x

# -------------------------------------------------------------------
# Multi-Resolution STFT Loss Function
# -------------------------------------------------------------------
class STFTLoss(nn.Module):
    def __init__(self, fft_size=1024, hop_size=256, win_length=1024):
        super().__init__()
        self.fft_size = fft_size
        self.hop_size = hop_size
        self.win_length = win_length
        self.register_buffer("window", torch.hann_window(win_length))

    def forward(self, x, y):
        x_stft = torch.stft(x, n_fft=self.fft_size, hop_length=self.hop_size, win_length=self.win_length, window=self.window, return_complex=True)
        y_stft = torch.stft(y, n_fft=self.fft_size, hop_length=self.hop_size, win_length=self.win_length, window=self.window, return_complex=True)
        x_mag = torch.abs(x_stft) + 1e-7
        y_mag = torch.abs(y_stft) + 1e-7
        sc_loss = torch.norm(y_mag - x_mag, p="fro") / (torch.norm(y_mag, p="fro") + 1e-7)
        mag_loss = torch.mean(torch.abs(torch.log(y_mag) - torch.log(x_mag)))
        return sc_loss + mag_loss

class MultiResolutionSTFTLoss(nn.Module):
    def __init__(self, fft_sizes=[256, 512, 2048], hop_sizes=[64, 128, 512], win_lengths=[256, 512, 2048]):
        super().__init__()
        self.stft_losses = nn.ModuleList([
            STFTLoss(fs, hs, wl) for fs, hs, wl in zip(fft_sizes, hop_sizes, win_lengths)
        ])

    def forward(self, x, y):
        loss = 0.0
        for stft in self.stft_losses:
            loss += stft(x, y)
        return loss / len(self.stft_losses)

# -------------------------------------------------------------------
# Spectral Analysis Utilities
# -------------------------------------------------------------------
def calculate_stereo_metrics(audio_data, sample_rate):
    if audio_data.ndim == 1:
        audio_data = np.column_stack((audio_data, audio_data))
    
    metrics = []
    for ch in range(audio_data.shape[1]):
        channel_data = audio_data[:, ch].astype(np.float32)
        rms = np.sqrt(np.mean(channel_data**2) + 1e-9)
        peak = np.max(np.abs(channel_data)) + 1e-9
        crest_factor = 20 * np.log10(peak / rms)

        frequencies, psd = signal.welch(channel_data, fs=sample_rate, nperseg=1024)
        psd = psd + 1e-12
        arithmetic_mean = np.mean(psd)
        geometric_mean = np.exp(np.mean(np.log(psd)))
        spectral_flatness = geometric_mean / arithmetic_mean

        metrics.append({
            "crest_factor_db": float(crest_factor),
            "spectral_flatness": float(spectral_flatness)
        })
    return metrics

# -------------------------------------------------------------------
# Background Neural Fitting Worker
# -------------------------------------------------------------------
def fit_neural_media_task(task_id: str, file_bytes: bytes, filename: str, precision_mode: str):
    try:
        tasks[task_id]["logs"].append(f"[Engine] Reading audio container: {filename}")
        
        sample_rate, audio_np = wavfile.read(io.BytesIO(file_bytes))
        if audio_np.dtype == np.int16:
            audio_np = audio_np.astype(np.float32) / 32768.0
        elif audio_np.dtype == np.int32:
            audio_np = audio_np.astype(np.float32) / 2147483648.0

        if audio_np.ndim == 1:
            audio_np = np.column_stack((audio_np, audio_np))

        num_samples, channels = audio_np.shape
        metrics = calculate_stereo_metrics(audio_np, sample_rate)
        avg_flatness = np.mean([m["spectral_flatness"] for m in metrics])
        avg_crest = np.mean([m["crest_factor_db"] for m in metrics])

        # Precision & Dimension Allocation
        if precision_mode == "archive":
            effective_precision = "archive"
            hidden_dim = 256
        elif precision_mode == "compact":
            effective_precision = "compact"
            hidden_dim = 128
        else: # auto
            if avg_flatness > 0.15 or avg_crest > 14.0:
                effective_precision = "archive"
                hidden_dim = 256
            else:
                effective_precision = "compact"
                hidden_dim = 128

        tasks[task_id]["logs"].append(f"[Metrics] Flatness: {avg_flatness:.4f}, Crest: {avg_crest:.2f}dB -> Mode: {effective_precision.upper()} (Hidden: {hidden_dim})")

        t_coords = torch.linspace(-1.0, 1.0, steps=num_samples).unsqueeze(1)
        audio_tensor = torch.from_numpy(audio_np)

        stft_loss_fn = MultiResolutionSTFTLoss()
        
        neural_chunks = []
        for ch in range(channels):
            # Check for Cancellation
            if tasks[task_id].get("status") == "cancelled":
                tasks[task_id]["logs"].append("[Cancel] Processing interrupted by user request.")
                return

            tasks[task_id]["logs"].append(f"[SIREN Agent {ch+1}/{channels}] Initiating STFT multi-resolution fitting...")
            tasks[task_id]["progress"] = 20 + int((ch / channels) * 70)

            agent = SirenAgent(in_features=1, hidden_features=hidden_dim, out_features=1)
            optimizer = torch.optim.Adam(agent.parameters(), lr=1e-3)

            target_ch = audio_tensor[:, ch].unsqueeze(1)

            for step in range(300):
                # Check for Cancellation during iteration
                if tasks[task_id].get("status") == "cancelled":
                    tasks[task_id]["logs"].append("[Cancel] Interrupted during SIREN Optimization loop.")
                    return

                optimizer.zero_grad()
                pred_ch = agent(t_coords)
                
                mse_loss = nn.MSELoss()(pred_ch, target_ch)
                stft_loss = stft_loss_fn(pred_ch.squeeze(1).unsqueeze(0), target_ch.squeeze(1).unsqueeze(0))
                total_loss = mse_loss + 0.1 * stft_loss

                total_loss.backward()
                optimizer.step()

                if step % 100 == 0:
                    tasks[task_id]["logs"].append(f"   Iter {step}/300 | Loss: {total_loss.item():.6f}")

            # Serialize weights
            state_dict = agent.state_dict()
            buf = io.BytesIO()

            if effective_precision == "compact":
                state_dict = {k: v.half() for k, v in state_dict.items()}

            torch.save(state_dict, buf)
            weights_b64 = base64.b64encode(buf.getvalue()).decode('utf-8')

            neural_chunks.append({
                "chunk_idx": ch,
                "band_idx": ch,
                "num_frames": num_samples,
                "channels": channels,
                "hidden_dim": hidden_dim,
                "effective_precision": effective_precision,
                "weights_b64": weights_b64
            })

        tasks[task_id]["progress"] = 100
        tasks[task_id]["status"] = "completed"
        tasks[task_id]["result"] = {
            "sample_rate": sample_rate,
            "channels": channels,
            "num_bands": channels,
            "neural_chunks": neural_chunks
        }
        tasks[task_id]["logs"].append("[Engine] Parameterization complete.")

    except Exception as e:
        tasks[task_id]["status"] = "failed"
        tasks[task_id]["logs"].append(f"[Error] Fitting failed: {str(e)}")

# -------------------------------------------------------------------
# FastAPI Endpoints
# -------------------------------------------------------------------

@app.post("/api/v1/encode-neural-media-start")
async def encode_neural_media_start(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    task_id: str = Form(...),
    precision_mode: str = Form("auto")
):
    file_bytes = await file.read()
    tasks[task_id] = {
        "id": task_id,
        "status": "running",
        "progress": 5,
        "logs": [f"[Python Engine] Initializing Neural Task {task_id}"],
        "result": None
    }
    background_tasks.add_task(fit_neural_media_task, task_id, file_bytes, file.filename, precision_mode)
    return {"status": "started", "task_id": task_id}

@app.get("/api/v1/task-status/{task_id}")
async def get_task_status(task_id: str):
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    return tasks[task_id]

@app.post("/api/v1/task-cancel/{task_id}")
async def cancel_task(task_id: str):
    if task_id == "all":
        for tid in list(tasks.keys()):
            tasks[tid]["status"] = "cancelled"
            tasks[tid]["logs"].append("[Cancel] Global Stop command received.")
        return {"status": "success", "message": "All tasks cancelled"}

    if task_id in tasks:
        tasks[task_id]["status"] = "cancelled"
        tasks[task_id]["logs"].append("[Cancel] User cancel command received.")
        return {"status": "success", "message": f"Task {task_id} cancelled"}

    return {"status": "success", "message": "Task not found or finished."}

class BinaryChunkBatch(BaseModel):
    chunks_b64: List[str]

@app.post("/api/v1/encode-lossless-binary")
async def encode_lossless_binary(batch: BinaryChunkBatch):
    compressed_chunks = []
    for chunk_b64 in batch.chunks_b64:
        raw_data = base64.b64decode(chunk_b64)
        compressed = lzma.compress(raw_data, preset=6)
        compressed_chunks.append(base64.b64encode(compressed).decode('utf-8'))
    return {"compressed_chunks_b64": compressed_chunks}

@app.post("/api/v1/reconstruct-lossless-binary")
async def reconstruct_lossless_binary(batch: BinaryChunkBatch):
    decompressed_chunks = []
    for chunk_b64 in batch.chunks_b64:
        comp_data = base64.b64decode(chunk_b64)
        decompressed = lzma.decompress(comp_data)
        decompressed_chunks.append(base64.b64encode(decompressed).decode('utf-8'))
    return {"decompressed_chunks_b64": decompressed_chunks}

class ResynthesisChunkInfo(BaseModel):
    chunk_idx: int
    band_idx: int
    num_frames: int
    channels: int
    hidden_dim: int
    effective_precision: str
    weights_b64: str

class ResynthesisRequest(BaseModel):
    chunks: List[ResynthesisChunkInfo]

@app.post("/api/v1/resynthesize-neural-media")
async def resynthesize_neural_media(req: ResynthesisRequest):
    if not req.chunks:
        raise HTTPException(status_code=400, detail="No neural chunks provided")

    num_samples = req.chunks[0].num_frames
    channels = req.chunks[0].channels
    effective_precision = req.chunks[0].effective_precision

    resynthesized_channels = []
    t_coords = torch.linspace(-1.0, 1.0, steps=num_samples).unsqueeze(1)

    for chunk in req.chunks:
        weights_bytes = base64.b64decode(chunk.weights_b64)
        buf = io.BytesIO(weights_bytes)
        state_dict = torch.load(buf, map_location="cpu")

        if chunk.effective_precision == "compact":
            state_dict = {k: v.float() for k, v in state_dict.items()}

        agent = SirenAgent(in_features=1, hidden_features=chunk.hidden_dim, out_features=1)
        agent.load_state_dict(state_dict)
        agent.eval()

        with torch.no_grad():
            pred_ch = agent(t_coords).squeeze(1).numpy()
            resynthesized_channels.append(pred_ch)

    audio_resynthesized = np.column_stack(resynthesized_channels)

    if effective_precision == "archive":
        # 32-bit Float WAV resynthesis
        audio_resynthesized = np.clip(audio_resynthesized, -1.0, 1.0).astype(np.float32)
        bits_per_sample = 32
        audio_format = 3 # IEEE Float
        pcm_bytes = audio_resynthesized.tobytes()
    else:
        # 16-bit PCM Int WAV resynthesis
        audio_pcm16 = (np.clip(audio_resynthesized, -1.0, 1.0) * 32767.0).astype(np.int16)
        bits_per_sample = 16
        audio_format = 1 # PCM Int
        pcm_bytes = audio_pcm16.tobytes()

    return {
        "status": "success",
        "pcm_b64": base64.b64encode(pcm_bytes).decode('utf-8'),
        "bits_per_sample": bits_per_sample,
        "audio_format": audio_format
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
