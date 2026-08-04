const express = require('express');
const fs = require('fs');
const path = require('path');
const multer = require('multer');
const HyperCompressorSDK = require('./hyper-compress-sdk');

const app = express();
const PORT = process.env.PORT || 3000;
const PYTHON_API_URL = process.env.PYTHON_API_URL || 'http://localhost:8000';

const sdk = new HyperCompressorSDK(PYTHON_API_URL);

const STORAGE_ROOT = path.join(__dirname, '..', 'storage');
const PUBLIC_DIR = path.join(__dirname, 'public');
const TEMP_DIR = path.join(__dirname, 'temp');

const activeTasks = {};

app.use(express.json());
app.use(express.urlencoded({ extended: true }));
app.use(express.static(PUBLIC_DIR));

const upload = multer({ dest: TEMP_DIR });

function initializeDirectories() {
    [STORAGE_ROOT, path.join(STORAGE_ROOT, 'media'), path.join(STORAGE_ROOT, 'documents'), PUBLIC_DIR, TEMP_DIR].forEach(dir => {
        if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
    });
}

function calculateFolderSize(dirPath) {
    if (!fs.existsSync(dirPath)) return 0;
    let total = 0;
    const items = fs.readdirSync(dirPath, { withFileTypes: true });
    for (const item of items) {
        const abs = path.join(dirPath, item.name);
        if (item.isDirectory()) total += calculateFolderSize(abs);
        else total += fs.statSync(abs).size;
    }
    return total;
}

function buildDirectoryTree(dirPath, relativePath = '') {
    if (!fs.existsSync(dirPath)) return [];
    const items = fs.readdirSync(dirPath, { withFileTypes: true });
    const tree = [];

    for (const item of items) {
        const itemRelPath = path.join(relativePath, item.name).replace(/\\/g, '/');
        const itemAbsPath = path.join(dirPath, item.name);

        if (item.isDirectory()) {
            tree.push({
                name: item.name,
                path: itemRelPath,
                type: 'folder',
                children: buildDirectoryTree(itemAbsPath, itemRelPath)
            });
        } else if (item.name.endsWith('.hcs')) {
            try {
                const header = sdk.readHcsHeader(itemAbsPath);
                const stats = fs.statSync(itemAbsPath);

                if (header.type === 'folder_bundle') {
                    const childNodes = header.files.map(f => ({
                        name: f.original_name,
                        hcs_file_name: item.name,
                        sub_path: f.relative_path,
                        path: `${itemRelPath}?subpath=${encodeURIComponent(f.relative_path)}`,
                        type: 'file',
                        file_category: f.type === 'neural_media' ? 'media' : 'document',
                        original_size: f.original_size,
                        compressed_size: Math.round(stats.size / header.files.length),
                        created_at: header.created_at,
                        compression_ratio: `${((1 - stats.size / header.original_size) * 100).toFixed(2)}%`
                    }));

                    tree.push({
                        name: header.folder_name,
                        path: itemRelPath,
                        type: 'folder',
                        children: childNodes
                    });
                } else {
                    const originalName = header.original_name || item.name;
                    tree.push({
                        name: originalName,
                        hcs_file_name: item.name,
                        path: itemRelPath,
                        type: 'file',
                        file_category: header.type === 'neural_media' ? 'media' : 'document',
                        original_size: header.original_size || stats.size,
                        compressed_size: stats.size,
                        created_at: header.created_at || stats.birthtime,
                        compression_ratio: `${((1 - stats.size / (header.original_size || stats.size)) * 100).toFixed(2)}%`
                    });
                }
            } catch (err) {
                console.warn(`[VFS Warning] Skipping non-standard or corrupt file '${itemAbsPath}':`, err.message);
            }
        }
    }
    return tree;
}

// REST Endpoints

