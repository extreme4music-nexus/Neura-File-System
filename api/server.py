import os
import io
import json
import time
import base64
import lzma
import math
import queue
import shutil
import struct
import hashlib
import threading
import subprocess
import traceback
from contextlib import asynccontextmanager
import numpy as np
import scipy.signal as signal
import torch
import torch.nn as nn
import torch.multiprocessing as mp
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, FileResponse, HTMLResponse
from pydantic import BaseModel
from typing import List, Optional

try:
    import psutil
except ImportError:
    psutil = None

try:
    mp.set_start_method('spawn', force=True)
except RuntimeError:
    pass

MAGIC_HEADER = b'HCS1'

STORAGE_ROOT = os.path.abspath(os.path.join(os.getcwd(), "..", "storage"))
if not os.path.exists(STORAGE_ROOT):
    STORAGE_ROOT = os.path.abspath(os.path.join(os.getcwd(), "storage"))

TEMP_ROOT = os.path.join(STORAGE_ROOT, ".temp")
PUBLIC_DIR = os.path.abspath(os.path.join(os.getcwd(), "..", "public"))
if not os.path.exists(PUBLIC_DIR):
    PUBLIC_DIR = os.path.abspath(os.path.join(os.getcwd(), "public"))

os.makedirs(STORAGE_ROOT, exist_ok=True)
os.makedirs(TEMP_ROOT, exist_ok=True)
os.makedirs(os.path.join(STORAGE_ROOT, "documents"), exist_ok=True)
os.makedirs(os.path.join(STORAGE_ROOT, "media"), exist_ok=True)

tasks = {}
task_payloads = {}
active_process_registry = {}
task_queue = queue.Queue()

def get_safe_path(base_dir: str, req_path: str) -> str:
    clean_path = os.path.normpath(req_path).lstrip("/\\")
    full_path = os.path.abspath(os.path.join(base_dir, clean_path))
    if not full_path.startswith(os.path.abspath(base_dir)):
        raise HTTPException(status_code=403, detail="Access denied: Invalid path trajectory.")
    return full_path

def sanitize_float(val: float, fallback: float = 0.0) -> float:
    if math.isnan(val) or math.isinf(val):
        return fallback
    return float(val)

# Standarized HCS1 Binary Container (Magic Header + Manifest + Raw FP16 Payload)
def pack_hcs_binary_container(metadata: dict, raw_blobs: list) -> bytes:
    meta_json_bytes = json.dumps(metadata, ensure_ascii=False).encode('utf-8')
    meta_len = len(meta_json_bytes)
    
    blob_bytes = bytearray()
    for blob in raw_blobs:
        blob_bytes.extend(blob)
        
    payload = struct.pack('>4sI', MAGIC_HEADER, meta_len) + meta_json_bytes + bytes(blob_bytes)
    return lzma.compress(payload, preset=9)

def unpack_hcs_binary_container(compressed_bytes: bytes):
    try:
        decompressed = lzma.decompress(compressed_bytes)
        magic, meta_len = struct.unpack('>4sI', decompressed[:8])
        if magic != MAGIC_HEADER:
            return json.loads(decompressed.decode('utf-8')), None
        
        meta_json = decompressed[8:8 + meta_len].decode('utf-8')
        metadata = json.loads(meta_json)
        raw_blobs_data = decompressed[8 + meta_len:]
        return metadata, raw_blobs_data
    except Exception:
        return json.loads(compressed_bytes.decode('utf-8')), None

def estimate_signal_complexity(pcm_subband: np.ndarray, subband_idx: int, num_bands: int):
    if len(pcm_subband) == 0:
        return 40, 0.0001
    rms = np.sqrt(np.mean(pcm_subband ** 2)) + 1e-9
    zero_crossings = np.sum(np.abs(np.diff(np.sign(pcm_subband)))) / (2 * len(pcm_subband))
    fft_mag = np.abs(np.fft.rfft(pcm_subband)) + 1e-9
    geo_mean = np.exp(np.mean(np.log(fft_mag)))
    arith_mean = np.mean(fft_mag)
    spectral_flatness = geo_mean / arith_mean
    complexity_score = np.clip((rms * 2.0) + (spectral_flatness * 1.5) + (zero_crossings * 0.5), 0.1, 1.0)
    max_steps = int(30 + (complexity_score * 170))
    if subband_idx == 0:
        target_loss = 0.00002
    elif subband_idx < int(num_bands * 0.7):
        target_loss = 0.000015
    else:
        target_loss = 0.00035
    return max_steps, target_loss

