import os
import sys
import io
import math
import wave
import json
import base64
import lzma
import warnings
import numpy as np
from typing import List, Dict, Any, Tuple
from multiprocessing import Pool, cpu_count

warnings.filterwarnings("ignore")

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

import torch
import torch.nn as nn
import torch.optim as optim
from scipy.signal import butter, sosfiltfilt

torch.set_num_threads(1)

app = FastAPI(
    title="NeuraFS High-Fidelity Archive Engine (Neural Parameterization & Resynthesis)",
    version="12.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_optimal_worker_count() -> int:
    return max(1, cpu_count() - 1)

tasks_db: Dict[str, Dict[str, Any]] = {}

# Global Memory Cache for Multi-Resolution STFT Loss Windows
STFT_WINDOWS = {
    256: torch.hann_window(256),
    512: torch.hann_window(512),
    2048: torch.hann_window(2048)
}

# =====================================================================
# APPROXIMATE SUBBAND DECOMPOSITION WITH RESIDUAL COMPENSATION
# =====================================================================

def split_waveform_into_bands(pcm_data: np.ndarray, sample_rate: int, num_bands: int) -> List[np.ndarray]:
    if num_bands <= 1:
        return [pcm_data]

    nyquist = sample_rate / 2.0
    freq_edges = np.logspace(np.log10(20), np.log10(max(100.0, nyquist - 100)), num=num_bands + 1)
    
    bands = []
    accumulated_subbands = np.zeros_like(pcm_data)

    for i in range(num_bands):
        low_f = max(10.0, freq_edges[i])
        high_f = min(nyquist - 10.0, freq_edges[i + 1])

        if i == 0:
            sos = butter(4, high_f / nyquist, btype='low', output='sos')
        elif i == num_bands - 1:
            sos = butter(4, low_f / nyquist, btype='high', output='sos')
        else:
            sos = butter(4, [low_f / nyquist, high_f / nyquist], btype='bandpass', output='sos')

        subband = sosfiltfilt(sos, pcm_data, axis=0)
        bands.append(subband.astype(np.float32))
        accumulated_subbands += subband

    # Residual Compensation Layer
    residual = pcm_data - accumulated_subbands
    bands[0] += residual.astype(np.float32)

    return bands

# =====================================================================
# AUDIO DECODER (NATIVE SAMPLE RATE PRESERVATION)
# =====================================================================

def decode_audio_to_pcm(content: bytes, filename: str) -> Tuple[bytes, int, int]:
    ext = os.path.splitext(filename)[1].lower()

    if ext == '.wav':
        try:
            with wave.open(io.BytesIO(content), 'rb') as wf:
                channels = wf.getnchannels()
                sample_rate = wf.getframerate()
                sampwidth = wf.getsampwidth()
                raw_frames = wf.readframes(wf.getnframes())

                if sampwidth == 2:
                    pcm_bytes = raw_frames
                elif sampwidth == 3:
                    raw_arr = np.frombuffer(raw_frames, dtype=np.uint8)
                    raw_arr = raw_arr[:(len(raw_arr) // 3) * 3].reshape(-1, 3)
                    a16 = (raw_arr[:, 1].astype(np.int16) | (raw_arr[:, 2].astype(np.int8).astype(np.int16) << 8))
                    pcm_bytes = a16.tobytes()
                elif sampwidth == 4:
                    a32 = np.frombuffer(raw_frames, dtype=np.float32)
                    a16 = (np.clip(a32, -1.0, 1.0) * 32767.0).astype(np.int16)
                    pcm_bytes = a16.tobytes()
                else:
                    pcm_bytes = raw_frames

                return pcm_bytes, sample_rate, channels
        except Exception:
            pass

    try:
        from pydub import AudioSegment
        audio = AudioSegment.from_file(io.BytesIO(content))
        # Preserve original frame rate without resampling
        native_sample_rate = audio.frame_rate
        audio = audio.set_sample_width(2)
        return audio.raw_data, native_sample_rate, audio.channels
    except Exception:
        pass

    return content, 44100, 2

# =====================================================================
# STEREO METRIC ANALYSIS & DYNAMIC CAPACITY
# =====================================================================

def compute_stereo_spectral_flatness(subband_np: np.ndarray) -> float:
    if len(subband_np) == 0:
        return 0.0
    mono_signal = np.mean(subband_np, axis=1) if subband_np.ndim > 1 else subband_np
    fft_mag = np.abs(np.fft.rfft(mono_signal)) + 1e-12
    arithmetic_mean = np.mean(fft_mag)
    geometric_mean = np.exp(np.mean(np.log(fft_mag)))
    return float(geometric_mean / arithmetic_mean)

def compute_dynamic_hidden_dim(subband_np: np.ndarray) -> Tuple[int, float, float]:
    flatness = compute_stereo_spectral_flatness(subband_np)
    rms = np.sqrt(np.mean(subband_np ** 2)) + 1e-8
    peak = np.max(np.abs(subband_np)) + 1e-8
    crest_factor = min(10.0, float(peak / rms))
    
    raw_dim = 32 + int(224 * (0.6 * flatness + 0.4 * (crest_factor / 10.0)))
    hidden_dim = int(np.clip(round(raw_dim / 32) * 32, 32, 256))
    return hidden_dim, flatness, crest_factor

class HarmonicPositionalEncoding(nn.Module):
    def __init__(self, num_frequencies=12):
        super().__init__()
        self.num_frequencies = num_frequencies
        self.out_dim = 1 + 2 * num_frequencies

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out = [x]
        for i in range(self.num_frequencies):
            freq = (2.0 ** i) * math.pi
            out.append(torch.sin(freq * x))
            out.append(torch.cos(freq * x))
        return torch.cat(out, dim=-1)

class SineLayer(nn.Module):
    def __init__(self, in_features: int, out_features: int, omega_0: float = 30.0, is_first: bool = False):
        super().__init__()
        self.omega_0 = omega_0
        self.is_first = is_first
        self.linear = nn.Linear(in_features, out_features)
        self.init_weights()

    def init_weights(self):
        with torch.no_grad():
            if self.is_first:
                self.linear.weight.uniform_(-1 / self.linear.in_features, 1 / self.linear.in_features)
            else:
                self.linear.weight.uniform_(
                    -math.sqrt(6 / self.linear.in_features) / self.omega_0,
                    math.sqrt(6 / self.linear.in_features) / self.omega_0
                )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return torch.sin(self.omega_0 * self.linear(x))

class DynamicBandAgentINR(nn.Module):
    def __init__(self, num_freqs: int = 12, hidden_dim: int = 128, out_channels: int = 2):
        super().__init__()
        self.pe = HarmonicPositionalEncoding(num_frequencies=num_freqs)
        in_dim = self.pe.out_dim
        
        self.net = nn.Sequential(
            SineLayer(in_dim, hidden_dim, omega_0=30.0, is_first=True),
            SineLayer(hidden_dim, hidden_dim, omega_0=30.0),
            SineLayer(hidden_dim, hidden_dim, omega_0=30.0),
            nn.Linear(hidden_dim, out_channels)
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        encoded = self.pe(x)
        return self.net(encoded)

# =====================================================================
# CACHED MULTI-RESOLUTION STFT LOSS & METRICS
# =====================================================================

def multi_resolution_stft_loss(output: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
    fft_sizes = [256, 512, 2048]
    hop_sizes = [64, 128, 512]
    win_lengths = [256, 512, 2048]
    
    total_loss = 0.0
    for n_fft, hop, win_len in zip(fft_sizes, hop_sizes, win_lengths):
        win = STFT_WINDOWS[win_len]
        stft_out = torch.stft(output.T, n_fft=n_fft, hop_length=hop, win_length=win_len, window=win, return_complex=True)
        stft_tg = torch.stft(target.T, n_fft=n_fft, hop_length=hop, win_length=win_len, window=win, return_complex=True)
        
        mag_out = torch.abs(stft_out)
        mag_tg = torch.abs(stft_tg)
        
        sc_loss = torch.norm(mag_tg - mag_out, p="fro") / (torch.norm(mag_tg, p="fro") + 1e-7)
        log_loss = torch.mean(torch.abs(torch.log(mag_tg + 1e-7) - torch.log(mag_out + 1e-7)))
        total_loss += (sc_loss + log_loss)
        
    return total_loss / len(fft_sizes)

def calculate_snr(original: torch.Tensor, reconstructed: torch.Tensor) -> float:
    noise = original - reconstructed
    signal_power = torch.sum(original ** 2)
    noise_power = torch.sum(noise ** 2) + 1e-8
    snr = 10.0 * torch.log10(signal_power / noise_power)
    return float(snr.item())

# =====================================================================
# ADAPTIVE WORKER WITH SMART AUTO-PRECISION SELECTION
# =====================================================================

def _fit_adaptive_frequency_band_agent_worker(args: Tuple[int, int, bytes, int, int, str]) -> Dict[str, Any]:
    chunk_idx, band_idx, raw_subband_bytes, channels, sample_rate, precision_mode = args
    
    try:
        subband_np = np.frombuffer(raw_subband_bytes, dtype=np.float32)
        remainder = len(subband_np) % channels
        if remainder != 0:
            subband_np = subband_np[:-remainder]

        subband_np = subband_np.reshape(-1, channels)
        samples = torch.from_numpy(subband_np)
        num_frames = samples.shape[0]

        if num_frames == 0:
            return {"chunk_idx": chunk_idx, "band_idx": band_idx, "weights_b64": "", "num_frames": 0, "channels": channels, "hidden_dim": 32, "effective_precision": "compact"}

        hidden_dim, flatness, crest_factor = compute_dynamic_hidden_dim(subband_np)

        # Smart Auto Precision Decision
        if precision_mode == "auto":
            effective_precision = "archive" if (flatness > 0.12 or crest_factor > 5.0) else "compact"
        else:
            effective_precision = precision_mode

        max_epochs = 400 if effective_precision == "archive" else 250

        coords = torch.linspace(-1.0, 1.0, steps=num_frames).unsqueeze(1)
        model = DynamicBandAgentINR(num_freqs=12, hidden_dim=hidden_dim, out_channels=channels)
        optimizer = optim.AdamW(model.parameters(), lr=3e-3, weight_decay=1e-7)

        model.train()
        epoch = 0
        loss_history = []
        patience = 20
        min_delta = 1e-5

        while epoch < max_epochs:
            optimizer.zero_grad()
            output = model(coords)
            
            l1_loss = torch.mean(torch.abs(output - samples))
            mr_stft = multi_resolution_stft_loss(output, samples)
            total_loss = l1_loss + 0.3 * mr_stft
            
            total_loss.backward()
            optimizer.step()

            loss_val = float(total_loss.item())
            loss_history.append(loss_val)

            # Convergence Early Stopping
            if len(loss_history) > patience:
                recent_avg = np.mean(loss_history[-patience:-10])
                latest_avg = np.mean(loss_history[-10:])
                if (recent_avg - latest_avg) < min_delta:
                    break

            epoch += 1

        with torch.no_grad():
            final_output = model(coords)
            achieved_snr = calculate_snr(samples, final_output)

        weights_tensor = torch.cat([p.detach().view(-1) for p in model.parameters()])
        
        if effective_precision == "archive":
            raw_weights_bytes = weights_tensor.float().cpu().numpy().tobytes()
        else:
            raw_weights_bytes = weights_tensor.half().cpu().numpy().tobytes()

        return {
            "chunk_idx": chunk_idx,
            "band_idx": band_idx,
            "weights_b64": base64.b64encode(raw_weights_bytes).decode('ascii'),
            "num_frames": num_frames,
            "channels": channels,
            "hidden_dim": hidden_dim,
            "effective_precision": effective_precision,
            "achieved_snr": round(achieved_snr, 2)
        }
    except Exception:
        return {"chunk_idx": chunk_idx, "band_idx": band_idx, "weights_b64": "", "num_frames": 0, "channels": channels, "hidden_dim": 64, "effective_precision": "compact"}

def _eval_adaptive_frequency_band_agent_worker(args: Tuple[int, int, str, int, int, int, str]) -> Tuple[int, int, np.ndarray]:
    chunk_idx, band_idx, weights_b64, num_frames, channels, hidden_dim, effective_precision = args
    if num_frames == 0 or not weights_b64:
        return chunk_idx, band_idx, np.zeros((0, channels), dtype=np.float32)

    try:
        weights_bytes = base64.b64decode(weights_b64)
        dtype = np.float32 if effective_precision == "archive" else np.float16
        weights_np = np.frombuffer(weights_bytes, dtype=dtype).astype(np.float32)
        weights_tensor = torch.from_numpy(weights_np.copy())

        model = DynamicBandAgentINR(num_freqs=12, hidden_dim=hidden_dim, out_channels=channels)
        
        idx = 0
        with torch.no_grad():
            for param in model.parameters():
                num_param = param.numel()
                param_data = weights_tensor[idx:idx + num_param].view(param.shape)
                param.copy_(param_data)
                idx += num_param

        coords = torch.linspace(-1.0, 1.0, steps=num_frames).unsqueeze(1)
        model.eval()
        with torch.no_grad():
            reconstructed = model(coords).clamp(-1.0, 1.0).numpy()

        return chunk_idx, band_idx, reconstructed.astype(np.float32)
    except Exception:
        return chunk_idx, band_idx, np.zeros((num_frames, channels), dtype=np.float32)

# =====================================================================
# BACKGROUND RUNNER & NEURAL ENCODING API
# =====================================================================

def run_background_encoding(task_id: str, content: bytes, filename: str, precision_mode: str = "auto"):
    tasks_db[task_id] = {
        "task_id": task_id,
        "progress": 5,
        "status": "running",
        "logs": [f"[NeuraFS Engine] Parameterizing '{filename}' (Mode: {precision_mode.upper()})..."]
    }

    pcm_bytes, detected_sr, detected_channels = decode_audio_to_pcm(content, filename)
    num_workers = get_optimal_worker_count()

    pcm_np = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
    remainder = len(pcm_np) % detected_channels
    if remainder != 0:
        pcm_np = pcm_np[:-remainder]

    pcm_np = pcm_np.reshape(-1, detected_channels)

    tasks_db[task_id]["logs"].append(f"[Native SR: {detected_sr}Hz] Subband Decomposition ({num_workers} Subbands)...")
    frequency_bands = split_waveform_into_bands(pcm_np, detected_sr, num_bands=num_workers)

    chunk_size_samples = detected_sr * 1  # Native 1-second chunks
    total_samples = pcm_np.shape[0]
    
    agent_tasks = []
    chunk_count = math.ceil(total_samples / chunk_size_samples)

    for chunk_idx in range(chunk_count):
        start_s = chunk_idx * chunk_size_samples
        end_s = min(total_samples, (chunk_idx + 1) * chunk_size_samples)

        for band_idx in range(num_workers):
            subband_slice = frequency_bands[band_idx][start_s:end_s]
            agent_tasks.append((chunk_idx, band_idx, subband_slice.tobytes(), detected_channels, detected_sr, precision_mode))

    total_tasks = len(agent_tasks)
    tasks_db[task_id]["logs"].append(f"[Neural Parameterization] Deploying Agents with Multi-Resolution STFT Loss...")

    results = []
    with Pool(processes=num_workers) as pool:
        for i in range(0, total_tasks, num_workers):
            batch = agent_tasks[i:i + num_workers]
            batch_results = pool.map(_fit_adaptive_frequency_band_agent_worker, batch)
            results.extend(batch_results)

            processed_count = min(i + num_workers, total_tasks)
            real_progress = round((processed_count / total_tasks) * 90) + 5
            
            avg_snr = np.mean([r.get("achieved_snr", 0) for r in batch_results])
            tasks_db[task_id]["progress"] = real_progress
            tasks_db[task_id]["logs"].append(f"[Progress] {processed_count}/{total_tasks} subbands parameterized. Avg SNR: {avg_snr:.1f} dB")

    results.sort(key=lambda x: (x["chunk_idx"], x["band_idx"]))

    tasks_db[task_id]["progress"] = 100
    tasks_db[task_id]["status"] = "completed"
    tasks_db[task_id]["logs"].append(f"[Archive Engine] Neural Parameterization Finished Successfully!")
    tasks_db[task_id]["result"] = {
        "file_name": filename,
        "sample_rate": detected_sr,
        "channels": detected_channels,
        "original_size": len(content),
        "num_bands": num_workers,
        "precision_mode": precision_mode,
        "neural_chunks": results
    }

@app.post("/api/v1/encode-neural-media-start")
@app.post("/api/v1/compress-neural-media-start") # Backward compatibility alias
async def encode_neural_media_start(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    task_id: str = Form(...),
    precision_mode: str = Form("auto")
):
    content = await file.read()
    background_tasks.add_task(run_background_encoding, task_id, content, file.filename, precision_mode)
    return {"status": "started", "task_id": task_id}

@app.get("/api/v1/task-status/{task_id}")
async def get_task_status(task_id: str):
    if task_id not in tasks_db:
        return {"status": "not_found", "progress": 0, "logs": []}
    return tasks_db[task_id]

@app.post("/api/v1/encode-lossless-binary")
@app.post("/api/v1/compress-lossless-binary")
async def encode_lossless_binary(payload: Dict[str, Any]):
    chunks_b64 = payload.get("chunks_b64", [])
    compressed_chunks = []
    for chunk_b64 in chunks_b64:
        raw_chunk = base64.b64decode(chunk_b64)
        compressed_lzma = lzma.compress(raw_chunk, format=lzma.FORMAT_XZ, preset=9)
        compressed_chunks.append(base64.b64encode(compressed_lzma).decode('ascii'))
    return {"status": "success", "compressed_chunks_b64": compressed_chunks}

@app.post("/api/v1/reconstruct-lossless-binary")
@app.post("/api/v1/decompress-lossless-binary")
async def reconstruct_lossless_binary(payload: Dict[str, Any]):
    chunks_b64 = payload.get("chunks_b64", [])
    decompressed_chunks = []
    try:
        for chunk_b64 in chunks_b64:
            compressed_lzma = base64.b64decode(chunk_b64)
            raw_chunk = lzma.decompress(compressed_lzma)
            decompressed_chunks.append(base64.b64encode(raw_chunk).decode('ascii'))
        return {"status": "success", "decompressed_chunks_b64": decompressed_chunks}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reconstruction error: {str(e)}")

@app.post("/api/v1/resynthesize-neural-media")
@app.post("/api/v1/decompress-neural-media")
async def resynthesize_neural_media(payload: Dict[str, Any]):
    chunks_data = payload.get("chunks", [])
    num_workers = get_optimal_worker_count()

    tasks = [
        (c["chunk_idx"], c.get("band_idx", 0), c["weights_b64"], c.get("num_frames", 0), c.get("channels", 2), c.get("hidden_dim", 128), c.get("effective_precision", "archive")) 
        for c in chunks_data
    ]
    
    reconstructed_evals = []
    with Pool(processes=num_workers) as pool:
        for i in range(0, len(tasks), num_workers):
            batch = tasks[i:i + num_workers]
            batch_results = pool.map(_eval_adaptive_frequency_band_agent_worker, batch)
            reconstructed_evals.extend(batch_results)

    chunk_groups: Dict[int, List[np.ndarray]] = {}
    for chunk_idx, band_idx, band_signal in reconstructed_evals:
        if chunk_idx not in chunk_groups:
            chunk_groups[chunk_idx] = []
        chunk_groups[chunk_idx].append(band_signal)

    full_pcm_arrays = []
    for chunk_idx in sorted(chunk_groups.keys()):
        summed_chunk = np.sum(chunk_groups[chunk_idx], axis=0)
        full_pcm_arrays.append(summed_chunk)

    if full_pcm_arrays:
        full_pcm = np.vstack(full_pcm_arrays)
    else:
        full_pcm = np.zeros((0, 2), dtype=np.float32)

    # 32-bit Float Output vs 16-bit Int Output
    has_archive_chunk = any(c.get("effective_precision") == "archive" for c in chunks_data)
    
    if has_archive_chunk:
        pcm_bytes = full_pcm.astype(np.float32).tobytes()
        bits_per_sample = 32
        audio_format = 3  # IEEE Float
    else:
        pcm_i16 = (np.clip(full_pcm, -1.0, 1.0) * 32767.0).astype(np.int16)
        pcm_bytes = pcm_i16.tobytes()
        bits_per_sample = 16
        audio_format = 1  # PCM Int

    return {
        "status": "success",
        "pcm_b64": base64.b64encode(pcm_bytes).decode('ascii'),
        "bits_per_sample": bits_per_sample,
        "audio_format": audio_format,
        "reconstructed_size": len(pcm_bytes)
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, access_log=False)