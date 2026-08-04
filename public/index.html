<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NeuraFS Storage Explorer</title>
    <!-- Tailwind CSS CDN -->
    <script src="https://cdn.tailwindcss.com"></script>
    <!-- FontAwesome Icons -->
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <!-- Monaco Code Editor CDN -->
    <script src="https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.38.0/min/vs/loader.min.js"></script>
    <style>
        .context-menu {
            display: none;
            position: absolute;
            z-index: 1000;
            background: #ffffff;
            border: 1px solid #e2e8f0;
            box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
            border-radius: 0.5rem;
            min-width: 220px;
            padding: 0.25rem 0;
        }
        .context-menu button {
            width: 100%;
            text-align: left;
            padding: 0.5rem 1rem;
            font-size: 0.875rem;
            color: #334155;
            display: flex;
            align-items: center;
            gap: 0.75rem;
        }
        .context-menu button:hover {
            background-color: #f1f5f9;
            color: #0284c7;
        }
        .no-select {
            -webkit-touch-callout: none;
            -webkit-user-select: none;
            user-select: none;
        }
    </style>
</head>
<body class="bg-slate-50 text-slate-800 font-sans h-screen flex flex-col no-select">

    <div id="appDashboard" class="flex-1 flex flex-col h-full overflow-hidden">
        <header class="bg-white border-b border-slate-200 px-6 py-3 flex items-center justify-between shadow-sm relative z-40">
            <div class="flex items-center gap-3">
                <div class="bg-sky-600 text-white p-2 rounded-lg">
                    <i class="fa-solid fa-shield-halved text-xl"></i>
                </div>
                <div>
                    <h1 class="font-bold text-slate-800 text-lg leading-none">NeuraFS Storage Explorer</h1>
                    <span class="text-xs text-slate-400">Multi-Agent Neural Parameterization & Resynthesis System</span>
                </div>
            </div>

            <!-- Search Bar -->
            <div class="flex-1 max-w-md mx-6">
                <div class="relative">
                    <i class="fa-solid fa-magnifying-glass absolute left-3 top-3 text-slate-400 text-sm"></i>
                    <input type="text" id="searchInput" oninput="handleSearch()" placeholder="Search files, extension, media..." 
                           class="w-full pl-9 pr-4 py-2 text-sm bg-slate-100 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-sky-500">
                </div>
            </div>

            <!-- Precision Selector & Main Actions -->
            <div class="flex items-center gap-3">

                <!-- Mode Selector Dropdown -->
                <div class="flex items-center gap-1 bg-slate-100 border border-slate-200 rounded-lg p-1">
                    <i class="fa-solid fa-sliders text-sky-600 text-xs ml-2"></i>
                    <select id="precisionModeSelect" class="bg-transparent text-slate-700 text-xs font-bold py-1 px-1 focus:outline-none cursor-pointer">
                        <option value="auto" selected>Auto (Smart Neural Allocation)</option>
                        <option value="archive">Archive Mode (FP32 - Studio Fidelity)</option>
                        <option value="compact">Compact Mode (FP16 - Space Efficient)</option>
                    </select>
                </div>

                <!-- Progress Widget -->
                <div id="taskProgressWidget" class="hidden relative">
                    <div onclick="toggleTaskDropdown()" class="flex items-center gap-3 bg-slate-100 hover:bg-slate-200 border border-slate-200 px-3 py-1.5 rounded-lg cursor-pointer transition">
                        <div class="w-4 h-4 border-2 border-sky-600 border-t-transparent rounded-full animate-spin"></div>
                        <div class="flex flex-col text-left">
                            <div class="flex items-center justify-between gap-2 text-xs font-semibold text-slate-700">
                                <span id="widgetTaskTitle">Parameterizing...</span>
                                <span id="widgetTaskPercent" class="text-sky-600 font-bold">0%</span>
                            </div>
                            <div class="w-24 bg-slate-300 h-1.5 rounded-full overflow-hidden mt-0.5">
                                <div id="widgetProgressBar" class="bg-sky-600 h-full rounded-full transition-all duration-300" style="width: 0%"></div>
                            </div>
                        </div>
                        <i class="fa-solid fa-chevron-down text-xs text-slate-400 ml-1"></i>
                    </div>

                    <div id="taskLogDropdown" class="hidden absolute right-0 mt-2 w-96 bg-slate-900 text-slate-100 border border-slate-700 rounded-xl shadow-2xl p-4 z-50 text-xs font-mono">
                        <div class="flex justify-between items-center border-b border-slate-700 pb-2 mb-2 font-bold text-sky-400">
                            <span class="flex items-center gap-1.5"><i class="fa-solid fa-terminal text-xs"></i> Subband Logs</span>
                            <div class="flex items-center gap-2">
                                <button onclick="cancelAllTasks()" title="Stop all tasks" class="px-2 py-0.5 bg-rose-600/80 hover:bg-rose-600 text-white rounded text-[10px] font-sans font-semibold transition flex items-center gap-1">
                                    <i class="fa-solid fa-ban text-[10px]"></i> Stop All
                                </button>
                                <span id="activeTaskCount" class="bg-sky-900 text-sky-300 px-2 py-0.5 rounded text-[10px]">0 Active</span>
                            </div>
                        </div>
                        <div id="taskListContainer" class="max-h-60 overflow-y-auto space-y-2 text-[11px] leading-relaxed text-slate-300"></div>
                    </div>
                </div>

                <button onclick="openNewFolderModal()" class="px-3 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-medium rounded-lg transition flex items-center gap-1.5">
                    <i class="fa-solid fa-folder-plus text-amber-500"></i> New Folder
                </button>

                <label class="px-3 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-medium rounded-lg transition cursor-pointer flex items-center gap-1.5">
                    <i class="fa-solid fa-folder-tree text-sky-500"></i> Upload Folder
                    <input type="file" id="folderInput" class="hidden" webkitdirectory directory multiple onchange="handleFolderUpload(event)">
                </label>

                <label class="px-3 py-2 bg-sky-600 hover:bg-sky-700 text-white text-xs font-medium rounded-lg transition cursor-pointer flex items-center gap-1.5 shadow-sm">
                    <i class="fa-solid fa-cloud-arrow-up"></i> Upload Files / .hcs
                    <input type="file" id="fileInput" class="hidden" multiple onchange="handleFileUpload(event)">
                </label>
            </div>
        </header>

        <!-- Navigation Toolbar -->
        <div class="bg-slate-100 border-b border-slate-200 px-6 py-2 flex items-center gap-3 text-sm">
            <div class="flex items-center gap-1 bg-white border border-slate-200 rounded-lg p-1">
                <button onclick="navigateHistoryBack()" id="btnBack" class="p-1.5 hover:bg-slate-100 text-slate-600 disabled:opacity-30 rounded"><i class="fa-solid fa-arrow-left"></i></button>
                <button onclick="navigateHistoryForward()" id="btnForward" class="p-1.5 hover:bg-slate-100 text-slate-600 disabled:opacity-30 rounded"><i class="fa-solid fa-arrow-right"></i></button>
                <button onclick="navigateUpLevel()" id="btnUp" class="p-1.5 hover:bg-slate-100 text-slate-600 disabled:opacity-30 rounded"><i class="fa-solid fa-arrow-up"></i></button>
            </div>
            <div class="flex-1 bg-white border border-slate-200 rounded-lg px-3 py-1.5 flex items-center gap-2 text-slate-600 overflow-x-auto">
                <i class="fa-solid fa-folder text-amber-500"></i>
                <span id="breadcrumbPath" class="font-medium">Root</span>
            </div>
        </div>

        <!-- Main Workspace -->
        <div class="flex-1 flex overflow-hidden">
            <aside class="w-64 bg-white border-r border-slate-200 p-4 flex flex-col justify-between">
                <div class="space-y-6">
                    <div>
                        <span class="text-xs font-semibold text-slate-400 uppercase tracking-wider px-2">Quick Access</span>
                        <nav class="mt-2 space-y-1">
                            <button onclick="navigateTo('')" id="navAll" class="w-full flex items-center gap-3 px-3 py-2 text-sm font-medium text-sky-600 bg-sky-50 rounded-lg"><i class="fa-solid fa-house text-sky-500"></i> All Files (Root)</button>
                            <button onclick="navigateTo('media')" id="navMedia" class="w-full flex items-center gap-3 px-3 py-2 text-sm font-medium text-slate-700 rounded-lg hover:bg-slate-100"><i class="fa-solid fa-photo-film text-purple-500"></i> Media Vault</button>
                            <button onclick="navigateTo('documents')" id="navDocs" class="w-full flex items-center gap-3 px-3 py-2 text-sm font-medium text-slate-700 rounded-lg hover:bg-slate-100"><i class="fa-solid fa-file-lines text-blue-500"></i> Documents</button>
                        </nav>
                    </div>
                </div>

                <div class="p-4 bg-slate-50 border border-slate-200 rounded-xl">
                    <div class="flex justify-between items-center text-xs text-slate-500 mb-1">
                        <span>Used Storage Space</span>
                        <span id="quotaText" class="font-bold text-slate-700">0 MB</span>
                    </div>
                </div>
            </aside>

            <main class="flex-1 flex flex-col bg-slate-50 overflow-hidden">
                <div class="flex-1 p-6 overflow-y-auto">
                    <table class="w-full text-left border-collapse">
                        <thead>
                            <tr class="border-b border-slate-200 text-xs font-semibold text-slate-400 uppercase">
                                <th class="pb-3 pl-2">Name</th>
                                <th class="pb-3">Type</th>
                                <th class="pb-3 text-right">Original Size</th>
                                <th class="pb-3 text-right">Container Size (.hcs)</th>
                                <th class="pb-3 text-center">Efficiency</th>
                                <th class="pb-3 text-right pr-2">Date Added</th>
                            </tr>
                        </thead>
                        <tbody id="fileExplorerBody" class="divide-y divide-slate-100 text-sm"></tbody>
                    </table>
                </div>
            </main>
        </div>
    </div>

    <!-- Modals & Context Menu -->
    <div id="contextMenu" class="context-menu">
        <button onclick="handleContextMenuAction('open')"><i class="fa-solid fa-folder-open text-sky-500"></i> Open / Preview / Resynthesize</button>
        <button onclick="handleContextMenuAction('download_raw')"><i class="fa-solid fa-file-arrow-down text-emerald-500"></i> Download Resynthesized File</button>
        <button onclick="handleContextMenuAction('download_compressed')"><i class="fa-solid fa-box-archive text-indigo-500"></i> Download Raw Container (.hcs)</button>
        <div class="border-t border-slate-100 my-1"></div>
        <button onclick="handleContextMenuAction('delete')" class="text-rose-600 hover:bg-rose-50"><i class="fa-solid fa-trash-can text-rose-500"></i> Delete</button>
    </div>

    <div id="loadingModal" class="fixed inset-0 bg-slate-900/60 backdrop-blur-sm hidden z-50 flex items-center justify-center p-4">
        <div class="bg-white rounded-2xl p-6 shadow-2xl flex flex-col items-center gap-4 text-center max-w-sm w-full">
            <div class="w-12 h-12 border-4 border-sky-600 border-t-transparent rounded-full animate-spin"></div>
            <div>
                <h3 class="font-bold text-slate-800 text-lg">Neural Resynthesis</h3>
                <p class="text-xs text-slate-500 mt-1">Merging frequency subbands & synthesizing WAV...</p>
            </div>
        </div>
    </div>

    <div id="editorModal" class="fixed inset-0 bg-slate-900/60 backdrop-blur-sm hidden z-50 flex items-center justify-center p-4">
        <div class="bg-white rounded-2xl max-w-5xl w-full p-6 shadow-2xl flex flex-col h-[85vh]">
            <div class="flex justify-between items-center mb-4">
                <h3 id="editorTitle" class="font-bold text-lg text-slate-800">Monaco Code Editor</h3>
                <button onclick="closeModal('editorModal')" class="text-slate-400 hover:text-slate-600 text-xl"><i class="fa-solid fa-xmark"></i></button>
            </div>
            <div id="monacoContainer" class="flex-1 w-full border border-slate-200 rounded-xl overflow-hidden"></div>
        </div>
    </div>

    <div id="pdfModal" class="fixed inset-0 bg-slate-900/60 backdrop-blur-sm hidden z-50 flex items-center justify-center p-4">
        <div class="bg-white rounded-2xl max-w-5xl w-full p-6 shadow-2xl flex flex-col h-[85vh]">
            <div class="flex justify-between items-center mb-4">
                <h3 id="pdfTitle" class="font-bold text-lg text-slate-800">PDF Viewer</h3>
                <button onclick="closeModal('pdfModal')" class="text-slate-400 hover:text-slate-600 text-xl"><i class="fa-solid fa-xmark"></i></button>
            </div>
            <iframe id="pdfFrame" class="flex-1 w-full border border-slate-200 rounded-xl"></iframe>
        </div>
    </div>

    <div id="mediaModal" class="fixed inset-0 bg-slate-900/60 backdrop-blur-sm hidden z-50 flex items-center justify-center p-4">
        <div class="bg-white rounded-2xl max-w-2xl w-full p-6 shadow-2xl relative">
            <button onclick="closeModal('mediaModal')" class="absolute top-4 right-4 text-slate-400 hover:text-slate-600 text-xl"><i class="fa-solid fa-xmark"></i></button>
            <h3 id="mediaTitle" class="font-bold text-lg text-slate-800 mb-4">Media Player</h3>
            <div id="mediaPlayerContainer" class="w-full flex justify-center bg-black rounded-xl overflow-hidden min-h-[200px]"></div>
        </div>
    </div>

    <div id="binaryModal" class="fixed inset-0 bg-slate-900/60 backdrop-blur-sm hidden z-50 flex items-center justify-center p-4">
        <div class="bg-white rounded-2xl max-w-md w-full p-6 shadow-2xl relative text-center">
            <h3 id="binaryTitle" class="font-bold text-lg text-slate-800 mb-2">Reconstructed Binary Document</h3>
            <p class="text-xs text-slate-500 mb-6">Select your action:</p>
            <div class="flex flex-col gap-3">
                <button id="btnOpenBrowser" class="w-full py-2.5 bg-sky-600 hover:bg-sky-700 text-white text-sm font-medium rounded-xl transition flex items-center justify-center gap-2"><i class="fa-solid fa-arrow-up-right-from-square"></i> Open in Browser</button>
                <button id="btnDownloadRaw" class="w-full py-2.5 bg-slate-100 hover:bg-slate-200 text-slate-700 text-sm font-medium rounded-xl transition flex items-center justify-center gap-2"><i class="fa-solid fa-download"></i> Download Reconstructed File</button>
            </div>
            <button onclick="closeModal('binaryModal')" class="mt-4 text-xs text-slate-400 hover:text-slate-600">Cancel</button>
        </div>
    </div>

    <script>
        let currentPath = '';
        let historyStack = [''];
        let forwardStack = [];
        let fileTreeData = [];
        let selectedItem = null;
        let searchQuery = '';
        let monacoEditor = null;
        let taskPollInterval = null;

        require.config({ paths: { vs: 'https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.38.0/min/vs' } });

        document.addEventListener('DOMContentLoaded', () => {
            setupContextMenuListeners();
            fetchFileTree();
            initBackgroundTasksTracker();
        });

        function formatBytes(bytes) {
            if (!bytes || bytes === 0) return '0 B';
            const k = 1024;
            const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
        }

        async function fetchFileTree() {
            try {
                const response = await fetch('/api/fs/tree');
                const data = await response.json();
                fileTreeData = data.root || [];
                renderExplorer();
                document.getElementById('quotaText').innerText = `${formatBytes(data.used_bytes || 0)}`;
            } catch (error) {
                console.error('Failed to fetch file tree:', error);
            }
        }

        function renderExplorer() {
            const tbody = document.getElementById('fileExplorerBody');
            tbody.innerHTML = '';

            let currentItems = fileTreeData;
            if (currentPath) {
                const pathParts = currentPath.split('/');
                for (const part of pathParts) {
                    const found = currentItems.find(i => i.name === part && i.type === 'folder');
                    if (found && found.children) currentItems = found.children;
                }
            }

            let filteredItems = currentItems.filter(item => !searchQuery || item.name.toLowerCase().includes(searchQuery.toLowerCase()));

            document.getElementById('breadcrumbPath').innerText = currentPath ? `Root / ${currentPath}` : 'Root';
            document.getElementById('btnBack').disabled = historyStack.length <= 1;
            document.getElementById('btnForward').disabled = forwardStack.length === 0;
            document.getElementById('btnUp').disabled = !currentPath;

            filteredItems.forEach(item => {
                const tr = document.createElement('tr');
                tr.className = 'hover:bg-sky-50/50 cursor-pointer transition group';

                let iconClass = 'fa-solid fa-folder text-amber-500 text-base';
                if (item.type === 'file') {
                    if (item.file_category === 'media') iconClass = 'fa-solid fa-file-audio text-purple-500 text-base';
                    else if (item.name.match(/\.(txt|json|js|html|css|py|csv|md|cpp|c|cs|log)$/i)) iconClass = 'fa-solid fa-file-code text-sky-500 text-base';
                    else if (item.name.match(/\.(pdf)$/i)) iconClass = 'fa-solid fa-file-pdf text-rose-500 text-base';
                    else iconClass = 'fa-solid fa-file text-slate-500 text-base';
                }

                tr.innerHTML = `
                    <td class="py-3 pl-2 flex items-center gap-3 font-medium text-slate-700">
                        <i class="${iconClass}"></i>
                        <span>${item.name}</span>
                    </td>
                    <td class="py-3 text-slate-400 text-xs uppercase">${item.type === 'folder' ? 'Folder' : item.file_category}</td>
                    <td class="py-3 text-right text-slate-600 font-mono text-xs">${item.type === 'folder' ? '-' : formatBytes(item.original_size)}</td>
                    <td class="py-3 text-right text-emerald-600 font-mono text-xs font-semibold">${item.type === 'folder' ? '-' : formatBytes(item.compressed_size)}</td>
                    <td class="py-3 text-center">${item.type === 'file' ? `<span class="px-2 py-0.5 text-[10px] font-bold bg-emerald-100 text-emerald-700 rounded-full">${item.compression_ratio}</span>` : '-'}</td>
                    <td class="py-3 text-right text-slate-400 text-xs pr-2">${item.created_at ? new Date(item.created_at).toLocaleDateString() : '-'}</td>
                `;

                tr.onclick = () => item.type === 'folder' ? navigateTo(item.path) : openFilePreview(item);
                tr.oncontextmenu = (e) => { e.preventDefault(); selectedItem = item; showContextMenu(e.clientX, e.clientY); };
                tbody.appendChild(tr);
            });
        }

        function handleSearch() {
            searchQuery = document.getElementById('searchInput').value;
            renderExplorer();
        }

        function navigateTo(path) {
            if (path !== currentPath) {
                historyStack.push(path);
                forwardStack = [];
                currentPath = path;
                renderExplorer();
            }
        }

        function navigateHistoryBack() {
            if (historyStack.length > 1) {
                forwardStack.push(historyStack.pop());
                currentPath = historyStack[historyStack.length - 1];
                renderExplorer();
            }
        }

        function navigateHistoryForward() {
            if (forwardStack.length > 0) {
                currentPath = forwardStack.pop();
                historyStack.push(currentPath);
                renderExplorer();
            }
        }

        function navigateUpLevel() {
            if (currentPath) {
                const parts = currentPath.split('/');
                parts.pop();
                navigateTo(parts.join('/'));
            }
        }

        function showContextMenu(x, y) {
            const menu = document.getElementById('contextMenu');
            menu.style.left = `${x}px`; menu.style.top = `${y}px`; menu.style.display = 'block';
        }

        function setupContextMenuListeners() {
            document.addEventListener('click', () => {
                const menu = document.getElementById('contextMenu');
                if (menu) menu.style.display = 'none';
            });
        }

        async function handleContextMenuAction(action) {
            if (!selectedItem) return;
            const pathParam = encodeURIComponent(selectedItem.path);

            if (action === 'open') {
                if (selectedItem.type === 'folder') navigateTo(selectedItem.path);
                else openFilePreview(selectedItem);
            } else if (action === 'download_raw') {
                window.location.href = `/api/fs/download/raw?path=${pathParam}`;
            } else if (action === 'download_compressed') {
                window.location.href = `/api/fs/download/compressed?path=${pathParam}`;
            } else if (action === 'delete') {
                if (confirm(`Are you sure you want to delete ${selectedItem.name}?`)) {
                    await fetch('/api/fs/item', {
                        method: 'DELETE',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ targetPath: selectedItem.path })
                    });
                    fetchFileTree();
                }
            }
        }

        async function openFilePreview(item) {
            const pathParam = encodeURIComponent(item.path);
            const streamUrl = `/api/fs/stream?path=${pathParam}`;
            const rawDownloadUrl = `/api/fs/download/raw?path=${pathParam}`;

            document.getElementById('loadingModal').classList.remove('hidden');

            try {
                const res = await fetch(streamUrl);
                const blob = await res.blob();
                const blobUrl = URL.createObjectURL(blob);
                document.getElementById('loadingModal').classList.add('hidden');

                if (item.file_category === 'media') {
                    document.getElementById('mediaTitle').innerText = item.name;
                    const container = document.getElementById('mediaPlayerContainer');
                    container.innerHTML = `<audio controls autoplay class="w-full my-8 px-4"><source src="${blobUrl}" type="audio/wav"></audio>`;
                    document.getElementById('mediaModal').classList.remove('hidden');
                } else if (item.name.match(/\.(pdf)$/i)) {
                    document.getElementById('pdfTitle').innerText = item.name;
                    document.getElementById('pdfFrame').src = blobUrl;
                    document.getElementById('pdfModal').classList.remove('hidden');
                } else if (item.name.match(/\.(txt|json|js|html|css|py|csv|md|cpp|c|cs|log)$/i)) {
                    document.getElementById('editorTitle').innerText = item.name;
                    const textContent = await blob.text();
                    document.getElementById('editorModal').classList.remove('hidden');

                    require(['vs/editor/editor.main'], function () {
                        if (monacoEditor) monacoEditor.dispose();
                        monacoEditor = monaco.editor.create(document.getElementById('monacoContainer'), {
                            value: textContent,
                            language: 'plaintext',
                            theme: 'vs-dark',
                            automaticLayout: true
                        });
                    });
                } else {
                    document.getElementById('binaryTitle').innerText = item.name;
                    document.getElementById('btnOpenBrowser').onclick = () => window.open(blobUrl, '_blank');
                    document.getElementById('btnDownloadRaw').onclick = () => window.location.href = rawDownloadUrl;
                    document.getElementById('binaryModal').classList.remove('hidden');
                }
            } catch (err) {
                document.getElementById('loadingModal').classList.add('hidden');
                alert('Resynthesis failed: ' + err.message);
            }
        }

        async function handleFolderUpload(event) {
            const files = event.target.files;
            if (!files.length) return;
            uploadFilesBatch(files, true);
        }

        async function handleFileUpload(event) {
            const files = event.target.files;
            if (!files.length) return;
            uploadFilesBatch(files, false);
        }

        async function uploadFilesBatch(files, isFolder = false) {
            const selectedFolder = currentPath || 'documents';
            const precisionMode = document.getElementById('precisionModeSelect').value;

            if (isFolder && files.length > 1) {
                const taskId = 'task_' + Date.now() + '_' + Math.random().toString(36).substr(2, 5);
                const formData = new FormData();
                formData.append('targetFolder', selectedFolder);
                formData.append('taskId', taskId);
                formData.append('precisionMode', precisionMode);

                for (let i = 0; i < files.length; i++) {
                    formData.append('files', files[i]);
                    formData.append('relativePaths', files[i].webkitRelativePath || files[i].name);
                }

                saveTaskToLocalStorage({
                    id: taskId,
                    fileName: files[0].webkitRelativePath ? files[0].webkitRelativePath.split('/')[0] : 'Folder Bundle',
                    progress: 5,
                    log: `Initiating Folder Bundle (${precisionMode.toUpperCase()})...`,
                    status: 'running'
                });

                fetch('/api/fs/upload-async', {
                    method: 'POST',
                    body: formData
                }).catch(err => console.error(err));

            } else {
                for (const file of files) {
                    const taskId = 'task_' + Date.now() + '_' + Math.random().toString(36).substr(2, 5);
                    const formData = new FormData();
                    formData.append('files', file);
                    formData.append('targetFolder', selectedFolder);
                    formData.append('taskId', taskId);
                    formData.append('precisionMode', precisionMode);

                    saveTaskToLocalStorage({
                        id: taskId,
                        fileName: file.name,
                        progress: 5,
                        log: `Initiating (${precisionMode.toUpperCase()})...`,
                        status: 'running'
                    });

                    fetch('/api/fs/upload-async', {
                        method: 'POST',
                        body: formData
                    }).catch(err => console.error(err));
                }
            }

            initBackgroundTasksTracker();
        }

        function saveTaskToLocalStorage(taskObj) {
            let tasks = JSON.parse(localStorage.getItem('neurafs_active_tasks') || '[]');
            const idx = tasks.findIndex(t => t.id === taskObj.id);
            if (idx >= 0) tasks[idx] = { ...tasks[idx], ...taskObj };
            else tasks.push(taskObj);
            localStorage.setItem('neurafs_active_tasks', JSON.stringify(tasks));
        }

        function getTasksFromLocalStorage() {
            return JSON.parse(localStorage.getItem('neurafs_active_tasks') || '[]');
        }

        function removeTaskFromLocalStorage(taskId) {
            let tasks = JSON.parse(localStorage.getItem('neurafs_active_tasks') || '[]');
            tasks = tasks.filter(t => t.id !== taskId);
            localStorage.setItem('neurafs_active_tasks', JSON.stringify(tasks));
        }

        async function cancelTask(taskId) {
            try {
                await fetch('/api/fs/task-cancel', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ taskId })
                });
                removeTaskFromLocalStorage(taskId);
                pollTasksStatus();
            } catch (err) {
                console.error('Failed to cancel task:', err);
            }
        }

        async function cancelAllTasks() {
            if (!confirm('Are you sure you want to stop all active tasks?')) return;
            try {
                await fetch('/api/fs/task-cancel', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ taskId: 'all' })
                });
                localStorage.removeItem('neurafs_active_tasks');
                pollTasksStatus();
            } catch (err) {
                console.error('Failed to cancel all tasks:', err);
            }
        }

        function initBackgroundTasksTracker() {
            if (taskPollInterval) clearInterval(taskPollInterval);
            pollTasksStatus();
            taskPollInterval = setInterval(pollTasksStatus, 1000);
        }

        async function pollTasksStatus() {
            let localTasks = getTasksFromLocalStorage();
            if (localTasks.length === 0) {
                document.getElementById('taskProgressWidget').classList.add('hidden');
                if (taskPollInterval) clearInterval(taskPollInterval);
                return;
            }

            try {
                const res = await fetch('/api/fs/tasks-status');
                const serverTasks = await res.json();

                let activeCount = 0;
                let overallProgress = 0;
                const taskContainer = document.getElementById('taskListContainer');
                taskContainer.innerHTML = '';

                localTasks.forEach(task => {
                    const serverInfo = serverTasks[task.id];
                    if (serverInfo) {
                        task.progress = serverInfo.progress || task.progress;
                        task.log = serverInfo.log || task.log;
                        task.logsHistory = serverInfo.logsHistory || task.logsHistory || [];
                        task.status = serverInfo.status || task.status;
                        saveTaskToLocalStorage(task);
                    }

                    if (task.status === 'completed' || task.status === 'cancelled') {
                        removeTaskFromLocalStorage(task.id);
                        fetchFileTree();
                        return;
                    }

                    activeCount++;
                    overallProgress += task.progress;

                    const taskEl = document.createElement('div');
                    taskEl.className = 'p-2 border-b border-slate-800 space-y-1';
                    let logsHtml = (task.logsHistory || []).map(l => `<div class="text-[10px] text-sky-300 font-mono truncate">${l}</div>`).join('');

                    taskEl.innerHTML = `
                        <div class="flex justify-between items-center font-bold text-slate-100">
                            <span class="truncate max-w-[160px]">${task.fileName}</span>
                            <div class="flex items-center gap-2">
                                <span class="text-sky-400 font-bold">${task.progress}%</span>
                                <button onclick="cancelTask('${task.id}')" title="Stop Task" class="text-rose-400 hover:text-rose-300 p-0.5 rounded transition">
                                    <i class="fa-solid fa-circle-xmark text-sm"></i>
                                </button>
                            </div>
                        </div>
                        <div class="w-full bg-slate-800 h-1 rounded-full overflow-hidden my-1">
                            <div class="bg-sky-500 h-full rounded-full transition-all duration-300" style="width: ${task.progress}%"></div>
                        </div>
                        <div class="max-h-20 overflow-y-auto space-y-0.5 mt-1 bg-black/40 p-1.5 rounded">
                            ${logsHtml}
                        </div>
                    `;
                    taskContainer.appendChild(taskEl);
                });

                if (activeCount > 0) {
                    const avgProgress = Math.round(overallProgress / activeCount);
                    document.getElementById('taskProgressWidget').classList.remove('hidden');
                    document.getElementById('widgetTaskTitle').innerText = activeCount === 1 ? 'Parameterizing...' : `${activeCount} Tasks...`;
                    document.getElementById('widgetTaskPercent').innerText = `${avgProgress}%`;
                    document.getElementById('widgetProgressBar').style.width = `${avgProgress}%`;
                    document.getElementById('activeTaskCount').innerText = `${activeCount} Active`;
                } else {
                    document.getElementById('taskProgressWidget').classList.add('hidden');
                }
            } catch (err) {
                console.error('Task polling error:', err);
            }
        }

        function toggleTaskDropdown() {
            document.getElementById('taskLogDropdown').classList.toggle('hidden');
        }

        function closeModal(id) {
            document.getElementById(id).classList.add('hidden');
            if (id === 'mediaModal') document.getElementById('mediaPlayerContainer').innerHTML = '';
            else if (id === 'pdfModal') document.getElementById('pdfFrame').src = '';
        }

        function openNewFolderModal() {
            const folderName = prompt('Enter new folder name:');
            if (folderName) {
                const folderPath = currentPath ? `${currentPath}/${folderName}` : folderName;
                fetch('/api/fs/folder', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ folderPath })
                }).then(() => fetchFileTree());
            }
        }
    </script>
</body>
</html>
