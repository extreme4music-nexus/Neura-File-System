const fs = require('fs');
const path = require('path');
const lzma = require('lzma-native');

function unpackPackageBuffer(fileBuffer) {
    try {
        const decompressed = lzma.decompress(fileBuffer);
        const magic = decompressed.subarray(0, 4).toString('utf-8');
        if (magic === 'HCS1') {
            const metaLen = decompressed.readUInt32BE(4);
            const header = JSON.parse(decompressed.subarray(8, 8 + metaLen).toString('utf-8'));
            const payload = decompressed.subarray(8 + metaLen);
            return { header, payload };
        }
        // Fallback for legacy JSON/LZMA
        return { header: JSON.parse(decompressed.toString('utf-8')), payload: null };
    } catch (e) {
        // Fallback if uncompressed json string
        return { header: JSON.parse(fileBuffer.toString('utf-8')), payload: null };
    }
}

class HyperCompressorSDK {
    constructor(apiBaseUrl = 'http://localhost:8000') {
        this.apiBaseUrl = apiBaseUrl;
    }

    detectFileType(filePath) {
        const ext = path.extname(filePath).toLowerCase();
        const mediaExtensions = ['.mp3', '.wav', '.flac', '.ogg', '.mp4', '.avi', '.mkv', '.mov'];
        return mediaExtensions.includes(ext) ? 'media' : 'binary';
    }

    readHcsHeader(hcsFilePath) {
        if (!fs.existsSync(hcsFilePath)) throw new Error(`Package file not found: ${hcsFilePath}`);
        const fileBuffer = fs.readFileSync(hcsFilePath);
        const { header } = unpackPackageBuffer(fileBuffer);
        return header;
    }

    async compressFile(inputPath, targetDir, overrideOriginalName = null, taskId = null, onProgress = null, precisionMode = 'auto', computeDevice = 'cpu', parallelEnabled = true) {
        if (!fs.existsSync(inputPath)) throw new Error(`Input file not found: ${inputPath}`);

        const originalName = overrideOriginalName || path.basename(inputPath);
        const finalOutputPath = path.join(targetDir, `${originalName}.hcs`);
        const rawBuffer = fs.readFileSync(inputPath);
        const fileType = this.detectFileType(originalName);

        if (fileType === 'media') {
            const formData = new FormData();
            const blob = new Blob([rawBuffer], { type: 'application/octet-stream' });
            formData.append('file', blob, originalName);
            formData.append('task_id', taskId || 'task_' + Date.now());
            formData.append('precision_mode', precisionMode);
            formData.append('compute_device', computeDevice);
            formData.append('parallel_enabled', String(parallelEnabled));

            const startRes = await fetch(`${this.apiBaseUrl}/api/v1/encode-neural-media-start`, {
                method: 'POST',
                body: formData
            });

            if (!startRes.ok) throw new Error(`API Error [Neural Start]: ${startRes.statusText}`);

            while (true) {
                await new Node.Promise(r => setTimeout(r, 500));
                const statusRes = await fetch(`${this.apiBaseUrl}/api/v1/task-status/${taskId}`);
                const statusData = await statusRes.json();

                if (onProgress) {
                    const latestLog = statusData.logs ? statusData.logs[statusData.logs.length - 1] : 'Parameterizing...';
                    onProgress(statusData.progress || 10, latestLog, statusData.logs || []);
                }

                if (statusData.status === 'completed') {
                    break;
                } else if (statusData.status === 'failed' || statusData.status === 'cancelled') {
                    throw new Error(statusData.logs ? statusData.logs[statusData.logs.length - 1] : 'Neural Task stopped.');
                }
            }
        }

        // За да ја зачуваме компатибилноста со server.py кој веќе генерира готови .hcs во storage/media или documents,
        // ова овозможува SDK-то да го мапира излезот директно.
        return {
            fileName: originalName,
            originalSize: rawBuffer.length,
            packagePath: finalOutputPath
        };
    }