def split_audio_into_subbands(pcm_signal: np.ndarray, sample_rate: int, num_bands: int):
    if num_bands <= 1:
        return [pcm_signal]
    nyquist = sample_rate / 2.0
    edges = np.logspace(np.log10(40.0), np.log10(min(20000.0, nyquist - 100)), num=num_bands + 1)
    subbands = []
    for i in range(num_bands):
        low = edges[i] / nyquist
        high = edges[i+1] / nyquist
        if i == 0:
            sos = signal.butter(4, high, btype='low', output='sos')
        elif i == num_bands - 1:
            sos = signal.butter(4, low, btype='high', output='sos')
        else:
            sos = signal.butter(4, [low, high], btype='band', output='sos')
        filtered = signal.sosfiltfilt(sos, pcm_signal)
        subbands.append(np.clip(filtered, -2.0, 2.0).astype(np.float32))
    return subbands

def create_wav_header(pcm_data: bytes, sample_rate: int = 44100, channels: int = 2, bits_per_sample: int = 16) -> bytes:
    data_size = len(pcm_data)
    byte_rate = sample_rate * channels * (bits_per_sample // 8)
    block_align = channels * (bits_per_sample // 8)
    header = bytearray()
    header.extend(b'RIFF')
    header.extend((36 + data_size).to_bytes(4, 'little'))
    header.extend(b'WAVEfmt ')
    header.extend((16).to_bytes(4, 'little'))
    header.extend((1).to_bytes(2, 'little'))
    header.extend(channels.to_bytes(2, 'little'))
    header.extend(sample_rate.to_bytes(4, 'little'))
    header.extend(byte_rate.to_bytes(4, 'little'))
    header.extend(block_align.to_bytes(2, 'little'))
    header.extend(bits_per_sample.to_bytes(2, 'little'))
    header.extend(b'data')
    header.extend(data_size.to_bytes(4, 'little'))
    return bytes(header) + pcm_data

def inspect_and_extract_media(file_bytes: bytes, filename: str):
    audio_np, video_frames_np = None, None
    sample_rate, fps = 44100, 24.0
    try:
        cmd_audio = ['ffmpeg', '-i', 'pipe:0', '-vn', '-f', 's16le', '-ac', '2', '-ar', '44100', 'pipe:1']
        proc_a = subprocess.Popen(cmd_audio, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out_a, _ = proc_a.communicate(input=file_bytes)
        if proc_a.returncode == 0 and len(out_a) > 0:
            a_int16 = np.frombuffer(out_a, dtype=np.int16)
            audio_np = (a_int16.astype(np.float32) / 32768.0).reshape((-1, 2))
    except Exception:
        pass
    return False, (audio_np is not None and len(audio_np) > 0), sample_rate, audio_np, None, fps

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
                self.linear.weight.uniform_(-np.sqrt(6 / self.in_features) / self.omega_0, np.sqrt(6 / self.in_features) / self.omega_0)

    def forward(self, input):
        return torch.sin(self.omega_0 * self.linear(input))

class SirenAgent(nn.Module):
    def __init__(self, in_features=1, hidden_features=32, hidden_layers=2, out_features=1, omega_0=30.0):
        super().__init__()
        self.net = nn.ModuleList()
        self.net.append(SineLayer(in_features, hidden_features, is_first=True, omega_0=omega_0))
        for _ in range(hidden_layers):
            self.net.append(SineLayer(hidden_features, hidden_features, is_first=False, omega_0=omega_0))
        final_linear = nn.Linear(hidden_features, out_features)
        with torch.no_grad():
            final_linear.weight.uniform_(-np.sqrt(6 / hidden_features) / omega_0, np.sqrt(6 / hidden_features) / omega_0)
        self.net.append(final_linear)

    def forward(self, coords):
        x = coords
        for layer in self.net:
            x = layer(x)
        return x

def serialize_agent_raw_bytes(agent: nn.Module) -> bytes:
    state = agent.state_dict()
    buffer = bytearray()
    for k, v in state.items():
        arr = v.cpu().numpy().astype(np.float16)
        buffer.extend(arr.tobytes())
    return bytes(buffer)

def deserialize_agent_from_bytes(agent: nn.Module, raw_bytes: bytes):
    curr_state = agent.state_dict()
    offset = 0
    new_state = {}
    for k, v in curr_state.items():
        shape = v.shape
        num_elements = np.prod(shape)
        byte_size = num_elements * 2 # float16 = 2 bytes
        chunk = raw_bytes[offset:offset + byte_size]
        arr = np.frombuffer(chunk, dtype=np.float16).reshape(shape).astype(np.float32)
        new_state[k] = torch.from_numpy(arr)
        offset += byte_size
    agent.load_state_dict(new_state)

def isolated_subband_worker(time_slice_idx, subband_idx, ch_idx, pcm_subband_data, sample_rate, num_bands, hidden_dim, device_str, core_id, return_dict):
    try:
        if core_id is not None and psutil is not None:
            try:
                psutil.Process().cpu_affinity([core_id])
            except Exception:
                pass

        torch.set_num_threads(1)
        device = torch.device("cuda" if (device_str == "cuda" and torch.cuda.is_available()) else "cpu")
        num_samples = len(pcm_subband_data)
        t_coords = torch.linspace(-1.0, 1.0, steps=num_samples, device=device).unsqueeze(1)
        target_tensor = torch.from_numpy(pcm_subband_data).float().to(device).unsqueeze(1)

        max_steps, target_loss = estimate_signal_complexity(pcm_subband_data, subband_idx, num_bands)
        agent = SirenAgent(in_features=1, hidden_features=hidden_dim, hidden_layers=2, out_features=1, omega_0=45.0).to(device)
        
        optimizer = torch.optim.Adam(agent.parameters(), lr=1e-3)
        criterion = nn.MSELoss()

        best_loss = 0.999
        patience = 0
        for step in range(max_steps):
            optimizer.zero_grad()
            pred = agent(t_coords)
            loss = criterion(pred, target_tensor)
            loss.backward()
            optimizer.step()
            c_loss = loss.item()
            if math.isnan(c_loss) or math.isinf(c_loss):
                continue
            if c_loss < best_loss - 1e-5:
                best_loss = c_loss
                patience = 0
            else:
                patience += 1
            if c_loss < target_loss or patience >= 12:
                break

        raw_weight_bytes = serialize_agent_raw_bytes(agent)
        key = f"sub_{time_slice_idx}_{subband_idx}_{ch_idx}"
        return_dict[key] = {
            "time_slice_idx": time_slice_idx, "subband_idx": subband_idx, "ch_idx": ch_idx,
            "num_samples": num_samples, "hidden_dim": hidden_dim,
            "loss": sanitize_float(best_loss, 0.0), "raw_bytes": raw_weight_bytes
        }
    except Exception as e:
        print(f"[Subband Worker Error]: {e}")

def run_reconstruction_validation(original_audio_np, subband_results, sample_rate, hidden_dim):
    try:
        if original_audio_np is None or len(subband_results) == 0:
            return {"si_sdr": 0.0, "lsd": 0.0, "mse": 0.0}
        
        slices_dict = {}
        for u in subband_results:
            ts, ch = u["time_slice_idx"], u["ch_idx"]
            slices_dict.setdefault(ts, {}).setdefault(ch, []).append(u)

        num_channels = original_audio_np.shape[1]
        resynthesized_channels = [[] for _ in range(num_channels)]

        for ts_idx in sorted(slices_dict.keys()):
            for ch_idx in range(num_channels):
                units = slices_dict[ts_idx].get(ch_idx, [])
                if not units: continue
                num_samples = units[0]["num_samples"]
                t_coords = torch.linspace(-1.0, 1.0, steps=num_samples).unsqueeze(1)
                slice_sum = np.zeros(num_samples, dtype=np.float32)
                for u in units:
                    agent = SirenAgent(in_features=1, hidden_features=u.get("hidden_dim", hidden_dim), hidden_layers=2, out_features=1, omega_0=45.0)
                    deserialize_agent_from_bytes(agent, u["raw_bytes"])
                    agent.eval()
                    with torch.no_grad():
                        slice_sum += agent(t_coords).squeeze(1).numpy()
                resynthesized_channels[ch_idx].append(slice_sum)

        resyn_audio = np.column_stack([np.concatenate(ch) for ch in resynthesized_channels if ch])
        min_len = min(len(original_audio_np), len(resyn_audio))
        s_target, s_estimate = original_audio_np[:min_len, 0], resyn_audio[:min_len, 0]

        mse = float(np.mean((s_target - s_estimate) ** 2))
        alpha = np.dot(s_estimate, s_target) / (np.dot(s_target, s_target) + 1e-9)
        e_target = alpha * s_target
        e_noise = s_estimate - e_target
        si_sdr = float(10 * np.log10(np.sum(e_target ** 2) / (np.sum(e_noise ** 2) + 1e-9)))

        _, _, stft_orig = signal.stft(s_target, fs=sample_rate, nperseg=512)
        _, _, stft_resyn = signal.stft(s_estimate, fs=sample_rate, nperseg=512)
        lsd = float(np.mean(np.sqrt(np.mean((np.log10(np.abs(stft_orig) + 1e-7) - np.log10(np.abs(stft_resyn) + 1e-7)) ** 2, axis=0))))

        return {"si_sdr": round(si_sdr, 2), "lsd": round(lsd, 3), "mse": round(mse, 6)}
    except Exception:
        return {"si_sdr": 0.0, "lsd": 0.0, "mse": 0.0}

def process_task_execution(task_id: str):
    task_info = tasks.get(task_id)
    file_bytes = task_payloads.get(task_id)
    if not task_info or file_bytes is None:
        return

    filename = task_info["filename"]
    precision_mode = task_info["precision_mode"]
    compute_device = task_info["compute_device"]
    parallel_enabled = task_info.get("parallel_enabled", True)

    manager = mp.Manager()
    try:
        tasks[task_id]["status"] = "running"
        has_video, has_audio, sample_rate, audio_np, _, _ = inspect_and_extract_media(file_bytes, filename)
        target_folder = "media" if has_audio else "documents"
        original_size = len(file_bytes)
        file_sha256 = hashlib.sha256(file_bytes).hexdigest()

        if not has_audio:
            chunk_size = 256 * 1024
            compressed_chunks = [base64.b64encode(lzma.compress(file_bytes[i:i+chunk_size], preset=9)).decode('utf-8') for i in range(0, len(file_bytes), chunk_size)]
            result_payload = {
                "type": "lossless_binary",
                "original_filename": filename,
                "original_size": original_size,
                "sha256": file_sha256,
                "compressed_chunks_b64": compressed_chunks
            }
            raw_blobs = []
        else:
            total_logical_cores = os.cpu_count() or 4
            available_cores = max(1, total_logical_cores - 2) if parallel_enabled else 1
            hidden_dim = 32 if precision_mode in ['compact', 'auto'] else 48
            return_dict = manager.dict()
            num_subbands = max(1, available_cores)

            total_samples, channels = audio_np.shape
            slice_samples = int(sample_rate * 2.5)
            total_slices = math.ceil(total_samples / slice_samples)

            all_work_units = []
            for slice_idx in range(total_slices):
                s_start = slice_idx * slice_samples
                s_end = min(s_start + slice_samples, total_samples)
                for ch in range(channels):
                    pcm_slice = audio_np[s_start:s_end, ch]
                    subband_signals = split_audio_into_subbands(pcm_slice, sample_rate, num_subbands)
                    for sb_idx, sb_pcm in enumerate(subband_signals):
                        all_work_units.append((slice_idx, sb_idx, ch, sb_pcm))

            for i in range(0, len(all_work_units), available_cores):
                batch = all_work_units[i:i + available_cores]
                procs = [mp.Process(target=isolated_subband_worker, args=(unit[0], unit[1], unit[2], unit[3], sample_rate, num_subbands, hidden_dim, compute_device, idx % available_cores, return_dict)) for idx, unit in enumerate(batch)]
                for p in procs: p.start()
                for p in procs: p.join()

            subband_results = [v for k, v in return_dict.items() if k.startswith("sub_")]
            
            # Reconstruction & Validation metrics
            rec_metrics = run_reconstruction_validation(audio_np, subband_results, sample_rate, hidden_dim)

            raw_blobs = []
            current_offset = 0
            subband_manifest = []

            for unit in subband_results:
                raw_w_bytes = unit.pop("raw_bytes")
                unit["offset"] = current_offset
                unit["length"] = len(raw_w_bytes)
                raw_blobs.append(raw_w_bytes)
                current_offset += len(raw_w_bytes)
                subband_manifest.append(unit)

            result_payload = {
                "type": "neural_media",
                "original_filename": filename,
                "original_size": original_size,
                "original_samples": total_samples,
                "sha256": file_sha256,
                "sample_rate": sample_rate,
                "channels": channels,
                "num_subbands": num_subbands,
                "reconstruction_metrics": rec_metrics,
                "subband_units": subband_manifest
            }

        save_dir = os.path.join(STORAGE_ROOT, target_folder)
        os.makedirs(save_dir, exist_ok=True)
        container_path = os.path.join(save_dir, f"{filename}.hcs")
        temp_file_path = os.path.join(TEMP_ROOT, f"{task_id}.tmp_raw")

        binary_hcs = pack_hcs_binary_container(result_payload, raw_blobs)
        with open(temp_file_path, 'wb') as f:
            f.write(binary_hcs)
            f.flush()
            os.fsync(f.fileno())

        shutil.move(temp_file_path, container_path)
        tasks[task_id]["progress"] = 100
        tasks[task_id]["status"] = "completed"
        tasks[task_id]["result"] = result_payload
        tasks[task_id]["logs"].append(f"[Master Assembler] Saved: storage/{target_folder}/{filename}.hcs")

    except Exception as e:
        print(f"[Task Execution Error]: {traceback.format_exc()}")
        tasks[task_id]["status"] = "failed"
        tasks[task_id]["logs"].append(f"[Error] {str(e)}")
    finally:
        manager.shutdown()
        task_payloads.pop(task_id, None)

def read_hcs_container(full_hcs_path: str):
    with open(full_hcs_path, "rb") as f:
        file_bytes = f.read()
    return unpack_hcs_binary_container(file_bytes)

def queue_worker_loop():
    while True:
        try:
            task_id = task_queue.get(timeout=1.0)
            if task_id:
                process_task_execution(task_id)
                task_queue.task_done()
        except queue.Empty:
            continue

@asynccontextmanager
async def lifespan(app: FastAPI):
    threading.Thread(target=queue_worker_loop, daemon=True).start()
    yield

app = FastAPI(title="NeuraFS Compressed Subband Engine", version="25.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

class ResynthesisChunkInfo(BaseModel):
    time_slice_idx: Optional[int] = 0
    subband_idx: Optional[int] = 0
    ch_idx: Optional[int] = 0
    num_samples: Optional[int] = 0
    hidden_dim: Optional[int] = 32
    weights_b64: Optional[str] = None
    offset: Optional[int] = None
    length: Optional[int] = None

class ResynthesisRequest(BaseModel):
    chunks: List[ResynthesisChunkInfo]

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    return "<h1>NeuraFS Backend Engine Active</h1>"

@app.post("/api/v1/resynthesize-neural-media")
async def resynthesize_neural_media(req: ResynthesisRequest):
    if not req.chunks:
        raise HTTPException(status_code=400, detail="No neural chunks provided")

    slices_dict = {}
    for chunk in req.chunks:
        ts = chunk.time_slice_idx or 0
        ch = chunk.ch_idx or 0
        slices_dict.setdefault(ts, {}).setdefault(ch, []).append(chunk)

    num_channels = max((c.ch_idx or 0) for c in req.chunks) + 1
    resynthesized_channels = [[] for _ in range(num_channels)]

    for ts_idx in sorted(slices_dict.keys()):
        for ch_idx in range(num_channels):
            units = slices_dict[ts_idx].get(ch_idx, [])
            if not units: continue
            slice_samples = units[0].num_samples or 110250
            t_coords = torch.linspace(-1.0, 1.0, steps=slice_samples).unsqueeze(1)
            pcm_sum = np.zeros(slice_samples, dtype=np.float32)

            for u in units:
                agent = SirenAgent(in_features=1, hidden_features=u.hidden_dim or 32, hidden_layers=2, out_features=1, omega_0=45.0)
                if u.weights_b64:
                    raw_w = base64.b64decode(u.weights_b64)
                    deserialize_agent_from_bytes(agent, raw_w)
                agent.eval()
                with torch.no_grad():
                    pcm_sum += agent(t_coords).squeeze(1).numpy()
            resynthesized_channels[ch_idx].append(pcm_sum)

    audio_resynthesized = np.column_stack([np.concatenate(ch) for ch in resynthesized_channels if ch])
    max_val = np.max(np.abs(audio_resynthesized))
    if max_val > 1.0:
        audio_resynthesized /= max_val

    audio_pcm16 = (np.clip(audio_resynthesized, -1.0, 1.0) * 32767.0).astype(np.int16)
    return {
        "status": "success",
        "pcm_b64": base64.b64encode(audio_pcm16.tobytes()).decode('utf-8'),
        "bits_per_sample": 16,
        "audio_format": 1
    }

@app.get("/api/fs/stream")
async def stream_neural_file(path: str):
    full_hcs_path = get_safe_path(STORAGE_ROOT, path)
    if not full_hcs_path.endswith(".hcs"):
        full_hcs_path += ".hcs"
    if not os.path.exists(full_hcs_path):
        raise HTTPException(status_code=404, detail=f"Container missing: {path}")

    container, raw_blobs_data = read_hcs_container(full_hcs_path)
    c_type = container.get("type")

    if c_type == "neural_media":
        subband_units = container.get("subband_units", [])
        sample_rate = container.get("sample_rate", 44100)
        num_channels = container.get("channels", 2)

        slices_dict = {}
        for unit in subband_units:
            ts, ch = unit["time_slice_idx"], unit["ch_idx"]
            slices_dict.setdefault(ts, {}).setdefault(ch, []).append(unit)

        resynthesized_channels = [[] for _ in range(num_channels)]
        device = torch.device("cpu")

        for ts_idx in sorted(slices_dict.keys()):
            for ch_idx in range(num_channels):
                units_in_ch = slices_dict[ts_idx].get(ch_idx, [])
                if not units_in_ch: continue
                num_samples = units_in_ch[0]["num_samples"]
                t_coords = torch.linspace(-1.0, 1.0, steps=num_samples).unsqueeze(1).to(device)
                slice_pcm_sum = np.zeros(num_samples, dtype=np.float32)

                for u in units_in_ch:
                    agent = SirenAgent(in_features=1, hidden_features=u.get("hidden_dim", 32), hidden_layers=2, out_features=1, omega_0=45.0).to(device)
                    off, length = u["offset"], u["length"]
                    raw_w_bytes = raw_blobs_data[off:off + length]
                    deserialize_agent_from_bytes(agent, raw_w_bytes)
                    agent.eval()
                    with torch.no_grad():
                        slice_pcm_sum += agent(t_coords).squeeze(1).cpu().numpy()
                resynthesized_channels[ch_idx].append(slice_pcm_sum)

        full_channels = [np.concatenate(ch) if ch else np.zeros(100, dtype=np.float32) for ch in resynthesized_channels]
        audio_resynthesized = np.column_stack(full_channels)
        max_val = np.max(np.abs(audio_resynthesized))
        if max_val > 1.0:
            audio_resynthesized /= max_val

        audio_pcm16 = (np.clip(audio_resynthesized, -1.0, 1.0) * 32767.0).astype(np.int16).tobytes()
        wav_bytes = create_wav_header(audio_pcm16, sample_rate=sample_rate, channels=num_channels)
        return Response(content=wav_bytes, media_type="audio/wav")

    elif c_type == "lossless_binary":
        compressed_chunks = container.get("compressed_chunks_b64", [])
        raw_bytes = bytearray()
        for chunk_b64 in compressed_chunks:
            raw_bytes.extend(lzma.decompress(base64.b64decode(chunk_b64)))
        return Response(content=bytes(raw_bytes), media_type="application/octet-stream")

    raise HTTPException(status_code=400, detail="Unknown container format")

@app.post("/api/v1/encode-neural-media-start")
async def encode_neural_media_start(file: UploadFile = File(...), task_id: str = Form(...), precision_mode: str = Form("auto"), compute_device: str = Form("cpu"), parallel_enabled: str = Form("true")):
    file_bytes = await file.read()
    task_payloads[task_id] = file_bytes
    tasks[task_id] = {"id": task_id, "status": "queued", "progress": 0, "logs": [f"Enqueued {file.filename}"], "result": None, "filename": file.filename, "precision_mode": precision_mode, "compute_device": compute_device, "parallel_enabled": parallel_enabled.lower() == "true"}
    task_queue.put(task_id)
    return {"status": "queued", "task_id": task_id}

@app.get("/api/v1/task-status/{task_id}")
async def get_task_status_v1(task_id: str):
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    res = dict(tasks[task_id])
    res["logsHistory"] = res.get("logs", [])
    res["log"] = res["logs"][-1] if res.get("logs") else ""
    return res

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
