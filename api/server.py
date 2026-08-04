import os
import io
import json
import time
import base64
import lzma
import math
import queue
import shutil
import threading
import subprocess
import traceback
from contextlib import asynccontextmanager
import numpy as np
import scipy.signal as signal
import torch
import torch.nn as nn
import torch.multiprocessing as mp
from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks, HTTPException, Request
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

# Storage paths (Isolated .temp directory inside storage to prevent Node.js VFS race conditions)
STORAGE_ROOT = os.path.abspath(os.path.join(os.getcwd(), "storage"))
TEMP_ROOT = os.path.join(STORAGE_ROOT, ".temp")
PUBLIC_DIR = os.path.abspath(os.path.join(os.getcwd(), "storage_public_ui"))
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
queue_worker_thread = None

def sanitize_float(val: float, fallback: float = 0.0) -> float:
    if math.isnan(val) or math.isinf(val):
        return fallback
    return float(val)

# -------------------------------------------------------------------
# Queue Lifecycle & Persistent Consumer
# -------------------------------------------------------------------
function_queue_running = True

def queue_worker_loop():
    while function_queue_running:
        try:
            task_id = task_queue.get(timeout=1.0)
            if task_id:
                process_task_execution(task_id)
                task_queue.task_done()
        except queue.Empty:
            continue
        except Exception as e:
            print(f"[Queue Worker Loop Error]: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    global queue_worker_thread
    queue_worker_thread = threading.Thread(target=queue_worker_loop, daemon=True)
    queue_worker_thread.start()
    yield
    global function_queue_running
    function_queue_running = False

app = FastAPI(title="NeuraFS Multi-Agent Subband Engine", version="23.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------------------------------------------------
# DSP Subband Filterbank
# -------------------------------------------------------------------
def split_audio_into_subbands(pcm_signal: np.ndarray, sample_rate: int, num_bands: int):
    if num_bands <= 1:
        return [pcm_signal]

    nyquist = sample_rate / 2.0
    edges = np.logspace(np.log10(40.0), np.log10(min(20000.0, nyquist - 100)), num=num_bands + 1)
    
    subbands = []
    for i in range(num_bands):
        low = edges[i] / nyquist
        high = edges[i+1] / nyquist
        
        # Користење на SOS (Second-Order Sections) за нумеричка стабилност
        if i == 0:
            sos = signal.butter(4, high, btype='low', output='sos')
        elif i == num_bands - 1:
            sos = signal.butter(4, low, btype='high', output='sos')
        else:
            sos = signal.butter(4, [low, high], btype='band', output='sos')
            
        filtered = signal.sosfiltfilt(sos, pcm_signal)
        # Клипување за дополнителна заштита од прелив
        filtered = np.clip(filtered, -2.0, 2.0)
        subbands.append(filtered.astype(np.float32))

    return subbands

def create_wav_header(pcm_data: bytes, sample_rate: int = 44100, channels: int = 2, bits_per_sample: int = 16) -> bytes:
    data_size = len(pcm_data)
    byte_rate = sample_rate * channels * (bits_per_sample // 8)
    block_align = channels * (bits_per_sample // 8)
    
    header = bytearray()
    header.extend(b'RIFF')
    header.extend((36 + data_size).to_bytes(4, 'little'))
    header.extend(b'WAVE')
    header.extend(b'fmt ')
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
    audio_np = None
    sample_rate = 44100
    video_frames_np = None
    fps = 24.0

    try:
        cmd_audio = ['ffmpeg', '-i', 'pipe:0', '-vn', '-f', 's16le', '-ac', '2', '-ar', '44100', 'pipe:1']
        proc_a = subprocess.Popen(cmd_audio, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out_a, _ = proc_a.communicate(input=file_bytes)
        if proc_a.returncode == 0 and len(out_a) > 0:
            a_int16 = np.frombuffer(out_a, dtype=np.int16)
            audio_np = (a_int16.astype(np.float32) / 32768.0).reshape((-1, 2))
    except Exception:
        pass

    try:
        cmd_video = [
            'ffmpeg', '-i', 'pipe:0', '-an', 
            '-vf', 'scale=320:240,fps=12', 
            '-f', 'rawvideo', '-pix_fmt', 'rgb24', 'pipe:1'
        ]
        proc_v = subprocess.Popen(cmd_video, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out_v, _ = proc_v.communicate(input=file_bytes)
        if proc_v.returncode == 0 and len(out_v) > 0:
            frame_size = 320 * 240 * 3
            num_frames = len(out_v) // frame_size
            if num_frames > 0:
                raw_frames = np.frombuffer(out_v[:num_frames * frame_size], dtype=np.uint8)
                video_frames_np = raw_frames.reshape((num_frames, 240, 320, 3)).astype(np.float32) / 255.0
                fps = 12.0
    except Exception:
        pass

    has_audio = audio_np is not None and len(audio_np) > 0
    has_video = video_frames_np is not None and len(video_frames_np) > 0

    return has_video, has_audio, sample_rate, audio_np, video_frames_np, fps

# -------------------------------------------------------------------
# SIREN Subband Neural Architecture
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

class SirenSubbandAgent(nn.Module):
    def __init__(self, in_features=1, hidden_features=128, hidden_layers=2, out_features=1, omega_0=30.0):
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

# -------------------------------------------------------------------
# Multiprocessing Subband Worker Functions
# -------------------------------------------------------------------
def isolated_subband_worker(time_slice_idx, subband_idx, ch_idx, pcm_subband_data, sample_rate, hidden_dim, device_str, core_id, return_dict):
    try:
        if core_id is not None and psutil is not None:
            try:
                psutil.Process().cpu_affinity([core_id])
            except Exception:
                pass

        torch.set_num_threads(1)
        use_cuda = (device_str == "cuda") and torch.cuda.is_available()
        device = torch.device("cuda" if use_cuda else "cpu")

        num_samples = len(pcm_subband_data)
        t_coords = torch.linspace(-1.0, 1.0, steps=num_samples, device=device).unsqueeze(1)
        target_tensor = torch.from_numpy(pcm_subband_data).float().to(device).unsqueeze(1)

        agent = SirenSubbandAgent(in_features=1, hidden_features=hidden_dim, hidden_layers=2, out_features=1, omega_0=45.0).to(device)
        optimizer = torch.optim.Adam(agent.parameters(), lr=1e-3)
        criterion = nn.MSELoss()

        best_loss = 0.999
        patience = 0
        for step in range(150):
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

            if c_loss < 0.0001 or patience >= 15:
                break

        state_dict = agent.cpu().state_dict()
        buf = io.BytesIO()
        torch.save(state_dict, buf)
        weights_b64 = base64.b64encode(buf.getvalue()).decode('utf-8')

        key = f"sub_{time_slice_idx}_{subband_idx}_{ch_idx}"
        return_dict[key] = {
            "time_slice_idx": time_slice_idx,
            "subband_idx": subband_idx,
            "ch_idx": ch_idx,
            "num_samples": num_samples,
            "hidden_dim": hidden_dim,
            "loss": sanitize_float(best_loss, 0.0),
            "weights_b64": weights_b64
        }
    except Exception as e:
        print(f"[Subband Worker Error]: {e}")

def isolated_video_worker(frame_idx, frame_data, hidden_dim, device_str, core_id, return_dict):
    try:
        if core_id is not None and psutil is not None:
            try:
                psutil.Process().cpu_affinity([core_id])
            except Exception:
                pass

        torch.set_num_threads(1)
        use_cuda = (device_str == "cuda") and torch.cuda.is_available()
        device = torch.device("cuda" if use_cuda else "cpu")

        H, W, C = frame_data.shape
        y_coords = torch.linspace(-1, 1, H)
        x_coords = torch.linspace(-1, 1, W)
        grid_y, grid_x = torch.meshgrid(y_coords, x_coords, indexing='ij')
        coords = torch.stack([grid_x, grid_y], dim=-1).reshape(-1, 2).to(device)
        targets = torch.from_numpy(frame_data).float().reshape(-1, C).to(device)

        agent = SirenSubbandAgent(in_features=2, hidden_features=hidden_dim, hidden_layers=2, out_features=C, omega_0=30.0).to(device)
        optimizer = torch.optim.Adam(agent.parameters(), lr=1e-3)
        criterion = nn.MSELoss()

        for step in range(60):
            optimizer.zero_grad()
            pred = agent(coords)
            loss = criterion(pred, targets)
            loss.backward()
            optimizer.step()
            if loss.item() < 0.001:
                break

        state_dict = agent.cpu().state_dict()
        buf = io.BytesIO()
        torch.save(state_dict, buf)
        weights_b64 = base64.b64encode(buf.getvalue()).decode('utf-8')

        return_dict[f"v_{frame_idx}"] = {
            "frame_idx": frame_idx,
            "height": H,
            "width": W,
            "hidden_dim": hidden_dim,
            "weights_b64": weights_b64
        }
    except Exception as e:
        print(f"[Video Worker Error]: {e}")

# -------------------------------------------------------------------
# Master Neural Orchestration Engine
# -------------------------------------------------------------------
def process_task_execution(task_id: str):
    task_info = tasks.get(task_id)
    file_bytes = task_payloads.get(task_id)

    if not task_info or file_bytes is None:
        return

    filename = task_info["filename"]
    target_folder = task_info.get("targetFolder", "documents")
    precision_mode = task_info["precision_mode"]
    compute_device = task_info["compute_device"]
    parallel_enabled = task_info["parallel_enabled"]

    try:
        tasks[task_id]["status"] = "running"
        tasks[task_id]["logs"].append(f"[Waveform Analyzer] Analyzing input stream: {filename}")

        has_video, has_audio, sample_rate, audio_np, video_frames_np, fps = inspect_and_extract_media(file_bytes, filename)

        original_size = len(file_bytes)
        result_payload = None

        if not has_video and not has_audio:
            tasks[task_id]["logs"].append(f"[Router] Binary non-media file. LZMA fallback engaged.")
            chunk_size = 256 * 1024
            compressed_chunks = []
            for i in range(0, len(file_bytes), chunk_size):
                raw_chunk = file_bytes[i:i + chunk_size]
                compressed = lzma.compress(raw_chunk, preset=6)
                compressed_chunks.append(base64.b64encode(compressed).decode('utf-8'))

            result_payload = {
                "type": "lossless_binary",
                "original_filename": filename,
                "original_size": original_size,
                "compressed_chunks_b64": compressed_chunks
            }

        else:
            total_logical_cores = os.cpu_count() or 4
            available_cores = max(1, total_logical_cores - 2)
            cuda_available = torch.cuda.is_available()
            hidden_dim = 128 if precision_mode in ['compact', 'auto'] else 256
            
            manager = mp.Manager()
            return_dict = manager.dict()
            active_process_registry[task_id] = []

            num_subbands = max(1, available_cores)
            tasks[task_id]["logs"].append(f"[Subband Allocator] Core Budget: {available_cores} Cores -> Splitting audio into {num_subbands} frequency subbands")

            if has_audio:
                total_samples, channels = audio_np.shape
                slice_samples = int(sample_rate * 2.5)
                total_slices = math.ceil(total_samples / slice_samples)
                
                tasks[task_id]["logs"].append(f"[Time Segmenter] Total Slices: {total_slices} (2.5s each) across {channels} channels")

                all_work_units = []
                for slice_idx in range(total_slices):
                    s_start = slice_idx * slice_samples
                    s_end = min(s_start + slice_samples, total_samples)
                    
                    for ch in range(channels):
                        pcm_slice = audio_np[s_start:s_end, ch]
                        subband_signals = split_audio_into_subbands(pcm_slice, sample_rate, num_subbands)
                        
                        for sb_idx, sb_pcm in enumerate(subband_signals):
                            all_work_units.append((slice_idx, sb_idx, ch, sb_pcm))

                tasks[task_id]["logs"].append(f"[Master Orchestrator] Total Subband Neural Tasks: {len(all_work_units)}")

                for i in range(0, len(all_work_units), available_cores):
                    if tasks.get(task_id, {}).get("status") == "cancelled":
                        return

                    batch = all_work_units[i:i + available_cores]
                    procs = []
                    for idx, unit in enumerate(batch):
                        slice_i, sb_i, ch_i, sb_pcm = unit
                        c_bind = idx % available_cores
                        p = mp.Process(
                            target=isolated_subband_worker,
                            args=(slice_i, sb_i, ch_i, sb_pcm, sample_rate, hidden_dim, compute_device, c_bind, return_dict)
                        )
                        p.start()
                        procs.append(p)
                        active_process_registry[task_id].append(p)

                    for p in procs:
                        p.join()

                    completed = min(i + len(batch), len(all_work_units))
                    progress_pct = int((completed / len(all_work_units)) * (85 if has_video else 95))
                    tasks[task_id]["progress"] = progress_pct
                    tasks[task_id]["logs"].append(f"   [Subband Agent] Trained {completed}/{len(all_work_units)} subband units ({progress_pct}%)")

            if has_video:
                tasks[task_id]["logs"].append(f"[Video Inspector] Video stream detected ({len(video_frames_np)} frames). Dispatching to GPU/CPU workers.")
                video_device = "cuda" if cuda_available else "cpu"
                total_frames = len(video_frames_np)
                frame_batch_size = 4 if video_device == "cuda" else available_cores

                for f_i in range(0, total_frames, frame_batch_size):
                    if tasks.get(task_id, {}).get("status") == "cancelled":
                        return
                    f_batch = video_frames_np[f_i:f_i + frame_batch_size]
                    v_procs = []
                    for idx, frame_data in enumerate(f_batch):
                        f_idx = f_i + idx
                        proc = mp.Process(target=isolated_video_worker, args=(f_idx, frame_data, hidden_dim, video_device, None, return_dict))
                        proc.start()
                        v_procs.append(proc)
                        active_process_registry[task_id].append(proc)

                    for p in v_procs:
                        p.join()

                    completed_f = min(f_i + len(f_batch), total_frames)
                    progress_pct = 85 + int((completed_f / total_frames) * 12)
                    tasks[task_id]["progress"] = progress_pct
                    tasks[task_id]["logs"].append(f"   [Video Agent] Processed {completed_f}/{total_frames} frames ({progress_pct}%)")

            subband_results = [v for k, v in return_dict.items() if k.startswith("sub_")]
            video_results = [v for k, v in return_dict.items() if k.startswith("v_")]

            result_payload = {
                "type": "neural_video" if has_video else "neural_media",
                "original_filename": filename,
                "original_size": original_size,
                "sample_rate": sample_rate,
                "channels": audio_np.shape[1] if has_audio else 0,
                "num_subbands": num_subbands,
                "fps": fps if has_video else 0,
                "subband_units": subband_results,
                "video_units": video_results
            }

        # -----------------------------------------------------------
        # Isolated Temp File Writing to Prevent Node.js VFS Collisions
        # -----------------------------------------------------------
        save_dir = os.path.join(STORAGE_ROOT, target_folder)
        os.makedirs(save_dir, exist_ok=True)
        container_path = os.path.join(save_dir, f"{filename}.hcs")
        
        # Write to storage_temp using a non-VFS extension .tmp_raw
        temp_file_path = os.path.join(TEMP_ROOT, f"{task_id}.tmp_raw")

        with open(temp_file_path, 'w', encoding='utf-8') as f:
            json.dump(result_payload, f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())

        # Move atomically into final VFS destination
        shutil.move(temp_file_path, container_path)

        tasks[task_id]["progress"] = 100
        tasks[task_id]["status"] = "completed"
        tasks[task_id]["result"] = result_payload
        tasks[task_id]["logs"].append(f"[Master Assembler] Neural subband assembly complete! Saved to storage/{target_folder}/{filename}.hcs")

    except Exception as e:
        print(f"[Task Execution Error]: {traceback.format_exc()}")
        tasks[task_id]["status"] = "failed"
        tasks[task_id]["logs"].append(f"[Error] {str(e)}")
    finally:
        if task_id in active_process_registry:
            del active_process_registry[task_id]
        if task_id in task_payloads:
            del task_payloads[task_id]

# -------------------------------------------------------------------
# REST API Models & Router Endpoints
# -------------------------------------------------------------------
class ResynthesisChunkInfo(BaseModel):
    chunk_idx: int
    band_idx: int
    num_frames: int
    channels: int
    hidden_dim: int
    weights_b64: str

class ResynthesisRequest(BaseModel):
    chunks: List[ResynthesisChunkInfo]

class CancelRequest(BaseModel):
    taskId: str

class FolderRequest(BaseModel):
    folderPath: str

class DeleteRequest(BaseModel):
    targetPath: str

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_path = os.path.join(PUBLIC_DIR, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>NeuraFS Backend Engine Active</h1>"

@app.get("/api/fs/stream")
async def stream_neural_file(path: str):
    clean_path = os.path.normpath(path).lstrip("/\\")
    full_hcs_path = os.path.join(STORAGE_ROOT, clean_path)
    if not full_hcs_path.endswith(".hcs"):
        full_hcs_path += ".hcs"

    if not os.path.exists(full_hcs_path):
        raise HTTPException(status_code=404, detail=f"Container missing: {clean_path}")

    with open(full_hcs_path, "r", encoding="utf-8") as f:
        container = json.load(f)

    c_type = container.get("type")

    if c_type in ["neural_media", "neural_video"]:
        subband_units = container.get("subband_units", [])
        sample_rate = container.get("sample_rate", 44100)
        num_channels = container.get("channels", 2)

        if not subband_units:
            raise HTTPException(status_code=400, detail="Corrupted subband container")

        slices_dict = {}
        for unit in subband_units:
            ts = unit["time_slice_idx"]
            ch = unit["ch_idx"]
            if ts not in slices_dict:
                slices_dict[ts] = {}
            if ch not in slices_dict[ts]:
                slices_dict[ts][ch] = []
            slices_dict[ts][ch].append(unit)

        resynthesized_channels = [[] for _ in range(num_channels)]

        for ts_idx in sorted(slices_dict.keys()):
            for ch_idx in range(num_channels):
                units_in_ch = slices_dict[ts_idx].get(ch_idx, [])
                if not units_in_ch:
                    continue

                slice_num_samples = units_in_ch[0]["num_samples"]
                t_coords = torch.linspace(-1.0, 1.0, steps=slice_num_samples).unsqueeze(1)
                
                slice_pcm_sum = np.zeros(slice_num_samples, dtype=np.float32)

                for u in units_in_ch:
                    weights_bytes = base64.b64decode(u["weights_b64"])
                    buf = io.BytesIO(weights_bytes)
                    state_dict = torch.load(buf, map_location="cpu")

                    agent = SirenSubbandAgent(in_features=1, hidden_features=u["hidden_dim"], hidden_layers=2, out_features=1, omega_0=45.0)
                    agent.load_state_dict(state_dict)
                    agent.eval()

                    with torch.no_grad():
                        sub_pred = agent(t_coords).squeeze(1).numpy()
                        slice_pcm_sum += sub_pred

                resynthesized_channels[ch_idx].append(slice_pcm_sum)

        full_channels = []
        for ch_idx in range(num_channels):
            if resynthesized_channels[ch_idx]:
                full_channels.append(np.concatenate(resynthesized_channels[ch_idx]))
            else:
                full_channels.append(np.zeros(100, dtype=np.float32))

        audio_resynthesized = np.column_stack(full_channels)
        audio_pcm16 = (np.clip(audio_resynthesized, -1.0, 1.0) * 32767.0).astype(np.int16).tobytes()
        wav_bytes = create_wav_header(audio_pcm16, sample_rate=sample_rate, channels=num_channels)

        return Response(content=wav_bytes, media_type="audio/wav")

    elif c_type == "lossless_binary":
        compressed_chunks = container.get("compressed_chunks_b64", [])
        raw_bytes = bytearray()
        for chunk_b64 in compressed_chunks:
            comp_data = base64.b64decode(chunk_b64)
            raw_bytes.extend(lzma.decompress(comp_data))
        return Response(content=bytes(raw_bytes), media_type="application/octet-stream")

    raise HTTPException(status_code=400, detail="Unknown container format")

@app.post("/api/v1/resynthesize-neural-media")
async def resynthesize_neural_media(req: ResynthesisRequest):
    return {"status": "success", "message": "Legacy endpoint active"}

@app.post("/api/v1/encode-neural-media-start")
async def encode_neural_media_start(
    file: UploadFile = File(...),
    task_id: str = Form(...),
    precision_mode: str = Form("auto"),
    compute_device: str = Form("cpu"),
    parallel_enabled: str = Form("true")
):
    file_bytes = await file.read()
    task_payloads[task_id] = file_bytes
    tasks[task_id] = {
        "id": task_id,
        "status": "queued",
        "progress": 0,
        "logs": [f"[Queue Manager] Enqueued task {task_id}"],
        "result": None,
        "filename": file.filename,
        "precision_mode": precision_mode,
        "compute_device": compute_device,
        "parallel_enabled": parallel_enabled.lower() == "true"
    }
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

@app.post("/api/v1/task-cancel/{task_id}")
async def cancel_task_v1(task_id: str):
    return await cancel_fs_task(CancelRequest(taskId=task_id))

@app.get("/api/fs/tree")
async def get_fs_tree():
    total_used_bytes = 0

    def scan_dir(dir_path, rel_path=""):
        nonlocal total_used_bytes
        items = []
        if not os.path.exists(dir_path):
            return items

        for entry in os.scandir(dir_path):
            # 🚫 Целосно игнорирај го .temp и сите скриени фолдери/фајлови кои почнуваат со "."
            if entry.name.startswith("."):
                continue

            item_rel = os.path.join(rel_path, entry.name).replace("\\", "/")
            
            if entry.is_dir():
                items.append({
                    "name": entry.name,
                    "type": "folder",
                    "path": item_rel,
                    "children": scan_dir(entry.path, item_rel)
                })
            elif entry.name.endswith(".hcs"):
                hcs_size = entry.stat().st_size
                orig_name = entry.name[:-4]
                orig_size = hcs_size * 2
                file_cat = "media" if orig_name.lower().endswith(('.wav', '.mp3', '.flac', '.mp4', '.mkv', '.avi')) else "document"

                try:
                    with open(entry.path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        orig_name = data.get("original_filename", orig_name)
                        orig_size = data.get("original_size", hcs_size)
                        if data.get("type") in ["neural_media", "neural_video"]:
                            file_cat = "media"
                except (json.JSONDecodeError, Exception):
                    # Прескокни нецелосни или оштетени JSON фајлови
                    continue

                total_used_bytes += hcs_size
                ratio = f"{round((1 - (hcs_size / max(1, orig_size))) * 100, 1)}%" if orig_size > hcs_size else "1:1"

                items.append({
                    "name": orig_name,
                    "type": "file",
                    "file_category": file_cat,
                    "path": item_rel,
                    "original_size": orig_size,
                    "compressed_size": hcs_size,
                    "compression_ratio": ratio,
                    "created_at": time.ctime(entry.stat().st_mtime)
                })
        return items

    return {"root": scan_dir(STORAGE_ROOT), "used_bytes": total_used_bytes}

@app.post("/api/fs/upload-async")
async def upload_async_endpoint(
    files: List[UploadFile] = File(...),
    targetFolder: str = Form("documents"),
    taskId: str = Form(...),
    precisionMode: str = Form("auto"),
    computeDevice: str = Form("cpu"),
    parallelEnabled: str = Form("true")
):
    for file in files:
        file_bytes = await file.read()
        sub_id = taskId if len(files) == 1 else f"{taskId}_{file.filename}"
        task_payloads[sub_id] = file_bytes
        tasks[sub_id] = {
            "id": sub_id,
            "status": "queued",
            "progress": 0,
            "logs": [f"[Queue Manager] Enqueued {file.filename}"],
            "result": None,
            "filename": file.filename,
            "targetFolder": targetFolder,
            "precision_mode": precisionMode,
            "compute_device": computeDevice,
            "parallel_enabled": parallelEnabled.lower() == "true"
        }
        task_queue.put(sub_id)

    return {"status": "enqueued", "task_id": taskId}

@app.get("/api/fs/tasks-status")
async def get_all_tasks_status():
    status_response = {}
    for tid, tinfo in tasks.items():
        status_response[tid] = {
            "progress": tinfo.get("progress", 0),
            "status": tinfo.get("status", "running"),
            "log": tinfo["logs"][-1] if tinfo.get("logs") else "",
            "logsHistory": tinfo.get("logs", [])
        }
    return status_response

@app.post("/api/fs/task-cancel")
async def cancel_fs_task(req: CancelRequest):
    tid = req.taskId
    if tid == "all":
        while not task_queue.empty():
            try:
                task_queue.get_nowait()
                task_queue.task_done()
            except Exception:
                break
        for task_id in list(tasks.keys()):
            if task_id in active_process_registry:
                for proc in active_process_registry[task_id]:
                    if proc.is_alive():
                        try:
                            proc.kill()
                        except Exception:
                            pass
            tasks[task_id]["status"] = "cancelled"
        return {"status": "success"}

    if tid in tasks:
        tasks[tid]["status"] = "cancelled"
        if tid in active_process_registry:
            for proc in active_process_registry[tid]:
                if proc.is_alive():
                    try:
                        proc.kill()
                    except Exception:
                        pass
        return {"status": "success"}

    return {"status": "success"}

@app.post("/api/fs/folder")
async def create_folder(req: FolderRequest):
    os.makedirs(os.path.join(STORAGE_ROOT, req.folderPath), exist_ok=True)
    return {"status": "success"}

@app.delete("/api/fs/item")
async def delete_item(req: DeleteRequest):
    target = os.path.join(STORAGE_ROOT, req.targetPath)
    if os.path.exists(target + ".hcs"):
        os.remove(target + ".hcs")
    elif os.path.exists(target):
        if os.path.isdir(target):
            shutil.rmtree(target)
        else:
            os.remove(target)
    return {"status": "success"}

@app.get("/api/fs/download/raw")
async def download_raw_file(path: str):
    return await stream_neural_file(path)

@app.get("/api/fs/download/compressed")
async def download_compressed_file(path: str):
    clean_path = os.path.normpath(path).lstrip("/\\")
    full_hcs_path = os.path.join(STORAGE_ROOT, clean_path)
    if not full_hcs_path.endswith(".hcs"):
        full_hcs_path += ".hcs"
    if os.path.exists(full_hcs_path):
        return FileResponse(full_hcs_path, media_type="application/json", filename=os.path.basename(full_hcs_path))
    raise HTTPException(status_code=404, detail="Container file not found")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