    async decompressToBuffer(hcsFilePath, targetSubPath = null) {
        if (!fs.existsSync(hcsFilePath)) throw new Error(`Package file not found: ${hcsFilePath}`);

        const fileBuffer = fs.readFileSync(hcsFilePath);
        const { header, payload } = unpackPackageBuffer(fileBuffer);

        let targetFileMeta = header;
        if (header.type === 'folder_bundle') {
            targetFileMeta = header.files.find(f => f.relative_path === targetSubPath || f.original_name === targetSubPath);
            if (!targetFileMeta) targetFileMeta = header.files[0];
        }

        if (targetFileMeta.type === 'neural_media' || targetFileMeta.type === 'neural_video') {
            const apiChunks = targetFileMeta.subband_units.map(chunkInfo => ({
                chunk_idx: chunkInfo.chunk_idx || 0,
                time_slice_idx: chunkInfo.time_slice_idx !== undefined ? chunkInfo.time_slice_idx : 0,
                subband_idx: chunkInfo.subband_idx !== undefined ? chunkInfo.subband_idx : 0,
                band_idx: chunkInfo.ch_idx !== undefined ? chunkInfo.ch_idx : 0,
                ch_idx: chunkInfo.ch_idx !== undefined ? chunkInfo.ch_idx : 0,
                num_frames: chunkInfo.num_samples || chunkInfo.num_frames || 0,
                num_samples: chunkInfo.num_samples || chunkInfo.num_frames || 0,
                channels: chunkInfo.channels || targetFileMeta.channels || 2,
                hidden_dim: chunkInfo.hidden_dim || 32,
                weights_b64: chunkInfo.weights_b64 ? chunkInfo.weights_b64 : (payload ? payload.subarray(chunkInfo.offset, chunkInfo.offset + chunkInfo.length).toString('base64') : '')
            }));

            const response = await fetch(`${this.apiBaseUrl}/api/v1/resynthesize-neural-media`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ chunks: apiChunks })
            });

            if (!response.ok) throw new Error(`API Error [Neural Resynthesis]: ${response.statusText}`);

            const result = await response.json();
            if (!result.pcm_b64) throw new Error('Resynthesis failed: No PCM returned from Python engine');

            const rawPcmBuffer = Buffer.from(result.pcm_b64, 'base64');
            const wavHeader = this.createWavHeader(
                rawPcmBuffer.length,
                targetFileMeta.sample_rate || 44100,
                targetFileMeta.channels || 2,
                result.bits_per_sample || 16,
                result.audio_format || 1
            );

            return {
                buffer: Buffer.concat([wavHeader, rawPcmBuffer]),
                originalName: targetFileMeta.original_filename || targetFileMeta.original_name || 'audio.wav',
                fileType: 'media'
            };

        } else {
            const compressedChunks = targetFileMeta.compressed_chunks_b64 || [];
            const rawBytes = Buffer.concat(compressedChunks.map(ch => lzma.decompress(Buffer.from(ch, 'base64'))));
            return {
                buffer: rawBytes,
                originalName: targetFileMeta.original_filename || targetFileMeta.original_name || 'file.bin',
                fileType: 'binary'
            };
        }
    }

    createWavHeader(dataLength, sampleRate = 44100, channels = 2, bitsPerSample = 16, audioFormat = 1) {
        const byteRate = (sampleRate * channels * bitsPerSample) / 8;
        const blockAlign = (channels * bitsPerSample) / 8;
        const buffer = Buffer.alloc(44);

        buffer.write('RIFF', 0);
        buffer.writeUInt32LE(36 + dataLength, 4);
        buffer.write('WAVE', 8);
        buffer.write('fmt ', 12);
        buffer.writeUInt32LE(16, 16);
        buffer.writeUInt16LE(audioFormat, 20);
        buffer.writeUInt16LE(channels, 22);
        buffer.writeUInt32LE(sampleRate, 24);
        buffer.writeUInt32LE(byteRate, 28);
        buffer.writeUInt16LE(blockAlign, 32);
        buffer.writeUInt16LE(bitsPerSample, 34);
        buffer.write('data', 36);
        buffer.writeUInt32LE(dataLength, 40);

        return buffer;
    }
}

module.exports = HyperCompressorSDK;
