const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const SYSTEM_MASTER_KEY = crypto.createHash('sha256').update('NeuraFS_System_Master_Encrypted_Container_Key_2026').digest();
const CONTAINER_MAGIC_HEADER = Buffer.from('NEURAFS1', 'utf-8');

function generateHashFilename() {
    return crypto.randomBytes(8).toString('hex') + '.hcs';
}

function encryptPayloadBuffer(plaintextBuffer) {
    const iv = crypto.randomBytes(12);
    const cipher = crypto.createCipheriv('aes-256-gcm', SYSTEM_MASTER_KEY, iv);
    const encryptedPayload = Buffer.concat([cipher.update(plaintextBuffer), cipher.final()]);
    const authTag = cipher.getAuthTag();
    return Buffer.concat([CONTAINER_MAGIC_HEADER, iv, authTag, encryptedPayload]);
}

function decryptPayloadBuffer(encryptedContainerBuffer) {
    if (encryptedContainerBuffer.length < 36) throw new Error("Corrupted .hcs container.");
    const magicHeader = encryptedContainerBuffer.subarray(0, 8);
    if (magicHeader.toString('utf-8') !== 'NEURAFS1') throw new Error("Invalid .hcs container header.");

    const iv = encryptedContainerBuffer.subarray(8, 20);
    const authTag = encryptedContainerBuffer.subarray(20, 36);
    const ciphertext = encryptedContainerBuffer.subarray(36);

    const decipher = crypto.createDecipheriv('aes-256-gcm', SYSTEM_MASTER_KEY, iv);
    decipher.setAuthTag(authTag);
    return Buffer.concat([decipher.update(ciphertext), decipher.final()]);
}

