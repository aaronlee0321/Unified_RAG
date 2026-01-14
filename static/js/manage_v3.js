// Manage Documents functionality - v3.0 (CLEAN - No Metadata, Robust Icons)
document.addEventListener('DOMContentLoaded', function() {
    // Internal tab navigation
    const tabButtons = document.querySelectorAll('.tab-btn[data-tab]');
    const tabContents = document.querySelectorAll('.tab-content');
    
    tabButtons.forEach(btn => {
        btn.addEventListener('click', function() {
            const targetTab = this.getAttribute('data-tab');
            tabButtons.forEach(b => {
                b.classList.remove('active');
                b.setAttribute('data-state', 'inactive');
                b.setAttribute('aria-selected', 'false');
            });
            this.classList.add('active');
            this.setAttribute('data-state', 'active');
            this.setAttribute('aria-selected', 'true');
            
            tabContents.forEach(content => {
                content.classList.remove('active');
                if (content.id === `tab-${targetTab}`) {
                    content.classList.add('active');
                }
            });
        });
    });
    
    // --- SHARED UI CONSTANTS ---
    const EXTENSION_COLORS = {
        ts: "bg-blue-500/10 text-blue-600",
        tsx: "bg-blue-500/10 text-blue-600",
        js: "bg-yellow-500/10 text-yellow-600",
        jsx: "bg-yellow-500/10 text-yellow-600",
        py: "bg-green-500/10 text-green-600",
        cs: "bg-purple-500/10 text-purple-600",
        cpp: "bg-purple-500/10 text-purple-600",
        json: "bg-orange-500/10 text-orange-600",
        css: "bg-pink-500/10 text-pink-600",
        html: "bg-red-500/10 text-red-600",
        md: "bg-slate-500/10 text-slate-600",
    };

    const getExtensionBadge = (ext) => {
        const colorClass = EXTENSION_COLORS[ext] || "bg-slate-500/10 text-slate-600";
        // Matching the requested style: px-2 py-1 rounded text-xs font-semibold flex-shrink-0
        return `<div class="badge-ext ${colorClass}" style="padding: 4px 8px; border-radius: 4px; font-size: 0.75rem; font-weight: 600; flex-shrink: 0; line-height: 1; min-width: 32px; text-align: center;">${ext}</div>`;
    };

    // --- GDD Elements ---
    const gddFileUpload = document.getElementById('gdd-file-upload');
    const gddBrowseBtn = document.getElementById('gdd-browse-btn');
    const gddQueueSection = document.getElementById('gdd-queue-section');
    const gddQueueList = document.getElementById('gdd-queue-list');
    const gddQueueHeader = document.getElementById('gdd-queue-header');
    const gddDocumentsList = document.getElementById('gdd-documents-list');
    const gddDropZone = document.getElementById('gdd-upload-card');
    const gddStats = document.getElementById('gdd-stats');
    const gddSearch = document.getElementById('gdd-manage-search');
    const gddClearAllBtn = document.getElementById('gdd-clear-all-btn');
    const gddPauseResumeBtn = document.getElementById('gdd-pause-resume-btn');
    
    // --- Code Elements ---
    const codeFileUpload = document.getElementById('code-file-upload');
    const codeBrowseBtn = document.getElementById('code-browse-btn');
    const codeQueueSection = document.getElementById('code-queue-section');
    const codeQueueList = document.getElementById('code-queue-list');
    const codeQueueHeader = document.getElementById('code-queue-header');
    const codeDocumentsList = document.getElementById('code-documents-list');
    const codeDropZone = document.getElementById('code-upload-card');
    const codeStats = document.getElementById('code-stats');
    const codeSearch = document.getElementById('code-manage-search');
    const codeClearAllBtn = document.getElementById('code-clear-all-btn');
    const codePauseResumeBtn = document.getElementById('code-pause-resume-btn');

    // --- State ---
    const state = {
        gdd: { queue: [], documents: [], isPaused: false, currentProcessing: null, searchQuery: "" },
        code: { queue: [], documents: [], isPaused: false, currentProcessing: null, searchQuery: "" },
        aliases: {
            keywords: [],
            lastUpdated: null,
            expandedKeywords: new Set(),
            searchQuery: "",
            selectedLanguage: null, // EN, VN, or null
            newAliasInput: {} // keywordId -> string
        }
    };

    // Load initial data
    loadGDDDocuments();
    loadCodeFiles();
    loadAliases();

    // 1. Core Processing Loop
    async function runProcessingLoop(type) {
        const s = state[type];
        if (s.queue.length === 0 || s.isPaused) return;
        const nextFile = s.queue.find(f => f.status === "queued");
        if (!nextFile || s.currentProcessing) return;
        
        await processFile(type, nextFile);
    }

    // 2. File Processing Pipeline
    async function processFile(type, queuedFile) {
        const s = state[type];
        s.currentProcessing = queuedFile.id;
        updateQueueItem(type, queuedFile.id, { status: "processing", progress: 10 });
        updateUploadUI(type);

        try {
            const formData = new FormData();
            formData.append('file', queuedFile.file);

            const uploadUrl = type === 'gdd' ? '/api/gdd/upload' : '/api/code/upload';
            const statusUrl = type === 'gdd' ? '/api/gdd/upload/status' : '/api/code/upload/status';

            const response = await fetch(uploadUrl, { method: 'POST', body: formData });
            const data = await response.json();

            if (data.status === 'error' || !data.job_id) {
                updateQueueItem(type, queuedFile.id, { status: "error", error: data.message || 'Upload failed' });
                s.currentProcessing = null;
                runProcessingLoop(type);
                return;
            }

            const jobId = data.job_id;
            
            const pollStatus = async () => {
                const statusRes = await fetch(`${statusUrl}?job_id=${encodeURIComponent(jobId)}`);
                const statusData = await statusRes.json();

                if (statusData.status === 'success') {
                    updateQueueItem(type, queuedFile.id, { status: "completed", progress: 100, chunks: statusData.chunks_count || 0 });
                    
                    if (type === 'gdd') await loadGDDDocuments();
                    else await loadCodeFiles();

                    setTimeout(() => {
                        s.queue = s.queue.filter(f => f.id !== queuedFile.id);
                        s.currentProcessing = null;
                        renderQueue(type);
                        updateUploadUI(type);
                        runProcessingLoop(type);
                    }, 1000);
                } else if (statusData.status === 'error') {
                    updateQueueItem(type, queuedFile.id, { status: "error", error: statusData.message });
                    s.currentProcessing = null;
                    runProcessingLoop(type);
                } else {
                    updateQueueItem(type, queuedFile.id, { progress: 50 });
                    setTimeout(pollStatus, 1500);
                }
            };

            pollStatus();
        } catch (error) {
            updateQueueItem(type, queuedFile.id, { status: "error", error: error.message });
            s.currentProcessing = null;
            runProcessingLoop(type);
        }
    }

    function updateQueueItem(type, id, updates) {
        state[type].queue = state[type].queue.map(f => f.id === id ? { ...f, ...updates } : f);
        renderQueue(type);
    }

    // 3. UI Rendering
    function renderQueue(type) {
        const s = state[type];
        const section = type === 'gdd' ? gddQueueSection : codeQueueSection;
        const list = type === 'gdd' ? gddQueueList : codeQueueList;
        const header = type === 'gdd' ? gddQueueHeader : codeQueueHeader;

        if (s.queue.length === 0) {
            section.classList.add('hidden');
            return;
        }
        section.classList.remove('hidden');
        header.textContent = `Upload Queue (${s.queue.length})`;

        list.innerHTML = s.queue.map(item => {
            const isCompleted = item.status === 'completed';
            const iconClass = type === 'code' && item.status === 'queued' ? 'icon-code' : getQueueIcon(item.status);
            return `
                <div class="queue-item ${isCompleted ? 'completed' : ''}" data-id="${item.id}">
                    <i class="${iconClass} ${item.status === 'processing' ? 'animate-spin' : ''}" style="color: ${getQueueIconColor(item.status)}; font-size: 16px;"></i>
                    <div style="flex: 1; min-width: 0;">
                        <div style="font-size: 0.875rem; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
                            ${item.file.name}
                        </div>
                        ${item.status === 'processing' ? `
                            <div class="progress-bar-container">
                                <div class="progress-bar-fill" style="width: ${item.progress}%"></div>
                            </div>
                        ` : ''}
                        ${isCompleted ? `
                            <div style="font-size: 0.75rem; color: #16a34a; margin-top: 2px;">${item.chunks || 0} chunks</div>
                        ` : ''}
                    </div>
                    ${!isCompleted ? `
                        <button class="action-btn cancel-btn" data-id="${item.id}">
                            <i class="icon-x" style="font-size: 14px;"></i>
                        </button>
                    ` : ''}
                </div>
            `;
        }).join('');

        list.querySelectorAll('.cancel-btn').forEach(btn => {
            btn.onclick = () => {
                const id = btn.dataset.id;
                s.queue = s.queue.filter(f => f.id !== id);
                if (s.currentProcessing === id) s.currentProcessing = null;
                renderQueue(type);
                updateUploadUI(type);
                runProcessingLoop(type);
            };
        });
    }

    function getQueueIcon(status) {
        switch (status) {
            case 'processing': return 'icon-loader-2';
            case 'completed': return 'icon-check-circle-2';
            case 'error': return 'icon-alert-circle';
            default: return 'icon-file-text';
        }
    }

    function getQueueIconColor(status) {
        switch (status) {
            case 'processing': return 'var(--primary)';
            case 'completed': return '#16a34a';
            case 'error': return 'var(--status-error)';
            default: return 'var(--muted-foreground)';
        }
    }

    function renderDocuments() {
        const s = state.gdd;
        const filtered = s.documents.filter(doc => 
            (doc.name || "").toLowerCase().includes(s.searchQuery.toLowerCase()) ||
            (doc.displayName || "").toLowerCase().includes(s.searchQuery.toLowerCase())
        );

        gddStats.textContent = `${filtered.length} of ${s.documents.length} documents`;
        gddClearAllBtn.style.display = s.documents.length > 0 ? 'flex' : 'none';

        if (filtered.length === 0) {
            gddDocumentsList.innerHTML = `
                <div class="placeholder-container">
                    <i class="icon-file-text" style="font-size: 48px; opacity: 0.3; margin-bottom: 12px;"></i>
                    <p style="font-size: 0.875rem; color: var(--muted-foreground);">
                        ${s.searchQuery ? "No documents found" : "No GDD documents uploaded yet"}
                    </p>
                </div>
            `;
            return;
        }

        gddDocumentsList.innerHTML = filtered.map(doc => `
            <div class="document-item" style="padding: 16px; border-bottom: 1px solid var(--border); display: flex; align-items: center; justify-content: space-between;">
                <div style="display: flex; align-items: center; gap: 12px; flex: 1; min-width: 0;">
                    <div style="width: 36px; height: 36px; border-radius: 6px; background: #ECFDF5; display: flex; align-items: center; justify-content: center; flex-shrink: 0; border: 1px solid #D1FAE5;">
                        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#16a34a" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-circle-check" style="flex-shrink: 0;"><circle cx="12" cy="12" r="10"></circle><path d="m9 12 2 2 4-4"></path></svg>
                    </div>
                    <div style="flex: 1; min-width: 0;">
                        <div style="font-weight: 600; font-size: 0.875rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: var(--foreground);">
                            ${doc.displayName.replace(/\.pdf$/i, "").replace(/\.txt$/i, "").replace(/\.md$/i, "")}
                        </div>
                        <div style="font-size: 0.75rem; color: var(--muted-foreground); margin-top: 2px;">
                            ${doc.chunks} chunks
                        </div>
                    </div>
                </div>
                <button class="action-btn delete-doc-btn" data-id="${doc.id}" style="color: var(--status-error); padding: 8px; border-radius: 6px; transition: all 0.2s;">
                    <img src="/static/icons/trash.svg" width="16" height="16" style="filter: invert(32%) sepia(85%) saturate(2853%) hue-rotate(345deg) brightness(101%) contrast(89%);">
                </button>
            </div>
        `).join('');

        gddDocumentsList.querySelectorAll('.delete-doc-btn').forEach(btn => {
            btn.onclick = () => deleteGDD(btn.dataset.id);
        });
    }

    function renderCodeFiles() {
        const s = state.code;
        const filtered = s.documents.filter(file => 
            (file.name || "").toLowerCase().includes(s.searchQuery.toLowerCase()) ||
            (file.path || "").toLowerCase().includes(s.searchQuery.toLowerCase())
        );

        codeStats.textContent = `${filtered.length} of ${s.documents.length} files`;
        codeClearAllBtn.style.display = s.documents.length > 0 ? 'flex' : 'none';

        if (filtered.length === 0) {
            codeDocumentsList.innerHTML = `
                <div class="placeholder-container">
                    <i class="icon-code" style="font-size: 48px; opacity: 0.3; margin-bottom: 12px;"></i>
                    <p style="font-size: 0.875rem; color: var(--muted-foreground);">
                        ${s.searchQuery ? "No files found" : "No code files uploaded yet"}
                    </p>
                </div>
            `;
            return;
        }

        codeDocumentsList.innerHTML = filtered.map(file => {
            const ext = (file.name || "").split('.').pop().toLowerCase();
            return `
                <div class="document-item" style="padding: 16px; border-bottom: 1px solid var(--border); display: flex; align-items: center; justify-content: space-between;">
                    <div style="display: flex; align-items: center; gap: 12px; flex: 1; min-width: 0;">
                        <div style="width: 36px; display: flex; align-items: center; justify-content: center; flex-shrink: 0;">
                            ${getExtensionBadge(ext)}
                        </div>
                        <div style="flex: 1; min-width: 0;">
                            <div style="font-weight: 600; font-size: 0.875rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: var(--foreground);">
                                ${file.name}
                            </div>
                            <div style="font-size: 0.75rem; color: var(--muted-foreground); margin-top: 2px;">
                                ${file.chunks} chunks
                            </div>
                        </div>
                    </div>
                    <button class="action-btn delete-code-btn" data-id="${file.id}" data-path="${file.path}" style="color: var(--status-error); padding: 8px; border-radius: 6px; transition: all 0.2s;">
                        <img src="/static/icons/trash.svg" width="16" height="16" style="filter: invert(32%) sepia(85%) saturate(2853%) hue-rotate(345deg) brightness(101%) contrast(89%);">
                    </button>
                </div>
            `;
        }).join('');

        codeDocumentsList.querySelectorAll('.delete-code-btn').forEach(btn => {
            btn.onclick = () => deleteCode(btn.dataset.path);
        });
    }

    function updateUploadUI(type) {
        const s = state[type];
        const title = type === 'gdd' ? document.getElementById('gdd-upload-title') : document.getElementById('code-upload-title');
        const subtitle = type === 'gdd' ? document.getElementById('gdd-upload-subtitle') : document.getElementById('code-upload-subtitle');
        const iconContainer = type === 'gdd' ? document.getElementById('gdd-upload-icon-container') : document.getElementById('code-upload-icon-container');
        const processingIcon = type === 'gdd' ? document.getElementById('gdd-upload-processing-icon') : document.getElementById('code-upload-processing-icon');

        if (s.queue.length === 0) {
            title.textContent = type === 'gdd' ? "Drag and drop your GDD files here" : "Drag and drop your code files here";
            subtitle.textContent = type === 'gdd' ? "Supports PDF, TXT, and Markdown" : "Supports all code formats";
            iconContainer.classList.remove('hidden');
            processingIcon.classList.add('hidden');
        } else {
            const completed = s.queue.filter(f => f.status === 'completed').length;
            const inQueue = s.queue.length - completed;
            
            title.textContent = s.currentProcessing ? "Processing files..." : "Waiting...";
            subtitle.textContent = `${completed} completed • ${inQueue} in queue`;
            iconContainer.classList.add('hidden');
            processingIcon.classList.remove('hidden');
        }
    }

    // 4. Handlers
    function setupSectionHandlers(type) {
        const s = state[type];
        const browseBtn = type === 'gdd' ? gddBrowseBtn : codeBrowseBtn;
        const fileInput = type === 'gdd' ? gddFileUpload : codeFileUpload;
        const dropZone = type === 'gdd' ? gddDropZone : codeDropZone;
        const searchInput = type === 'gdd' ? gddSearch : codeSearch;
        const clearBtn = type === 'gdd' ? gddClearAllBtn : codeClearAllBtn;
        const pauseBtn = type === 'gdd' ? gddPauseResumeBtn : codePauseResumeBtn;

        if (browseBtn) browseBtn.onclick = () => fileInput.click();
        if (fileInput) fileInput.onchange = (e) => {
            if (e.target.files) addFilesToQueue(type, e.target.files);
            e.target.value = '';
        };

        if (pauseBtn) {
            pauseBtn.onclick = () => {
                s.isPaused = !s.isPaused;
                const icon = pauseBtn.querySelector('i');
                const text = pauseBtn.querySelector('span');
                icon.className = s.isPaused ? 'icon-play' : 'icon-pause';
                text.textContent = s.isPaused ? 'Resume' : 'Pause';
                if (!s.isPaused) runProcessingLoop(type);
            };
        }

        if (searchInput) {
            searchInput.oninput = (e) => {
                s.searchQuery = e.target.value;
                if (type === 'gdd') renderDocuments();
                else renderCodeFiles();
            };
        }

        if (clearBtn) {
            clearBtn.onclick = () => {
                const msg = type === 'gdd' ? "Are you sure you want to delete all GDD documents?" : "Are you sure you want to delete all code files?";
                if (confirm(msg)) {
                    if (type === 'gdd') clearAllGDD();
                    else clearAllCode();
                }
            };
        }

        if (dropZone) {
            dropZone.ondragover = (e) => { e.preventDefault(); dropZone.classList.add('drag-active'); };
            dropZone.ondragleave = () => dropZone.classList.remove('drag-active');
            dropZone.ondrop = (e) => {
                e.preventDefault();
                dropZone.classList.remove('drag-active');
                if (e.dataTransfer.files.length > 0) addFilesToQueue(type, e.dataTransfer.files);
            };
        }
    }

    setupSectionHandlers('gdd');
    setupSectionHandlers('code');

    function addFilesToQueue(type, files) {
        const s = state[type];
        const newFiles = Array.from(files).map(file => ({
            id: `queue-${Date.now()}-${Math.random()}`,
            file,
            status: "queued",
            progress: 0
        }));
        s.queue = [...s.queue, ...newFiles];
        renderQueue(type);
        updateUploadUI(type);
        runProcessingLoop(type);
    }

    // 5. Helpers
    async function loadGDDDocuments() {
        try {
            const res = await fetch('/api/gdd/documents');
            const data = await res.json();
            const uniqueDocsMap = new Map();
            (data.documents || []).forEach(doc => {
                const docId = doc.doc_id || doc.id;
                if (!docId || uniqueDocsMap.has(docId)) return;
                
                const rawName = doc.name || doc.file_name || doc.display_name || "Unknown";
                uniqueDocsMap.set(docId, {
                    id: docId,
                    name: rawName,
                    displayName: rawName, // Keep original for regex in render
                    chunks: doc.chunks_count || doc.chunks || 0
                });
            });
            state.gdd.documents = Array.from(uniqueDocsMap.values());
            renderDocuments();
        } catch (error) { console.error("GDD load failed:", error); }
    }

    async function loadCodeFiles() {
        try {
            const res = await fetch('/api/code/files');
            const data = await res.json();
            state.code.documents = (data.files || []).map(file => ({
                id: file.id || file.file_path,
                name: file.file_name || file.name,
                path: file.file_path || file.path,
                chunks: 12
            }));
            renderCodeFiles();
        } catch (error) { console.error("Code load failed:", error); }
    }

    async function deleteGDD(id) {
        if (!confirm('Are you sure you want to delete this document?')) return;
        try {
            await fetch(`/api/manage/delete/gdd`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ doc_id: id })
            });
            await loadGDDDocuments();
        } catch (error) { alert('Error: ' + error.message); }
    }

    async function clearAllGDD() {
        try {
            const res = await fetch('/api/gdd/documents');
            const data = await res.json();
            const promises = (data.documents || []).map(doc => 
                fetch('/api/manage/delete/gdd', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ doc_id: doc.doc_id || doc.id })
                })
            );
            await Promise.all(promises);
            loadGDDDocuments();
        } catch (error) { console.error("Clear GDD failed:", error); }
    }

    async function deleteCode(path) {
        if (!confirm('Are you sure you want to delete this file?')) return;
        try {
            await fetch(`/api/manage/delete/code`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ file_path: path })
            });
            await loadCodeFiles();
        } catch (error) { alert('Error: ' + error.message); }
    }

    async function clearAllCode() {
        try {
            const res = await fetch('/api/code/files');
            const data = await res.json();
            const promises = (data.files || []).map(f => 
                fetch('/api/manage/delete/code', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ file_path: f.file_path })
                })
            );
            await Promise.all(promises);
            loadCodeFiles();
        } catch (error) { console.error("Clear code failed:", error); }
    }

    // --- ALIAS MANAGEMENT LOGIC ---
    const aliasKeywordsList = document.getElementById('alias-keywords-list');
    const aliasSearch = document.getElementById('alias-search');
    const aliasStats = document.getElementById('alias-stats');
    const aliasAddBtn = document.getElementById('alias-add-keyword-btn');
    const addKeywordDialog = document.getElementById('add-keyword-dialog');
    const confirmAddBtn = document.getElementById('confirm-add-keyword');
    const langFilterBtns = document.querySelectorAll('#tab-aliases .badge-btn');

    async function loadAliases() {
        try {
            const res = await fetch('/api/manage/aliases');
            const data = await res.json();
            state.aliases.keywords = data.keywords || [];
            state.aliases.lastUpdated = data.lastUpdated;
            renderAliases();
        } catch (e) { console.error("Load aliases failed", e); }
    }

    async function saveAliases() {
        try {
            const res = await fetch('/api/manage/aliases/save', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ keywords: state.aliases.keywords })
            });
            const data = await res.json();
            state.aliases.lastUpdated = data.lastUpdated;
        } catch (e) { console.error("Save aliases failed", e); }
    }

    function renderAliases() {
        if (!aliasKeywordsList) return;

        const s = state.aliases;
        const filtered = s.keywords.filter(kw => {
            if (s.selectedLanguage && kw.language !== s.selectedLanguage) return false;
            if (s.searchQuery.trim()) {
                const query = s.searchQuery.toLowerCase();
                const kwMatches = kw.name.toLowerCase().includes(query);
                const aliasMatches = kw.aliases.some(a => a.name.toLowerCase().includes(query));
                return kwMatches || aliasMatches;
            }
            return true;
        });

        aliasStats.textContent = `Results: ${filtered.length} of ${s.keywords.length} keywords`;

        if (filtered.length === 0) {
            aliasKeywordsList.innerHTML = `
                <div class="placeholder-container">
                    <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" style="opacity: 0.2; margin-bottom: 12px;"><ellipse cx="12" cy="5" rx="9" ry="3"></ellipse><path d="M3 5V19A9 3 0 0 0 21 19V5"></path><path d="M3 12A9 3 0 0 0 21 12"></path></svg>
                    <p style="font-size: 0.875rem; color: var(--muted-foreground);">
                        ${s.searchQuery ? "No matches found" : "No keywords yet. Create one to get started!"}
                    </p>
                </div>
            `;
            return;
        }

        aliasKeywordsList.innerHTML = filtered.map(kw => {
            const isExpanded = s.expandedKeywords.has(kw.id);
            return `
                <div class="keyword-container" style="border-bottom: 1px solid var(--border); overflow: hidden;">
                    <div class="keyword-row" onclick="toggleAliasRow('${kw.id}')" style="display: flex; align-items: center; justify-content: space-between; padding: 12px; cursor: pointer;">
                        <div style="display: flex; align-items: center; gap: 12px; flex: 1; min-width: 0;">
                            <svg class="chevron ${isExpanded ? 'rotate-90' : ''}" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="transition: transform 0.2s;"><path d="m9 18 6-6-6-6"></path></svg>
                            <span style="font-weight: 500; font-size: 0.875rem;" class="truncate">${kw.name}</span>
                            <span style="font-size: 0.75rem; color: var(--muted-foreground);">(${kw.aliases.length})</span>
                        </div>
                        <div style="display: flex; align-items: center; gap: 8px;">
                            <span class="badge badge-outline">${kw.language}</span>
                            <button class="action-btn" onclick="event.stopPropagation(); deleteKeyword('${kw.id}')" style="color: var(--status-error);"><svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18"></path><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"></path><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"></path></svg></button>
                        </div>
                    </div>
                    ${isExpanded ? `
                        <div class="alias-list animate-in" style="background: rgba(0,0,0,0.02); padding: 8px 12px 12px 40px; border-top: 1px solid var(--border-color)/30;">
                            <div style="display: flex; flex-direction: column; gap: 4px;">
                                ${kw.aliases.map(a => `
                                    <div class="alias-item group" style="display: flex; align-items: center; justify-content: space-between; padding: 6px 8px; border-radius: 4px; font-size: 0.8125rem;">
                                        <span style="color: var(--muted-foreground);">${a.name}</span>
                                        <button class="action-btn" onclick="deleteAlias('${kw.id}', '${a.id}')" style="opacity: 0.4; padding: 2px;"><svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6 6 18"></path><path d="m6 6 12 12"></path></svg></button>
                                    </div>
                                `).join('')}
                            </div>
                            <div style="display: flex; gap: 4px; margin-top: 8px; padding-top: 8px; border-top: 1px solid var(--border);">
                                <input type="text" placeholder="Add new alias..." onkeydown="if(event.key==='Enter') addAlias('${kw.id}', this.value)" style="flex: 1; height: 28px; font-size: 0.75rem; border-radius: 4px; border: 1px solid var(--border); padding: 0 8px;">
                                <button class="btn-primary" onclick="addAlias('${kw.id}', this.previousElementSibling.value)" style="height: 28px; padding: 0 8px; font-size: 0.75rem;"><svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h14"></path><path d="M12 5v14"></path></svg></button>
                            </div>
                        </div>
                    ` : ''}
                </div>
            `;
        }).join('');
    }

    window.toggleAliasRow = (id) => {
        if (state.aliases.expandedKeywords.has(id)) state.aliases.expandedKeywords.delete(id);
        else state.aliases.expandedKeywords.add(id);
        renderAliases();
    };

    window.addAlias = (kwId, name) => {
        if (!name.trim()) return;
        const kw = state.aliases.keywords.find(k => k.id === kwId);
        if (kw.aliases.some(a => a.name.toLowerCase() === name.trim().toLowerCase())) {
            alert("Alias already exists");
            return;
        }
        kw.aliases.push({ id: `alias-${Date.now()}`, name: name.trim(), createdAt: new Date() });
        saveAliases();
        renderAliases();
    };

    window.deleteAlias = async (kwId, aliasId) => {
        const kw = state.aliases.keywords.find(k => k.id === kwId);
        if (!kw) return;
        
        const alias = kw.aliases.find(a => a.id === aliasId);
        if (!alias) return;
        
        if (!confirm(`Delete alias "${alias.name}" for keyword "${kw.name}"?`)) {
            return;
        }
        
        try {
            const response = await fetch('/api/manage/aliases', {
                method: 'DELETE',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    keyword: kw.name,
                    alias: alias.name
                })
            });
            
            const result = await response.json();
            
            if (response.ok && result.success) {
                // Remove from local state
                kw.aliases = kw.aliases.filter(a => a.id !== aliasId);
                renderAliases();
                // Reload from server to ensure sync
                await loadAliases();
            } else {
                alert('Error deleting alias: ' + (result.error || 'Unknown error'));
            }
        } catch (error) {
            alert('Error deleting alias: ' + error.message);
        }
    };

    window.deleteKeyword = async (id) => {
        const kw = state.aliases.keywords.find(k => k.id === id);
        if (!kw) return;
        
        if (!confirm(`Delete keyword "${kw.name}" and all its ${kw.aliases.length} alias(es)?`)) {
            return;
        }
        
        try {
            // Delete all aliases for this keyword
            const deletePromises = kw.aliases.map(alias => 
                fetch('/api/manage/aliases', {
                    method: 'DELETE',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        keyword: kw.name,
                        alias: alias.name
                    })
                })
            );
            
            await Promise.all(deletePromises);
            
            // Remove from local state
            state.aliases.keywords = state.aliases.keywords.filter(k => k.id !== id);
            state.aliases.expandedKeywords.delete(id);
            renderAliases();
            
            // Reload from server to ensure sync
            await loadAliases();
        } catch (error) {
            alert('Error deleting keyword: ' + error.message);
        }
    };

    // Event Handlers for Aliases Tab
    if (aliasSearch) {
        aliasSearch.oninput = (e) => {
            state.aliases.searchQuery = e.target.value;
            renderAliases();
        };
    }

    langFilterBtns.forEach(btn => {
        btn.onclick = () => {
            langFilterBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            const lang = btn.dataset.lang;
            state.aliases.selectedLanguage = lang === 'all' ? null : lang;
            renderAliases();
        };
    });

    if (aliasAddBtn) {
        aliasAddBtn.onclick = () => {
            addKeywordDialog.classList.remove('hidden');
            document.getElementById('new-keyword-name').focus();
        };
    }

    if (addKeywordDialog) {
        addKeywordDialog.querySelector('.dialog-close').onclick = () => addKeywordDialog.classList.add('hidden');
        addKeywordDialog.onclick = (e) => { if (e.target === addKeywordDialog) addKeywordDialog.classList.add('hidden'); };
    }

    const modalLangBtns = document.querySelectorAll('.lang-select-btn');
    modalLangBtns.forEach(btn => {
        btn.onclick = () => {
            modalLangBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
        };
    });

    if (confirmAddBtn) {
        confirmAddBtn.onclick = () => {
            const name = document.getElementById('new-keyword-name').value;
            const lang = document.querySelector('.lang-select-btn.active').dataset.lang;
            if (!name.trim()) return;
            
            if (state.aliases.keywords.some(k => k.name.toLowerCase() === name.trim().toLowerCase())) {
                alert("Keyword already exists");
                return;
            }

            state.aliases.keywords.push({
                id: `keyword-${Date.now()}`,
                name: name.trim(),
                language: lang,
                aliases: [],
                createdAt: new Date()
            });
            
            saveAliases();
            renderAliases();
            addKeywordDialog.classList.add('hidden');
            document.getElementById('new-keyword-name').value = "";
        };
    }
});