app.get('/api/fs/tree', (req, res) => {
    try {
        const tree = buildDirectoryTree(STORAGE_ROOT);
        const totalUsed = calculateFolderSize(STORAGE_ROOT);
        res.json({ status: 'success', root: tree, used_bytes: totalUsed });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

app.post('/api/fs/folder', (req, res) => {
    try {
        const { folderPath } = req.body;
        if (!folderPath) return res.status(400).json({ error: 'Folder path is required' });

        const targetDir = path.join(STORAGE_ROOT, folderPath);
        if (!fs.existsSync(targetDir)) {
            fs.mkdirSync(targetDir, { recursive: true });
            return res.json({ status: 'success', message: 'Folder created', path: folderPath });
        }
        res.status(400).json({ error: 'Folder already exists' });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

app.delete('/api/fs/item', (req, res) => {
    try {
        const { targetPath } = req.body;
        if (!targetPath) return res.status(400).json({ error: 'Target path is required' });

        const cleanPath = targetPath.split('?')[0];
        const absPath = path.join(STORAGE_ROOT, cleanPath);
        if (!fs.existsSync(absPath)) return res.status(404).json({ error: 'Item not found' });

        fs.rmSync(absPath, { recursive: true, force: true });
        res.json({ status: 'success', message: 'Item deleted successfully' });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

app.get('/api/fs/tasks-status', (req, res) => {
    res.json(activeTasks);
});

// Using upload.any() to handle any incoming field name gracefully
app.post('/api/fs/upload-async', upload.any(), async (req, res) => {
    const files = req.files || (req.file ? [req.file] : []);
    if (!files.length) return res.status(400).json({ error: 'No files uploaded' });

    const taskId = req.body.taskId || ('task_' + Date.now());
    const precisionMode = req.body.precisionMode || 'auto';
    const relativePaths = [].concat(req.body.relativePaths || req.body.relativePath || []);
    const targetFolder = req.body.targetFolder || 'documents';
    const isFolderBundle = files.length > 1 || relativePaths.length > 0;

    res.json({ status: 'processing', taskId, message: 'Neural parameterization initiated' });

    activeTasks[taskId] = {
        id: taskId,
        fileName: isFolderBundle ? 'Folder Bundle' : files[0].originalname,
        progress: 5,
        log: `Initiating Neural Parameterization (Mode: ${precisionMode.toUpperCase()})...`,
        logsHistory: [`[NeuraFS Node.js] Mode: ${precisionMode.toUpperCase()}`],
        status: 'running'
    };

    try {
        const destDir = path.join(STORAGE_ROOT, targetFolder);
        if (!fs.existsSync(destDir)) fs.mkdirSync(destDir, { recursive: true });

        const onProgress = (progressPercent, statusLog, pythonLogs) => {
            activeTasks[taskId] = {
                id: taskId,
                fileName: isFolderBundle ? 'Folder Bundle' : files[0].originalname,
                progress: progressPercent,
                log: statusLog,
                logsHistory: ['[NeuraFS Node.js] Processing Neural/Lossless bands...', ...(pythonLogs || [])],
                status: 'running'
            };
        };

        if (isFolderBundle && files.length > 1) {
            const folderName = relativePaths[0] ? relativePaths[0].split('/')[0] : 'Uploaded_Folder';
            const fileItems = files.map((f, i) => ({
                tempFilePath: f.path,
                originalName: f.originalname,
                relativePath: relativePaths[i] || f.originalname
            }));

            await sdk.compressFolderBundle(fileItems, destDir, folderName, taskId, onProgress, precisionMode);

            fileItems.forEach(f => { if (fs.existsSync(f.tempFilePath)) fs.unlinkSync(f.tempFilePath); });

        } else {
            const file = files[0];
            await sdk.compressFile(file.path, destDir, file.originalname, taskId, onProgress, precisionMode);
            if (fs.existsSync(file.path)) fs.unlinkSync(file.path);
        }

        activeTasks[taskId].progress = 100;
        activeTasks[taskId].log = 'Neural parameterization complete!';
        activeTasks[taskId].status = 'completed';

        setTimeout(() => { delete activeTasks[taskId]; }, 5000);

    } catch (error) {
        files.forEach(f => { if (fs.existsSync(f.path)) fs.unlinkSync(f.path); });
        activeTasks[taskId].status = 'failed';
        activeTasks[taskId].log = `Error: ${error.message}`;
    }
});

app.get('/api/fs/stream', async (req, res) => {
    const rawPath = req.query.path;
    if (!rawPath) return res.status(400).send('File path required');

    const pathParts = rawPath.split('?subpath=');
    const relPath = pathParts[0];
    const subPath = pathParts[1] ? decodeURIComponent(pathParts[1]) : null;

    const absPath = path.join(STORAGE_ROOT, relPath);
    if (!fs.existsSync(absPath)) return res.status(404).send('File not found');

    try {
        const { buffer, originalName } = await sdk.decompressToBuffer(absPath, subPath);
        const ext = path.extname(originalName).toLowerCase();
        let contentType = 'application/octet-stream';

        if (['.txt', '.csv', '.log'].includes(ext)) contentType = 'text/plain';
        else if (ext === '.json') contentType = 'application/json';
        else if (ext === '.pdf') contentType = 'application/pdf';
        else if (['.wav', '.mp3', '.ogg', '.flac'].includes(ext)) contentType = 'audio/wav';
        else if (['.mp4', '.mkv', '.avi'].includes(ext)) contentType = 'video/mp4';

        res.setHeader('Content-Type', contentType);
        res.setHeader('Content-Disposition', `inline; filename="${originalName}"`);
        res.send(buffer);
    } catch (error) {
        res.status(500).send(`Resynthesis error: ${error.message}`);
    }
});

app.get('/api/fs/download/raw', async (req, res) => {
    const rawPath = req.query.path;
    if (!rawPath) return res.status(400).send('File path required');

    const pathParts = rawPath.split('?subpath=');
    const relPath = pathParts[0];
    const subPath = pathParts[1] ? decodeURIComponent(pathParts[1]) : null;

    const absPath = path.join(STORAGE_ROOT, relPath);
    if (!fs.existsSync(absPath)) return res.status(404).send('File not found');

    try {
        const { buffer, originalName } = await sdk.decompressToBuffer(absPath, subPath);
        res.setHeader('Content-Type', 'application/octet-stream');
        res.setHeader('Content-Disposition', `attachment; filename="${originalName}"`);
        res.send(buffer);
    } catch (error) {
        res.status(500).send(`Download error: ${error.message}`);
    }
});

app.get('/api/fs/download/compressed', (req, res) => {
    const rawPath = req.query.path;
    if (!rawPath) return res.status(400).send('File path required');

    const cleanPath = rawPath.split('?')[0];
    const absPath = path.join(STORAGE_ROOT, cleanPath);
    if (!fs.existsSync(absPath)) return res.status(404).send('File not found');

    const fileName = path.basename(absPath);
    res.setHeader('Content-Type', 'application/octet-stream');
    res.setHeader('Content-Disposition', `attachment; filename="${fileName}"`);
    res.sendFile(absPath);
});

app.use((req, res) => {
    res.sendFile(path.join(PUBLIC_DIR, 'index.html'));
});

app.listen(PORT, () => {
    initializeDirectories();
    console.log(`===================================================`);
    console.log(` NeuraFS Single-User Web Engine Running on port ${PORT}`);
    console.log(`===================================================`);
});