function createWavHeader(dataLength, sampleRate = 44100, channels = 2, bitsPerSample = 16, audioFormat = 1) {
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
        let packageBuffer = (fileBuffer.length >= 36 && fileBuffer.subarray(0, 8).toString('utf-8') === 'NEURAFS1')
            ? decryptPayloadBuffer(fileBuffer) : fileBuffer;

        const headerLength = packageBuffer.readUInt32BE(0);
        return JSON.parse(packageBuffer.subarray(4, 4 + headerLength).toString('utf-8'));
    }

    async compressFile(inputPath, targetDir, overrideOriginalName = null, taskId = null, onProgress = null, precisionMode = 'auto', computeDevice = 'cpu', parallelEnabled = true) {
        if (!fs.existsSync(inputPath)) throw new Error(`Input file not found: ${inputPath}`);

        const originalName = overrideOriginalName || path.basename(inputPath);
        const obfuscatedHcsName = generateHashFilename();
        const finalOutputPath = path.join(targetDir, obfuscatedHcsName);
        const rawBuffer = fs.readFileSync(inputPath);
        const fileType = this.detectFileType(originalName);

        let headerMeta = {};
        const binaryPayloadBuffers = [];

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

            let apiResult = null;
            while (true) {
                await new Promise(r => setTimeout(r, 600));
                const statusRes = await fetch(`${this.apiBaseUrl}/api/v1/task-status/${taskId}`);
                const statusData = await statusRes.json();

                if (onProgress) {
                    const latestLog = statusData.logs ? statusData.logs[statusData.logs.length - 1] : 'Parameterizing...';
                    onProgress(statusData.progress || 10, latestLog, statusData.logs || []);
                }

                if (statusData.status === 'completed') {
                    apiResult = statusData.result;
                    break;
                } else if (statusData.status === 'failed' || statusData.status === 'cancelled') {
                    throw new Error(statusData.logs ? statusData.logs[statusData.logs.length - 1] : 'Neural Task stopped.');
                }
            }

            const chunksMeta = [];
            let currentOffset = 0;

            for (let idx = 0; idx < apiResult.neural_chunks.length; idx++) {
                const chunk = apiResult.neural_chunks[idx];
                const chunkBuffer = Buffer.from(chunk.weights_b64, 'base64');
                binaryPayloadBuffers.push(chunkBuffer);

                chunksMeta.push({
                    chunk_idx: chunk.chunk_idx,
                    band_idx: chunk.band_idx || 0,
                    num_frames: chunk.num_frames,
                    channels: chunk.channels,
                    hidden_dim: chunk.hidden_dim,
                    offset: currentOffset,
                    length: chunkBuffer.length
                });

                currentOffset += chunkBuffer.length;
            }

            headerMeta = {
                type: 'neural_media',
                original_name: originalName,
                original_size: rawBuffer.length,
                sample_rate: apiResult.sample_rate || 44100,
                channels: apiResult.channels || 2,
                num_bands: apiResult.num_bands || 1,
                precision_mode: precisionMode,
                created_at: new Date().toISOString(),
                chunks_info: chunksMeta
            };

        } else {
            const chunkSize = 256 * 1024;
            const chunksB64 = [];
            for (let i = 0; i < rawBuffer.length; i += chunkSize) {
                chunksB64.push(rawBuffer.subarray(i, i + chunkSize).toString('base64'));
            }

            const batchResponse = await fetch(`${this.apiBaseUrl}/api/v1/encode-lossless-binary`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ chunks_b64: chunksB64 })
            });

            if (!batchResponse.ok) throw new Error(`API Error [Binary Encoding]: ${batchResponse.statusText}`);

            const batchResult = await batchResponse.json();
            const chunksMeta = [];
            let currentOffset = 0;

            for (let idx = 0; idx < batchResult.compressed_chunks_b64.length; idx++) {
                const chunkBuffer = Buffer.from(batchResult.compressed_chunks_b64[idx], 'base64');
                binaryPayloadBuffers.push(chunkBuffer);

                chunksMeta.push({ chunk_idx: idx, offset: currentOffset, length: chunkBuffer.length });
                currentOffset += chunkBuffer.length;
            }

            headerMeta = {
                type: 'lossless_binary',
                original_name: originalName,
                original_size: rawBuffer.length,
                created_at: new Date().toISOString(),
                chunks_info: chunksMeta
            };
        }

        const jsonHeaderBuffer = Buffer.from(JSON.stringify(headerMeta), 'utf-8');
        const headerLenBuffer = Buffer.alloc(4);
        headerLenBuffer.writeUInt32BE(jsonHeaderBuffer.length, 0);

        const payloadBuffer = Buffer.concat(binaryPayloadBuffers);
        const unencryptedPackageBuffer = Buffer.concat([headerLenBuffer, jsonHeaderBuffer, payloadBuffer]);
        const finalEncryptedContainerBuffer = encryptPayloadBuffer(unencryptedPackageBuffer);

        fs.writeFileSync(finalOutputPath, finalEncryptedContainerBuffer);

        return {
            fileName: originalName,
            obfuscatedName: obfuscatedHcsName,
            originalSize: rawBuffer.length,
            compressedSize: finalEncryptedContainerBuffer.length,
            packagePath: finalOutputPath
        };
    }

    async compressFolderBundle(fileItems, targetDir, folderName, taskId = null, onProgress = null, precisionMode = 'auto', computeDevice = 'cpu', parallelEnabled = true) {
        const obfuscatedHcsName = generateHashFilename();
        const finalOutputPath = path.join(targetDir, obfuscatedHcsName);

        const manifestFiles = [];
        const binaryPayloadBuffers = [];
        let globalOffset = 0;
        let totalOriginalSize = 0;

        for (let i = 0; i < fileItems.length; i++) {
            const item = fileItems[i];
            const rawBuffer = fs.readFileSync(item.tempFilePath);
            totalOriginalSize += rawBuffer.length;
            const fileType = this.detectFileType(item.originalName);

            if (fileType === 'media') {
                const formData = new FormData();
                const blob = new Blob([rawBuffer], { type: 'application/octet-stream' });
                formData.append('file', blob, item.originalName);
                formData.append('task_id', `${taskId}_file_${i}`);
                formData.append('precision_mode', precisionMode);
                formData.append('compute_device', computeDevice);
                formData.append('parallel_enabled', String(parallelEnabled));

                const startRes = await fetch(`${this.apiBaseUrl}/api/v1/encode-neural-media-start`, {
                    method: 'POST',
                    body: formData
                });

                if (!startRes.ok) throw new Error(`API Error [Neural Start]: ${startRes.statusText}`);

                let apiResult = null;
                while (true) {
                    await new Promise(r => setTimeout(r, 600));
                    const statusRes = await fetch(`${this.apiBaseUrl}/api/v1/task-status/${taskId}_file_${i}`);
                    const statusData = await statusRes.json();

                    if (statusData.status === 'completed') {
                        apiResult = statusData.result;
                        break;
                    } else if (statusData.status === 'failed' || statusData.status === 'cancelled') {
                        throw new Error(`Neural Task cancelled/failed for ${item.relativePath}`);
                    }
                }

                const chunksMeta = [];
                for (let idx = 0; idx < apiResult.neural_chunks.length; idx++) {
                    const chunk = apiResult.neural_chunks[idx];
                    const chunkBuffer = Buffer.from(chunk.weights_b64, 'base64');
                    binaryPayloadBuffers.push(chunkBuffer);

                    chunksMeta.push({
                        chunk_idx: chunk.chunk_idx,
                        band_idx: chunk.band_idx || 0,
                        num_frames: chunk.num_frames,
                        channels: chunk.channels,
                        hidden_dim: chunk.hidden_dim,
                        offset: globalOffset,
                        length: chunkBuffer.length
                    });

                    globalOffset += chunkBuffer.length;
                }

                manifestFiles.push({
                    relative_path: item.relativePath,
                    original_name: item.originalName,
                    type: 'neural_media',
                    original_size: rawBuffer.length,
                    sample_rate: apiResult.sample_rate || 44100,
                    channels: apiResult.channels || 2,
                    chunks_info: chunksMeta
                });

            } else {
                const chunkSize = 256 * 1024;
                const chunksB64 = [];
                for (let j = 0; j < rawBuffer.length; j += chunkSize) {
                    chunksB64.push(rawBuffer.subarray(j, j + chunkSize).toString('base64'));
                }

                const batchResponse = await fetch(`${this.apiBaseUrl}/api/v1/encode-lossless-binary`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ chunks_b64: chunksB64 })
                });

                if (!batchResponse.ok) throw new Error(`API Error [Binary Encoding]: ${batchResponse.statusText}`);

                const batchResult = await batchResponse.json();
                const chunksMeta = [];

                for (let idx = 0; idx < batchResult.compressed_chunks_b64.length; idx++) {
                    const chunkBuffer = Buffer.from(batchResult.compressed_chunks_b64[idx], 'base64');
                    binaryPayloadBuffers.push(chunkBuffer);

                    chunksMeta.push({ chunk_idx: idx, offset: globalOffset, length: chunkBuffer.length });
                    globalOffset += chunkBuffer.length;
                }

                manifestFiles.push({
                    relative_path: item.relativePath,
                    original_name: item.originalName,
                    type: 'lossless_binary',
                    original_size: rawBuffer.length,
                    chunks_info: chunksMeta
                });
            }
        }

        const headerMeta = {
            type: 'folder_bundle',
            folder_name: folderName,
            original_size: totalOriginalSize,
            created_at: new Date().toISOString(),
            files: manifestFiles
        };

        const jsonHeaderBuffer = Buffer.from(JSON.stringify(headerMeta), 'utf-8');
        const headerLenBuffer = Buffer.alloc(4);
        headerLenBuffer.writeUInt32BE(jsonHeaderBuffer.length, 0);

        const payloadBuffer = Buffer.concat(binaryPayloadBuffers);
        const unencryptedPackageBuffer = Buffer.concat([headerLenBuffer, jsonHeaderBuffer, payloadBuffer]);
        const finalEncryptedContainerBuffer = encryptPayloadBuffer(unencryptedPackageBuffer);
        fs.writeFileSync(finalOutputPath, finalEncryptedContainerBuffer);

        return {
            folderName,
            obfuscatedName: obfuscatedHcsName,
            originalSize: totalOriginalSize,
            compressedSize: finalEncryptedContainerBuffer.length,
            packagePath: finalOutputPath
        };
    }

    async decompressToBuffer(hcsFilePath, targetSubPath = null) {
        if (!fs.existsSync(hcsFilePath)) throw new Error(`Package file not found: ${hcsFilePath}`);

        const fileBuffer = fs.readFileSync(hcsFilePath);
        let packageBuffer = (fileBuffer.length >= 36 && fileBuffer.subarray(0, 8).toString('utf-8') === 'NEURAFS1')
            ? decryptPayloadBuffer(fileBuffer) : fileBuffer;

        const headerLength = packageBuffer.readUInt32BE(0);
        const header = JSON.parse(packageBuffer.subarray(4, 4 + headerLength).toString('utf-8'));
        const payloadBuffer = packageBuffer.subarray(4 + headerLength);

        let targetFileMeta = header;
        if (header.type === 'folder_bundle') {
            targetFileMeta = header.files.find(f => f.relative_path === targetSubPath || f.original_name === targetSubPath);
            if (!targetFileMeta) targetFileMeta = header.files[0];
        }

        if (targetFileMeta.type === 'neural_media') {
            const apiChunks = targetFileMeta.chunks_info.map(chunkInfo => ({
                chunk_idx: chunkInfo.chunk_idx,
                band_idx: chunkInfo.band_idx || 0,
                num_frames: chunkInfo.num_frames,
                channels: chunkInfo.channels || targetFileMeta.channels || 2,
                hidden_dim: chunkInfo.hidden_dim || 128,
                weights_b64: payloadBuffer.subarray(chunkInfo.offset, chunkInfo.offset + chunkInfo.length).toString('base64')
            }));

            const response = await fetch(`${this.apiBaseUrl}/api/v1/resynthesize-neural-media`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ chunks: apiChunks })
            });

            if (!response.ok) throw new Error(`API Error [Neural Resynthesis]: ${response.statusText}`);

            const result = await response.json();
            const rawPcmBuffer = Buffer.from(result.pcm_b64, 'base64');

            const wavHeader = createWavHeader(
                rawPcmBuffer.length,
                targetFileMeta.sample_rate || 44100,
                targetFileMeta.channels || 2,
                result.bits_per_sample || 16,
                result.audio_format || 1
            );

            return {
                buffer: Buffer.concat([wavHeader, rawPcmBuffer]),
                originalName: targetFileMeta.original_name,
                fileType: 'media'
            };

        } else {
            const chunksB64 = targetFileMeta.chunks_info.map(chunkInfo => 
                payloadBuffer.subarray(chunkInfo.offset, chunkInfo.offset + chunkInfo.length).toString('base64')
            );

            const response = await fetch(`${this.apiBaseUrl}/api/v1/reconstruct-lossless-binary`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ chunks_b64: chunksB64 })
            });

            if (!response.ok) throw new Error(`API Error [Binary Reconstruction]: ${response.statusText}`);

            const result = await response.json();
            return {
                buffer: Buffer.concat(result.decompressed_chunks_b64.map(b64 => Buffer.from(b64, 'base64'))),
                originalName: targetFileMeta.original_name,
                fileType: 'binary'
            };
        }
    }
}

module.exports = HyperCompressorSDK;
