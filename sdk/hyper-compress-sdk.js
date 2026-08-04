const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

// System Master Encryption Key (32-Byte Key for AES-256-GCM)
const SYSTEM_MASTER_KEY = crypto.createHash('sha256').update('NeuraFS_System_Master_Encrypted_Container_Key_2026').digest();
const CONTAINER_MAGIC_HEADER = Buffer.from('NEURAFS1', 'utf-8'); // 8-Byte Proprietary Magic Header

function encryptPayloadBuffer(plaintextBuffer) {
    const iv = crypto.randomBytes(12); // 12-byte IV for AES-GCM
    const cipher = crypto.createCipheriv('aes-256-gcm', SYSTEM_MASTER_KEY, iv);
    
    const encryptedPayload = Buffer.concat([cipher.update(plaintextBuffer), cipher.final()]);
    const authTag = cipher.getAuthTag(); // 16-byte Authentication Tag

    // Binary Layout: [MAGIC (8B)] + [IV (12B)] + [AUTH TAG (16B)] + [ENCRYPTED PAYLOAD]
    return Buffer.concat([CONTAINER_MAGIC_HEADER, iv, authTag, encryptedPayload]);
}

function decryptPayloadBuffer(encryptedContainerBuffer) {
    if (encryptedContainerBuffer.length < 36) {
        throw new Error("Corrupted or invalid .hcs container file size.");
    }

    const magicHeader = encryptedContainerBuffer.subarray(0, 8);
    if (magicHeader.toString('utf-8') !== 'NEURAFS1') {
        throw new Error("Invalid or unauthorized .hcs container magic header.");
    }

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
    buffer.writeUInt16LE(audioFormat, 20); // 1 = PCM Int, 3 = IEEE Float
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
        let packageBuffer;

        if (fileBuffer.length >= 36 && fileBuffer.subarray(0, 8).toString('utf-8') === 'NEURAFS1') {
            packageBuffer = decryptPayloadBuffer(fileBuffer);
        } else {
            packageBuffer = fileBuffer;
        }

        if (packageBuffer.length < 4) {
            throw new Error("Invalid .hcs package size.");
        }

        const headerLength = packageBuffer.readUInt32BE(0);
        if (packageBuffer.length < 4 + headerLength) {
            throw new Error("Corrupted .hcs header length.");
        }

        const headerStr = packageBuffer.subarray(4, 4 + headerLength).toString('utf-8');
        return JSON.parse(headerStr);
    }

    async compressFile(inputPath, outputPath, overrideOriginalName = null, taskId = null, onProgress = null, precisionMode = 'auto') {
        if (!fs.existsSync(inputPath)) {
            throw new Error(`Input file not found: ${inputPath}`);
        }

        const fileName = overrideOriginalName || path.basename(inputPath);

        if (fileName.toLowerCase().endsWith('.hcs')) {
            fs.copyFileSync(inputPath, outputPath);
            const stats = fs.statSync(outputPath);
            return {
                fileName,
                originalSize: stats.size,
                compressedSize: stats.size,
                packagePath: outputPath
            };
        }

        const rawBuffer = fs.readFileSync(inputPath);
        const fileType = this.detectFileType(fileName);

        let headerMeta = {};
        const binaryPayloadBuffers = [];

        if (fileType === 'media') {
            const formData = new FormData();
            const blob = new Blob([rawBuffer], { type: 'application/octet-stream' });
            formData.append('file', blob, fileName);
            formData.append('task_id', taskId || 'task_' + Date.now());
            formData.append('precision_mode', precisionMode);

            const startRes = await fetch(`${this.apiBaseUrl}/api/v1/encode-neural-media-start`, {
                method: 'POST',
                body: formData
            });

            if (!startRes.ok) throw new Error(`API Error [Neural Encoding Start]: ${startRes.statusText}`);

            let apiResult = null;
            while (true) {
                await new Promise(r => setTimeout(r, 800));
                const statusRes = await fetch(`${this.apiBaseUrl}/api/v1/task-status/${taskId}`);
                const statusData = await statusRes.json();

                if (onProgress) {
                    const latestLog = statusData.logs ? statusData.logs[statusData.logs.length - 1] : 'Parameterizing Neural Bands...';
                    onProgress(statusData.progress || 10, latestLog, statusData.logs || []);
                }

                if (statusData.status === 'completed') {
                    apiResult = statusData.result;
                    break;
                } else if (statusData.status === 'failed') {
                    throw new Error('Python Neural Parameterization failed.');
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
                    effective_precision: chunk.effective_precision || 'archive',
                    offset: currentOffset,
                    length: chunkBuffer.length
                });

                currentOffset += chunkBuffer.length;
            }

            headerMeta = {
                type: 'neural_media',
                original_name: fileName,
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

                chunksMeta.push({
                    chunk_idx: idx,
                    offset: currentOffset,
                    length: chunkBuffer.length
                });

                currentOffset += chunkBuffer.length;
            }

            headerMeta = {
                type: 'lossless_binary',
                original_name: fileName,
                original_size: rawBuffer.length,
                created_at: new Date().toISOString(),
                chunks_info: chunksMeta
            };
        }

        const jsonHeaderBuffer = Buffer.from(JSON.stringify(headerMeta), 'utf-8');
        const headerLenBuffer = Buffer.alloc(4);
        headerLenBuffer.writeUInt32BE(jsonHeaderBuffer.length, 0);

        const payloadBuffer = Buffer.concat(binaryPayloadBuffers);
        
        // Unencrypted Raw Internal Package
        const unencryptedPackageBuffer = Buffer.concat([headerLenBuffer, jsonHeaderBuffer, payloadBuffer]);

        // Full AES-256-GCM Container Encryption with NEURAFS1 Magic Header
        const finalEncryptedContainerBuffer = encryptPayloadBuffer(unencryptedPackageBuffer);

        fs.writeFileSync(outputPath, finalEncryptedContainerBuffer);

        return {
            fileName,
            originalSize: rawBuffer.length,
            compressedSize: finalEncryptedContainerBuffer.length,
            packagePath: outputPath
        };
    }

    async decompressToBuffer(hcsFilePath) {
        if (!fs.existsSync(hcsFilePath)) throw new Error(`Package file not found: ${hcsFilePath}`);

        const fileBuffer = fs.readFileSync(hcsFilePath);
        let packageBuffer;
        if (fileBuffer.length >= 36 && fileBuffer.subarray(0, 8).toString('utf-8') === 'NEURAFS1') {
            packageBuffer = decryptPayloadBuffer(fileBuffer);
        } else {
            packageBuffer = fileBuffer;
        }

        const headerLength = packageBuffer.readUInt32BE(0);
        const header = JSON.parse(packageBuffer.subarray(4, 4 + headerLength).toString('utf-8'));
        const payloadBuffer = packageBuffer.subarray(4 + headerLength);

        if (header.type === 'neural_media') {
            const apiChunks = header.chunks_info.map(chunkInfo => ({
                chunk_idx: chunkInfo.chunk_idx,
                band_idx: chunkInfo.band_idx || 0,
                num_frames: chunkInfo.num_frames,
                channels: chunkInfo.channels || header.channels || 2,
                hidden_dim: chunkInfo.hidden_dim || 128,
                effective_precision: chunkInfo.effective_precision || header.precision_mode || 'archive',
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
            const bitsPerSample = result.bits_per_sample || 16;
            const audioFormat = result.audio_format || 1;

            const wavHeader = createWavHeader(
                rawPcmBuffer.length,
                header.sample_rate || 44100,
                header.channels || 2,
                bitsPerSample,
                audioFormat
            );

            return {
                buffer: Buffer.concat([wavHeader, rawPcmBuffer]),
                originalName: header.original_name,
                fileType: 'media'
            };

        } else {
            const chunksB64 = header.chunks_info.map(chunkInfo => 
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
                originalName: header.original_name,
                fileType: 'binary'
            };
        }
    }
}

module.exports = HyperCompressorSDK;