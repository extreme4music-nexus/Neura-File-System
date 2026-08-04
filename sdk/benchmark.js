const express = require('express');
const fs = require('fs');
const path = require('path');
const { performance } = require('perf_hooks');
const HyperCompressorSDK = require('./hyper-compress-sdk');

const app = express();
const PORT = 4000;
const PYTHON_API_URL = 'http://localhost:8000';

const sdk = new HyperCompressorSDK(PYTHON_API_URL);

const STORAGE_ROOT = path.join(__dirname, '..', 'storage');
const BENCHMARK_DIR = path.join(STORAGE_ROOT, 'benchmark_tests');
const PUBLIC_DIR = path.join(__dirname, '..', 'public');

app.use(express.static(PUBLIC_DIR));
app.use(express.json());

// Ensure benchmark directory exists
if (!fs.existsSync(BENCHMARK_DIR)) {
    fs.mkdirSync(BENCHMARK_DIR, { recursive: true });
}

function formatBytes(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

app.get('/api/benchmark/files', (req, res) => {
    try {
        const files = fs.readdirSync(BENCHMARK_DIR).filter(f => !f.startsWith('.'));
        res.json({ status: 'success', files });
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

app.post('/api/benchmark/run', async (req, res) => {
    const { filename } = req.body;
    if (!filename) return res.status(400).json({ error: 'Filename required' });

    const filePath = path.join(BENCHMARK_DIR, filename);
    if (!fs.existsSync(filePath)) return res.status(404).json({ error: 'File not found' });

    const originalSize = fs.statSync(filePath).size;
    const taskId = `bench_${Date.now()}_${filename}`;
    const targetDir = path.join(STORAGE_ROOT, 'media');

    try {
        const startMem = process.memoryUsage().heapUsed;
        const startTime = performance.now();

        // Run compression
        const result = await sdk.compressFile(
            filePath, 
            targetDir, 
            filename, 
            taskId, 
            null, // Silent progress for benchmark
            'auto', 
            'cpu', // Change to 'cuda' if testing GPU
            true
        );

        const endTime = performance.now();
        const endMem = process.memoryUsage().heapUsed;
        const hcsSize = fs.statSync(result.packagePath).size;

        // Fetch logs from Python API to extract DSP metrics (SI-SDR, LSD, etc.)
        const statusRes = await fetch(`${PYTHON_API_URL}/api/v1/task-status/${taskId}`);
        const statusData = await statusRes.json();
        
        let dspMetrics = "N/A (Binary)";
        if (statusData.logsHistory) {
            const verificationLog = statusData.logsHistory.find(log => log.includes('[Verification Agent] Analysis Report:'));
            if (verificationLog) {
                dspMetrics = verificationLog.replace('[Verification Agent] Analysis Report: ', '');
            }
        }

        // Run Reconstruction (Decode) Benchmark
        const decodeStartTime = performance.now();
        const decompressed = await sdk.decompressToBuffer(result.packagePath);
        const decodeEndTime = performance.now();

        const benchmarkData = {
            filename,
            original_size_bytes: originalSize,
            original_size: formatBytes(originalSize),
            hcs_size: formatBytes(hcsSize),
            compression_ratio: ((1 - (hcsSize / originalSize)) * 100).toFixed(2) + '%',
            encode_time_ms: Math.round(endTime - startTime),
            decode_time_ms: Math.round(decodeEndTime - decodeStartTime),
            ram_delta: formatBytes(Math.abs(endMem - startMem)),
            metrics: dspMetrics
        };

        // Clean up HCS container after test
        if (fs.existsSync(result.packagePath)) fs.unlinkSync(result.packagePath);

        res.json({ status: 'success', data: benchmarkData });

    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

app.listen(PORT, () => {
    console.log(`===================================================`);
    console.log(` NeuraFS Benchmark Suite Running on port ${PORT}`);
    console.log(` Place test files in /storage/benchmark_tests/`);
    console.log(`===================================================`);
});
