const HyperCompressorSDK = require('./hyper-compress-sdk');
const fs = require('fs');

async function testSDK() {
    console.log('--- Initializing Node.js SDK Test ---');
    const sdk = new HyperCompressorSDK('http://localhost:8000');

    // 1. Create a mock document
    const testDocPath = './sample_document.txt';
    const sampleText = 'Production Neural Data Compression. '.repeat(500);
    fs.writeFileSync(testDocPath, sampleText);

    // 2. Compress Document to .hcs Package
    console.log('Compressing text document...');
    const result = await sdk.compressFile(testDocPath, './sample_document.txt.hcs');
    console.log('Compression Result:', result);

    // 3. Decompress back to original
    console.log('Decompressing .hcs package...');
    await sdk.decompressFile('./sample_document.txt.hcs', './restored_document.txt');

    // 4. Verify integrity
    const restoredText = fs.readFileSync('./restored_document.txt', 'utf-8');
    console.log('Integrity Test:', sampleText === restoredText ? 'PASSED (100% Lossless)' : 'FAILED');
}

testSDK().catch(console.error);