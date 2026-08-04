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
        return { header: JSON.parse(decompressed.toString('utf-8')), payload: null };
    } catch (e) {
        return { header: JSON.parse(fileBuffer.toString('utf-8')), payload: null };
    }
}

class HyperCompressorSDK {
    constructor(apiBaseUrl = 'http://localhost:8000') {
        this.apiBaseUrl = apiBaseUrl;
    }

    readHcsHeader(hcsFilePath) {
        if (!fs.existsSync(hcsFilePath)) throw new Error(`Package file not found: ${hcsFilePath}`);
        const fileBuffer = fs.readFileSync(hcsFilePath);
        const { header } = unpackPackageBuffer(fileBuffer);
        return header;
    }

    async decompressToBuffer(hcsFilePath) {
        if (!fs.existsSync(hcsFilePath)) throw new Error(`Package file not found: ${hcsFilePath}`);

        const fileBuffer = fs.readFileSync(hcsFilePath);
        const { header, payload } = unpackPackageBuffer(fileBuffer);

        if (header.type === 'neural_media') {
            let apiChunks = [];
            if (payload && header.subband_units) {
                apiChunks = header.subband_units.map(unit => ({
                    time_slice_idx: unit.time_slice_idx || 0,
                    subband_idx: unit.subband_idx || 0,
                    ch_idx: unit.ch_idx || 0,
                    num_samples: unit.num_samples || 0,
                    hidden_dim: unit.hidden_dim || 32,
                    weights_b64: payload.subarray(unit.offset, unit.offset + unit.length).toString('base64')
                }));
            }

            const response = await fetch(`${this.apiBaseUrl}/api/v1/resynthesize-neural-media`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ chunks: apiChunks })
            });

            if (!response.ok) throw new Error(`Resynthesis failed: ${response.statusText}`);
            const result = await response.json();

            const rawPcmBuffer = Buffer.from(result.pcm_b64, 'base64');
            const wavHeader = this.createWavHeader(
                rawPcmBuffer.length,
                header.sample_rate || 44100,
                header.channels || 2,
                result.bits_per_sample || 16,
                result.audio_format || 1
            );

            return {
                buffer: Buffer.concat([wavHeader, rawPcmBuffer]),
                originalName: header.original_filename || 'audio.wav',
                fileType: 'media'
            };
        } else {
            const compressedChunks = header.compressed_chunks_b64 || [];
            const rawBytes = Buffer.concat(compressedChunks.map(ch => lzma.decompress(Buffer.from(ch, 'base64'))));
            return {
                buffer: rawBytes,
                originalName: header.original_filename || 'file.bin',
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
