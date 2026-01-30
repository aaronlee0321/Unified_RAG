// GDD RAG functionality
document.addEventListener('DOMContentLoaded', function() {
    const chatContainer = document.getElementById('chat-container');
    const queryInput = document.getElementById('query-input');
    const sendBtn = document.getElementById('send-btn');
    const uploadBtn = document.getElementById('upload-btn');
    const fileUpload = document.getElementById('file-upload');
    const uploadStatus = document.getElementById('upload-status');
    const documentsList = document.getElementById('documents-list');
    const documentSearch = document.getElementById('document-search');
    const sidebar = document.getElementById('gdd-sidebar');
    const previewPanel = document.getElementById('preview-panel');
    const closePreviewBtn = document.getElementById('close-preview');
    const dropzone = document.getElementById('gdd-dropzone');
    const selectedDocHint = document.getElementById('selected-doc-hint');
    
    let selectedDocument = null; // Track selected document
    let selectedDocId = null; // Track selected document ID
    let allDocumentsData = null; // Store all documents data for filtering
    const CHAT_STORAGE_KEY = 'gdd_chat_history';
    const GDD_LANGUAGE_KEY = 'gdd_language';
    let isUpdatingFromSelection = false; // Flag to prevent circular updates
    // Response language: 'en' (toggle checked) or 'vn' (toggle unchecked)
    let gddLanguage = (typeof localStorage !== 'undefined' && localStorage.getItem(GDD_LANGUAGE_KEY)) || 'en';
    let sectionDropdown = null; // Section dropdown element
    let documentSections = []; // Cached sections for selected document
    
    // If this page load is a hard refresh, clear any persisted chat history
    try {
        const navEntries = performance.getEntriesByType('navigation');
        const navType = navEntries && navEntries.length > 0 ? navEntries[0].type : null;
        if (navType === 'reload') {
            localStorage.removeItem(CHAT_STORAGE_KEY);
        }
    } catch (e) {
        console.warn('Navigation type detection failed:', e);
    }
    
    // GDD language toggle (EN/VN) – top right (same convention as Keyword Finder: checked = VN, unchecked = EN)
    const gddLanguageToggle = document.getElementById('gdd-language-toggle');
    if (gddLanguageToggle) {
        gddLanguageToggle.checked = gddLanguage === 'vn';
        gddLanguageToggle.addEventListener('change', function() {
            gddLanguage = this.checked ? 'vn' : 'en';
            try { localStorage.setItem(GDD_LANGUAGE_KEY, gddLanguage); } catch (e) {}
        });
    }

    // Load documents on page load
    loadDocuments();
    // Restore chat history
    loadChatHistory();
    
    // Close preview
    if (closePreviewBtn) {
        closePreviewBtn.addEventListener('click', () => {
            previewPanel.classList.remove('open');
        });
    }

    // Drag & Drop
    if (dropzone) {
        dropzone.addEventListener('click', () => fileUpload.click());
        dropzone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropzone.style.borderColor = 'var(--primary)';
            dropzone.style.background = 'var(--muted)';
        });
        dropzone.addEventListener('dragleave', () => {
            dropzone.style.borderColor = 'var(--border)';
            dropzone.style.background = 'transparent';
        });
        dropzone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropzone.style.borderColor = 'var(--border)';
            dropzone.style.background = 'transparent';
            if (e.dataTransfer.files.length) {
                fileUpload.files = e.dataTransfer.files;
                uploadFile();
            }
        });
    }

    // Search functionality
    documentSearch.addEventListener('input', function() {
        filterDocuments(this.value);
    });
    
    // Send query
    sendBtn.addEventListener('click', sendQuery);
    queryInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendQuery();
        }
    });
    
    // Sync input box with @documentname patterns and handle @ section dropdown
    queryInput.addEventListener('input', function() {
        if (!isUpdatingFromSelection) {
            syncSelectionFromInput();
            handleSectionDropdown();
        }
    });
    
    // Handle clicks outside to close dropdown
    document.addEventListener('click', function(e) {
        if (sectionDropdown && !sectionDropdown.contains(e.target) && e.target !== queryInput) {
            hideSectionDropdown();
        }
    });
    
    // Handle keyboard navigation in dropdown
    queryInput.addEventListener('keydown', function(e) {
        if (sectionDropdown && sectionDropdown.style.display !== 'none') {
            const items = sectionDropdown.querySelectorAll('.section-item');
            const currentIndex = Array.from(items).findIndex(item => item.classList.contains('highlighted'));
            
            if (e.key === 'ArrowDown') {
                e.preventDefault();
                const nextIndex = currentIndex < items.length - 1 ? currentIndex + 1 : 0;
                items.forEach(item => item.classList.remove('highlighted'));
                if (items[nextIndex]) {
                    items[nextIndex].classList.add('highlighted');
                    items[nextIndex].scrollIntoView({ block: 'nearest' });
                }
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                const prevIndex = currentIndex > 0 ? currentIndex - 1 : items.length - 1;
                items.forEach(item => item.classList.remove('highlighted'));
                if (items[prevIndex]) {
                    items[prevIndex].classList.add('highlighted');
                    items[prevIndex].scrollIntoView({ block: 'nearest' });
                }
            } else if (e.key === 'Enter' && currentIndex >= 0) {
                e.preventDefault();
                if (items[currentIndex]) {
                    items[currentIndex].click();
                }
            } else if (e.key === 'Escape') {
                hideSectionDropdown();
            }
        }
    });
    
    
    async function parseJsonSafe(response) {
        const raw = await response.text();   // Always read as text first
        let data = null;

        if (raw && raw.trim().length > 0) {
            try {
                data = JSON.parse(raw);
            } catch {
                // Not JSON (e.g., HTML error page) — wrap it
                data = { status: response.ok ? 'success' : 'error', message: raw };
            }
        } else {
            // Empty body — fabricate a small, safe payload
            data = { status: response.ok ? 'success' : 'error', message: response.ok ? 'Uploaded' : 'Empty response' };
        }
        return data;
    }


    // Upload file
    if (uploadBtn) {
        uploadBtn.addEventListener('click', uploadFile);
    }
    
    function sendQuery() {
        const query = queryInput.value.trim();
        if (!query) return;
        
        // Extract query text - keep @section but remove @documentname
        // Format: "@documentname @section query text"
        // We want to send: "@section query text" (document is already selected via selected_doc)
        let queryText = query;
        if (selectedDocument && selectedDocument !== 'All Documents') {
            // Remove the first @documentname pattern (with underscores replacing spaces)
            const docName = selectedDocument.split(' (')[0];
            const cleanDocName = docName.replace(/[()]/g, '').trim().replace(/\s+/g, '_');
            const docPattern = `@${cleanDocName}`;
            if (queryText.startsWith(docPattern)) {
                queryText = queryText.substring(docPattern.length).trim();
            }
        }
        
        // Add user message (show the full input including @patterns)
        addMessage(query, 'user');
        
        // Clear input but preserve @documentname pattern if document is selected
        if (selectedDocument && selectedDocument !== 'All Documents') {
            // Extract document name and set input to just @documentname with space
            const docName = selectedDocument.split(' (')[0]; // Remove (doc_id) part
            // Use underscores for spaces to keep it as one token
            const cleanDocName = docName.replace(/[()]/g, '').trim().replace(/\s+/g, '_');
            queryInput.value = `@${cleanDocName} `; // Add space after @filename
        } else {
            queryInput.value = '';
        }
        
        // Show typing indicator
        const typingIndicator = addTypingIndicator();
        
        // Send to API with selected document (use the text query, selected_doc is already set)
        fetch('/api/gdd/query', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                query: queryText || query, // Use queryText if available, fallback to full query
                selected_doc: selectedDocument,
                language: gddLanguage
            })
        })
        .then(parseJsonSafe)
        .then(data => {
            removeTypingIndicator(typingIndicator);
            if (data.status === 'error') {
                addMessage('Error: ' + (data.response || data.error || 'Query failed'), 'bot');
            } else {
                // Support markdown-like formatting in response
                const response = data.response || 'No response received';
                addMessage(response, 'bot');
            }
        })
        .catch(error => {
            removeTypingIndicator(typingIndicator);
            addMessage('Error: ' + error.message, 'bot');
        });
    }
    
    
    function uploadFile() {
        const file = fileUpload.files[0];
        if (!file) {
            alert('Please select a file');
            return;
        }

        uploadStatus.style.display = 'block';
        uploadStatus.style.color = '#0b5ed7'; // neutral while in progress
        uploadStatus.textContent = 'Uploading file…';

        const formData = new FormData();
        formData.append('file', file);

        fetch('/api/gdd/upload', { method: 'POST', body: formData })
            .then(parseJsonSafe)
            .then(data => {
            if (data.status === 'error') {
                uploadStatus.textContent = 'Error: ' + (data.message || 'Upload failed');
                uploadStatus.style.color = '#d32f2f';
                return;
            }

            if (data.status !== 'accepted' || !data.job_id) {
                uploadStatus.textContent = 'Unexpected response; upload not started.';
                uploadStatus.style.color = '#d32f2f';
                return;
            }

            const jobId = data.job_id;
            uploadStatus.textContent = data.step || 'Uploading file…';

            // Poll status every 1 second
            const interval = setInterval(() => {
                fetch(`/api/gdd/upload/status?job_id=${encodeURIComponent(jobId)}`)
                    .then(parseJsonSafe)
                    .then(statusData => {
                        if (!statusData || !statusData.status) return;

                        // Update the one-liner
                        const stepText = statusData.step || 'Working…';
                        uploadStatus.textContent = stepText;

                        if (statusData.status === 'success') {
                            uploadStatus.style.color = '#2e7d32';
                            uploadStatus.textContent = statusData.message || 'Upload complete';
                            clearInterval(interval);
                            fileUpload.value = '';
                            // Refresh document list
                        loadDocuments();
                        } else if (statusData.status === 'error') {
                            uploadStatus.style.color = '#d32f2f';
                            uploadStatus.textContent = 'Error: ' + (statusData.message || 'Upload failed');
                            clearInterval(interval);
                        } else {
                            // status === 'running' → continue polling
                        }
                })
            .catch(err => {
                // Keep polling; transient network errors can happen
                console.warn('Status poll error:', err);
            });
            }, 1000);
        })
        .catch(error => {
            uploadStatus.textContent = 'Error: ' + error.message;
            uploadStatus.style.color = '#d32f2f';
        });
    }

    
    function loadDocuments() {
        fetch('/api/gdd/documents')
            .then(parseJsonSafe)
            .then(data => {
                // Store all documents data for filtering
                allDocumentsData = data;
                
                // Update document count
                const docCount = document.getElementById('doc-count');
                if (docCount && data.documents) {
                    docCount.textContent = `(${data.documents.length})`;
                }
                
                // Render documents (will apply current search filter)
                renderDocuments(data);
            })
            .catch(error => {
                console.error('Error loading documents:', error);
                documentsList.innerHTML = '<p style="font-size:0.85rem;color:#d32f2f;">Error loading documents.</p>';
            });
    }
    
    function renderDocuments(data) {
        documentsList.innerHTML = '';
        
        if (!data.documents || data.documents.length === 0) {
            documentsList.innerHTML = '<p style="font-size:0.85rem;color:#666;">No documents indexed yet. Upload a document to get started.</p>';
            return;
        }
        
        // Remove duplicates based on doc_id (keep first occurrence)
        const uniqueDocs = [];
        const seenDocIds = new Set();
        data.documents.forEach(doc => {
            const docId = doc.doc_id;
            if (docId && !seenDocIds.has(docId)) {
                seenDocIds.add(docId);
                uniqueDocs.push(doc);
            }
        });
        
        // Get current search term
        const searchTerm = documentSearch.value.toLowerCase().trim();
        
        // Filter documents based on search term
        const filteredDocs = uniqueDocs.filter(doc => {
            if (!searchTerm) return true;
            const displayName = (doc.name || doc.doc_id).toLowerCase();
            const docId = doc.doc_id.toLowerCase();
            return displayName.includes(searchTerm) || docId.includes(searchTerm);
        });
        
        if (filteredDocs.length === 0 && searchTerm) {
            documentsList.innerHTML = '<p style="font-size:0.85rem;color:#666;">No documents match your search.</p>';
            return;
        }
        
        // Sort documents: selected document first, then unselected documents
        filteredDocs.sort((a, b) => {
            const aOptionValue = data.options ? 
                data.options.find(opt => opt.includes(a.name || a.doc_id) || opt.includes(a.doc_id)) : 
                `${a.name || a.doc_id} (${a.doc_id})`;
            const bOptionValue = data.options ? 
                data.options.find(opt => opt.includes(b.name || b.doc_id) || opt.includes(b.doc_id)) : 
                `${b.name || b.doc_id} (${b.doc_id})`;
            
            const aSelected = selectedDocument === aOptionValue;
            const bSelected = selectedDocument === bOptionValue;
            
            if (aSelected && !bSelected) return -1; // a comes first
            if (!aSelected && bSelected) return 1;  // b comes first
            return 0; // Keep original order for documents with same selection status
        });
        
        // Create "All Documents" option (always show if no search or matches, and at top if selected)
        const showAllDocs = !searchTerm || 'all documents'.includes(searchTerm);
        const allDocsSelected = !selectedDocument || selectedDocument === 'All Documents';
        
        if (showAllDocs) {
            // If "All Documents" is selected, show it first; otherwise show it after selected document
            const allDocsItem = document.createElement('div');
            allDocsItem.className = 'document-item';
            if (allDocsSelected) {
                allDocsItem.classList.add('selected');
            }
            allDocsItem.innerHTML = '<span class="name">All Documents</span>';
            allDocsItem.dataset.docValue = 'All Documents';
            allDocsItem.addEventListener('click', function() {
                selectDocument('All Documents', allDocsItem);
            });
            
            // Insert at top if selected, otherwise append
            if (allDocsSelected && filteredDocs.length > 0 && selectedDocument && selectedDocument !== 'All Documents') {
                // Selected document will be first, so insert All Documents after first group
                // We'll handle this after creating groups
            } else {
                documentsList.appendChild(allDocsItem);
            }
        }
        
        // Group documents by derived category for nicer headings
        const groups = {};
        const seenInGroups = new Set(); // Track doc_ids already added to groups
        
        filteredDocs.forEach(doc => {
            // Skip if we've already processed this doc_id
            if (seenInGroups.has(doc.doc_id)) {
                return;
            }
            seenInGroups.add(doc.doc_id);
            
            const rawName = doc.name || doc.doc_id || 'Unknown';
            const info = parseDocumentName(rawName);
            const groupKey = info.groupLabel || '[Other]';
            
            if (!groups[groupKey]) {
                groups[groupKey] = [];
            }
            groups[groupKey].push({
                doc,
                displayName: info.displayTitle,
                rawName,
            });
        });
        
        // Sort group keys alphabetically
        const sortedGroupKeys = Object.keys(groups).sort((a, b) => a.localeCompare(b));
        
        sortedGroupKeys.forEach(groupKey => {
            const groupWrapper = document.createElement('div');
            groupWrapper.className = 'document-group';
            
            const docsInGroup = groups[groupKey];
            
            const heading = document.createElement('div');
            heading.className = 'document-group-title';
            heading.innerHTML = `
                <img src="/static/icons/chevron-down.svg" class="chevron">
                <span>${groupKey}</span>
                <span class="group-count">(${docsInGroup.length})</span>
            `;
            
            // Handle collapsing
            heading.addEventListener('click', function() {
                groupWrapper.classList.toggle('collapsed');
            });
            
            groupWrapper.appendChild(heading);
            
            const docList = document.createElement('ul');
            docList.className = 'document-list';
            
            // Sort documents within group by display title
            groups[groupKey].sort((a, b) => a.displayName.localeCompare(b.displayName));
            
            groups[groupKey].forEach(entry => {
                const { doc, displayName, rawName } = entry;
                
                const docItem = document.createElement('li');
                docItem.className = 'document-item';
                
                let optionValue = null;
                if (data.options) {
                    optionValue = data.options.find(opt => opt.includes(`(${doc.doc_id})`)) || `${rawName} (${doc.doc_id})`;
                } else {
                    optionValue = `${rawName} (${doc.doc_id})`;
                }
                
                if (selectedDocument === optionValue) {
                    docItem.classList.add('selected');
                }
                
                const isPdf = rawName.toLowerCase().endsWith('.pdf');
                const isMd = rawName.toLowerCase().endsWith('.md') || rawName.toLowerCase().endsWith('.txt');
                const iconSrc = isPdf ? '/static/icons/file-pdf.svg' : (isMd ? '/static/icons/file-md.svg' : '/static/icons/file.svg');
                const iconColor = isPdf ? '#EF4444' : (isMd ? '#3B82F6' : '#6B7280');

                docItem.innerHTML = `
                    <img src="${iconSrc}" class="file-icon" width="16" height="16" style="filter: drop-shadow(0 0 0 ${iconColor})">
                    <div class="content-wrapper">
                        <span class="name">${displayName}</span>
                        <span class="meta-text">${(doc.chunks_count || 0)} chunks</span>
                    </div>
                    <div class="actions">
                        <button class="action-btn preview-trigger" title="Preview">
                            <img src="/static/icons/eye.svg" width="14" height="14">
                        </button>
                        <button class="action-btn delete-trigger" title="Delete">
                            <img src="/static/icons/close.svg" width="14" height="14">
                        </button>
                    </div>
                `;
                
                docItem.dataset.docValue = optionValue;
                docItem.dataset.docId = doc.doc_id;
                
                docItem.addEventListener('click', (e) => {
                    if (e.target.closest('.preview-trigger')) {
                        openPreview(doc);
                        return;
                    }
                    if (e.target.closest('.delete-trigger')) {
                        e.preventDefault();
                        e.stopPropagation();
                        if (confirm('Delete this document?')) {
                            fetch('/api/manage/delete/gdd', {
                                method: 'POST',
                                headers: {'Content-Type': 'application/json'},
                                body: JSON.stringify({ doc_id: doc.doc_id })
                            })
                            .then(response => response.json())
                            .then(data => {
                                if (data.error) {
                                    alert('Error deleting document: ' + data.error);
                                } else {
                                    loadDocuments();
                                }
                            })
                            .catch(error => {
                                console.error('Delete failed:', error);
                                alert('Error deleting document: ' + error.message);
                            });
                        }
                        return;
                    }
                    selectDocument(optionValue, docItem);
                });
                
                docList.appendChild(docItem);
            });
            
            groupWrapper.appendChild(docList);
            documentsList.appendChild(groupWrapper);
        });
        
        // After rendering, update selection UI to ensure consistency
        updateDocumentSelectionUI();
    }
    
    function filterDocuments(searchTerm) {
        // Use cached data if available, otherwise reload
        if (allDocumentsData) {
            renderDocuments(allDocumentsData);
        } else {
            loadDocuments();
        }
    }
    
    function selectDocument(docValue, element) {
        // Ensure only one document can be selected at a time
        // First, clear any previous selection
        const previousSelected = selectedDocument;
        selectedDocument = null;
        selectedDocId = null;
        
        // Remove selected class from all items
        document.querySelectorAll('.document-item').forEach(item => {
            item.classList.remove('selected');
        });
        
        // Update selected document (only one can be selected)
        selectedDocument = docValue === 'All Documents' ? null : docValue;
        
        // Add selected class to clicked item (only this one)
        if (element) {
            element.classList.add('selected');
        }
        
        // Extract doc_id from selected document
        if (selectedDocument && selectedDocument !== 'All Documents') {
            // Use stored doc_id if available (most reliable)
            if (element && element.dataset.docId) {
                selectedDocId = element.dataset.docId;
            } else {
                // Fallback: try to extract from optionValue format: "filename (doc_id) - X chunks"
                // Match the LAST parentheses before " - " to handle doc_ids with parentheses
                const match = selectedDocument.match(/\(([^)]+)\)\s*-\s*\d+/);
                if (match) {
                    selectedDocId = match[1];
                } else {
                    // Try to find doc_id from allDocumentsData
                    if (allDocumentsData && allDocumentsData.documents) {
                        const doc = allDocumentsData.documents.find(d => {
                            const opt = allDocumentsData.options ? 
                                allDocumentsData.options.find(o => o.includes(d.name || d.doc_id) || o.includes(d.doc_id)) : 
                                `${d.name || d.doc_id} (${d.doc_id})`;
                            return opt === selectedDocument;
                        });
                        if (doc) {
                            selectedDocId = doc.doc_id;
                        }
                    }
                }
            }
            
            // Load sections for this document
            if (selectedDocId) {
                loadDocumentSections(selectedDocId);
            }
        } else {
            selectedDocId = null;
            documentSections = [];
            hideSectionDropdown();
        }
        
        // Re-render documents to move selected document to top
        if (allDocumentsData) {
            renderDocuments(allDocumentsData);
        }
        
        // Update input box with @documentname pattern
        syncInputFromSelection();
    }
    
    function syncInputFromSelection() {
        if (!allDocumentsData) return;
        
        isUpdatingFromSelection = true;
        const currentValue = queryInput.value;
        
        // Remove ALL existing @patterns from the input (handles names with spaces)
        // Match @followed by non-whitespace characters OR @followed by text until the next @ or end
        let queryText = currentValue.replace(/@[^\s@]+/g, '').trim();
        // Clean up any extra spaces
        queryText = queryText.replace(/\s+/g, ' ').trim();
        
        if (selectedDocument && selectedDocument !== 'All Documents') {
            const docName = selectedDocument.split(' (')[0];
            // Replace spaces with underscores for the @mention to keep it as one token
            const cleanDocName = docName.replace(/[()]/g, '').trim().replace(/\s+/g, '_');
            queryInput.value = `@${cleanDocName} ${queryText}`.trim();
            if (selectedDocHint) selectedDocHint.textContent = `Targeting: ${docName}`;
        } else {
            queryInput.value = queryText;
            if (selectedDocHint) selectedDocHint.textContent = '';
        }
        
        isUpdatingFromSelection = false;
    }

    function openPreview(doc) {
        if (!previewPanel) return;
        
        const filename = document.getElementById('preview-filename');
        const chunks = document.getElementById('meta-chunks');
        const content = document.getElementById('preview-content');
        
        filename.textContent = doc.name || doc.doc_id;
        chunks.textContent = doc.chunks_count || '0';
        content.innerHTML = '<p style="opacity: 0.5;">Loading preview content...</p>';
        
        previewPanel.classList.add('open');
        
        // Fetch real sections as preview content
        fetch(`/api/gdd/sections?doc_id=${encodeURIComponent(doc.doc_id)}`)
            .then(r => r.json())
            .then(data => {
                if (data.sections && data.sections.length > 0) {
                    content.innerHTML = data.sections.map(s => 
                        `<div style="margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid var(--border);">
                            <div style="font-weight: 600; margin-bottom: 4px;">${s.section_name || 'Section'}</div>
                            <div style="opacity: 0.8; font-size: 0.7rem;">Path: ${s.section_path || '/'}</div>
                        </div>`
                    ).join('');
                } else {
                    content.textContent = 'No preview content available for this document.';
                }
            });
    }
    
    function syncSelectionFromInput() {
        if (!allDocumentsData) return;
        
        const inputValue = queryInput.value;
        
        // Extract @documentname pattern from input
        // Match @ followed by text until space, @, or end of string
        // This handles doc_ids with parentheses like @Asset_UI_Tank_War_Tank_Selection_Screen_Design_(Cơ_chế_chọn_tank)
        const atPattern = inputValue.match(/@([^\s@]+)/);
        if (!atPattern) {
            // No @pattern found, deselect if something was selected
            if (selectedDocument && selectedDocument !== 'All Documents') {
                selectedDocument = null;
                selectedDocId = null;
                documentSections = [];
                hideSectionDropdown();
                updateDocumentSelectionUI();
            }
            return;
        }
        
        const docNameFromInput = atPattern[1];
        
        // Early exit: If we already have this document selected and it matches the input, don't re-process
        if (selectedDocument) {
            const currentDocName = selectedDocument.split(' (')[0];
            const normalizedCurrent = currentDocName.toLowerCase().replace(/[()[\]_,-\s]/g, '');
            const normalizedInput = docNameFromInput.toLowerCase().replace(/[()[\]_,-\s]/g, '');
            // If current selection matches input, don't re-process
            if (normalizedCurrent === normalizedInput || 
                normalizedCurrent.includes(normalizedInput) ||
                normalizedInput.includes(normalizedCurrent)) {
                return; // Already selected and matches - no need to re-process
            }
        }
        
        // Find matching document
        let matchedDoc = null;
        let matchedOptionValue = null;
        
        // Normalize input for matching (remove special chars, lowercase)
        const normalizeForMatch = (text) => {
            if (!text) return '';
            return text.toLowerCase()
                .replace(/[()[\]_,-]/g, '')
                .replace(/\s+/g, '');
        };
        
        const normalizedInput = normalizeForMatch(docNameFromInput);
        
        // Check all documents - use for...of with break to stop after first match
        // Priority: Exact matches first, then partial matches
        for (const doc of allDocumentsData.documents) {
            const rawName = doc.name || doc.doc_id || 'Unknown';
            const displayName = parseDocumentName(rawName).displayTitle;
            const optionValue = allDocumentsData.options ? 
                allDocumentsData.options.find(opt => opt.includes(rawName) || opt.includes(doc.doc_id)) : 
                `${rawName} (${doc.doc_id})`;
            
            // Normalize doc_id and names for comparison
            const normalizedDocId = normalizeForMatch(doc.doc_id);
            const normalizedRawName = normalizeForMatch(rawName);
            const normalizedDisplayName = normalizeForMatch(displayName);
            
            // Try to match by EXACT matches first (more specific, less likely to match multiple)
            if (normalizedDocId === normalizedInput ||
                normalizedDisplayName === normalizedInput ||
                normalizedRawName === normalizedInput) {
                matchedDoc = doc;
                matchedOptionValue = optionValue;
                break; // Stop after first exact match
            }
        }
        
        // If no exact match found, try partial matches (but only if we don't already have a selection)
        if (!matchedDoc && !selectedDocument) {
            for (const doc of allDocumentsData.documents) {
                const rawName = doc.name || doc.doc_id || 'Unknown';
                const optionValue = allDocumentsData.options ? 
                    allDocumentsData.options.find(opt => opt.includes(rawName) || opt.includes(doc.doc_id)) : 
                    `${rawName} (${doc.doc_id})`;
                
                const normalizedDocId = normalizeForMatch(doc.doc_id);
                const normalizedRawName = normalizeForMatch(rawName);
                
                // Partial match (less specific - only use if no exact match)
                if (normalizedDocId.includes(normalizedInput) ||
                    normalizedInput.includes(normalizedDocId) ||
                    normalizedRawName.includes(normalizedInput)) {
                    matchedDoc = doc;
                    matchedOptionValue = optionValue;
                    break; // Stop after first partial match
                }
            }
        }
        
        // Update selectedDocument if match found
        // IMPORTANT: Only allow one document to be selected at a time
        if (matchedOptionValue && selectedDocument !== matchedOptionValue) {
            // Clear previous selection first
            const previousSelected = selectedDocument;
            selectedDocument = null;
            selectedDocId = null;
            
            // Set new selection (only one document)
            selectedDocument = matchedOptionValue;
            // Use the actual doc_id from the matched document (most reliable)
            selectedDocId = matchedDoc ? matchedDoc.doc_id : null;
            
            // Fallback: try to extract from optionValue if doc_id not available
            if (!selectedDocId) {
                // Match the LAST parentheses before " - " to handle doc_ids with parentheses
                const match = matchedOptionValue.match(/\(([^)]+)\)\s*-\s*\d+/);
                selectedDocId = match ? match[1] : null;
            }
            
            if (selectedDocId) {
                loadDocumentSections(selectedDocId);
            }
            // Only update UI, don't re-render all documents (that causes the issue)
            // This ensures only one document is visually selected
            updateDocumentSelectionUI();
        } else if (!matchedOptionValue && selectedDocument) {
            // No match found, deselect (ensure only one selection state)
            selectedDocument = null;
            selectedDocId = null;
            documentSections = [];
            hideSectionDropdown();
            updateDocumentSelectionUI();
        }
    }
    
    function updateDocumentSelectionUI() {
        // Ensure only one document can be selected at a time
        // First, remove selected class from ALL items
        const docItems = documentsList.querySelectorAll('.document-item');
        docItems.forEach(item => {
            item.classList.remove('selected');
        });
        
        // Then, add selected class to ONLY the matching item
        if (selectedDocument) {
            docItems.forEach(item => {
                const docValue = item.dataset.docValue || item.title;
                if (selectedDocument === docValue) {
                    item.classList.add('selected');
                }
            });
        } else {
            // No document selected - select "All Documents" if it exists
            docItems.forEach(item => {
                const docValue = item.dataset.docValue || item.title;
                if (docValue === 'All Documents') {
                    item.classList.add('selected');
                }
            });
        }
    }
    
    function addMessage(text, type, fromHistory) {
        // Hide welcome message on first activity
        const welcome = document.getElementById('gdd-welcome-message');
        if (welcome) welcome.style.display = 'none';

        const wrapper = document.createElement('div');
        wrapper.className = `message-wrapper ${type}`;
        
        const avatar = document.createElement('div');
        avatar.className = 'avatar';
        const iconPath = type === 'bot' ? '/static/icons/bot.svg' : '/static/icons/user.svg';
        avatar.innerHTML = `<img src="${iconPath}" width="18" height="18" style="${type === 'bot' ? 'filter: brightness(0) invert(1)' : ''}">`;
        
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${type}-message`;
        
        // Format text with code block support
        const formattedText = formatMessage(text);
        messageDiv.innerHTML = formattedText;
        
        wrapper.appendChild(avatar);
        wrapper.appendChild(messageDiv);
        
        chatContainer.appendChild(wrapper);
        chatContainer.scrollTop = chatContainer.scrollHeight;

        // Persist to localStorage unless loading from history
        if (!fromHistory) {
            saveMessageToHistory(text, type);
        }
    }
    
    function formatMessage(text) {
        if (!text) return '';
        
        // Check if text contains HTML elements (iframe, embed, etc.) - don't escape if it does
        if (text.includes('<iframe') || text.includes('<embed') || text.includes('<object')) {
            // Contains HTML embeds - return as-is to allow rendering
            return text;
        }
        
        // Escape HTML first
        let escaped = text
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
        
        // Handle code blocks (```language\ncode\n``` or ```\ncode\n```)
        // Match with or without language specifier, with or without leading newline
        escaped = escaped.replace(/```(\w+)?\n?([\s\S]*?)```/g, function(match, lang, code) {
            // Preserve whitespace in code blocks - unescape for code content
            const codeContent = code
                .replace(/&amp;/g, '&')
                .replace(/&lt;/g, '<')
                .replace(/&gt;/g, '>');
            return `<pre><code class="code-block">${codeContent}</code></pre>`;
        });
        
        // Handle inline code (`code`) - but not inside code blocks
        // Split by code blocks first, then process each part
        const parts = escaped.split(/(<pre><code class="code-block">[\s\S]*?<\/code><\/pre>)/);
        for (let i = 0; i < parts.length; i++) {
            // Skip code blocks themselves
            if (parts[i].includes('<pre><code class="code-block">')) {
                continue;
            }
            // Process inline code in regular text
            parts[i] = parts[i].replace(/`([^`\n]+)`/g, '<code class="inline-code">$1</code>');
        }
        escaped = parts.join('');
        
        // Handle bold (**text**)
        escaped = escaped.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
        
        // Skip italic formatting for now to avoid conflicts with bold
        
        // Convert newlines to <br> (but not inside code blocks)
        const parts2 = escaped.split(/(<pre><code class="code-block">[\s\S]*?<\/code><\/pre>)/);
        for (let i = 0; i < parts2.length; i++) {
            if (parts2[i].includes('<pre><code class="code-block">')) {
                continue;
            }
            parts2[i] = parts2[i].replace(/\n/g, '<br>');
        }
        escaped = parts2.join('');
        
        return escaped;
    }

    function saveMessageToHistory(text, type) {
        try {
            const existing = JSON.parse(localStorage.getItem(CHAT_STORAGE_KEY) || '[]');
            existing.push({
                type,
                text,
                ts: Date.now()
            });
            if (existing.length > 200) {
                existing.splice(0, existing.length - 200);
            }
            localStorage.setItem(CHAT_STORAGE_KEY, JSON.stringify(existing));
        } catch (e) {
            console.error('Failed to save GDD chat history:', e);
        }
    }

    function loadChatHistory() {
        try {
            const raw = localStorage.getItem(CHAT_STORAGE_KEY);
            if (!raw) {
                return; // No history; keep default welcome message
            }
            const history = JSON.parse(raw);
            if (!Array.isArray(history) || history.length === 0) {
                return;
            }
            // Clear existing messages (including welcome)
            chatContainer.innerHTML = '';
            history.forEach(msg => {
                if (msg && typeof msg.text === 'string' && msg.type) {
                    addMessage(msg.text, msg.type, true);
                }
            });
        } catch (e) {
            console.error('Failed to load GDD chat history:', e);
        }
    }

    // Clear chat button
    const clearChatBtn = document.getElementById('clear-chat-btn');
    if (clearChatBtn) {
        clearChatBtn.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            try {
                localStorage.removeItem(CHAT_STORAGE_KEY);
            } catch (err) {
                console.error('Failed to clear GDD chat history:', err);
            }
            // Clear chat container and restore welcome message
            chatContainer.innerHTML = '';
            const welcome = document.createElement('div');
            welcome.className = 'message bot-message';
            welcome.id = 'gdd-welcome-message';
            welcome.innerHTML = `
                <div style="display: flex; flex-direction: column; align-items: center; text-align: center; padding: 40px 0;">
                    <div class="icon-box" style="width: 48px; height: 48px; background: #EEF2FF; border-radius: 50%; display: flex; align-items: center; justify-content: center; margin-bottom: 16px;">
                        <img src="/static/icons/file.svg" width="24" height="24" style="filter: invert(26%) sepia(89%) saturate(1583%) hue-rotate(217deg) brightness(96%) contrast(93%);">
                    </div>
                    <h3 style="margin-bottom: 8px;">GDD RAG Assistant</h3>
                    <p style="color: var(--text-muted); max-width: 400px;">Ask questions about your documents. Use <span style="color: var(--primary); font-family: var(--font-mono);">@document</span> to target specific files.</p>
                </div>
            `;
            chatContainer.appendChild(welcome);
        });
    }

    function parseDocumentName(rawName) {
        // Remove extension and normalize
        let base = rawName.replace(/\.[^/.]+$/, '');
        // Replace underscores with spaces for easier pattern matching
        base = base.replace(/_/g, ' ');
        
        // Define the specific group patterns to match
        const groupPatterns = [
            { pattern: /^\[Asset,\s*UI\]\s*\[Tank\s+War\]\s*(.+)$/i, label: '[Asset, UI] [Tank War]' },
            { pattern: /^\[Character\s+Module\]\s*\[Tank\s+War\]\s*(.+)$/i, label: '[Character Module] [Tank War]' },
            { pattern: /^\[Combat\s+Module\]\s*\[Tank\s+War\]\s*(.+)$/i, label: '[Combat Module] [Tank War]' },
            { pattern: /^\[Game\s+Mode\s+Module\]\s*\[Tank\s+War\]\s*(.+)$/i, label: '[Game Mode Module] [Tank War]' },
            { pattern: /^\[Monetization\s+Module\]\s*\[Tank\s+War\]\s*(.+)$/i, label: '[Monetization Module] [Tank War]' },
            { pattern: /^\[Multiplayer\s+Module\]\s*\[Tank\s+War\]\s*(.+)$/i, label: '[Multiplayer Module] [Tank War]' },
            { pattern: /^\[Progression\s+Module\]\s*\[Tank\s+War\]\s*(.+)$/i, label: '[Progression Module] [Tank War]' },
            { pattern: /^\[Progression\s+Module\]\s*\[Tank\s+Wars\]\s*(.+)$/i, label: '[Progression Module] [Tank Wars]' },
            { pattern: /^\[World\]\s*\[Tank\s+War\]\s*(.+)$/i, label: '[World] [Tank War]' },
        ];
        
        // Try to match against each pattern
        for (const { pattern, label } of groupPatterns) {
            const match = base.match(pattern);
            if (match) {
                const displayTitle = match[1].trim();
                return { 
                    groupLabel: label, 
                    displayTitle: displayTitle || base // Fallback to full name if empty
                };
            }
        }
        
        // Also try matching with underscores (in case the name uses underscores)
        const baseWithUnderscores = rawName.replace(/\.[^/.]+$/, '');
        const parts = baseWithUnderscores.split('_').filter(p => p);
        
        // Try to reconstruct and match patterns with underscores
        if (parts.length >= 2) {
            // Try to match patterns like "Asset_UI_Tank_War" or "Character_Module_Tank_War"
            const firstPart = parts[0].toLowerCase();
            const secondPart = parts[1] ? parts[1].toLowerCase() : '';
            const thirdPart = parts[2] ? parts[2].toLowerCase() : '';
            const fourthPart = parts[3] ? parts[3].toLowerCase() : '';
            
            // Match [Asset, UI] [Tank War]
            if (firstPart === 'asset' && secondPart === 'ui' && thirdPart === 'tank' && fourthPart === 'war') {
                const remainder = parts.slice(4);
                return {
                    groupLabel: '[Asset, UI] [Tank War]',
                    displayTitle: remainder.length > 0 ? toTitleCase(remainder.join(' ')) : base.replace(/_/g, ' ')
                };
            }
            
            // Match [Character Module] [Tank War]
            if (firstPart === 'character' && secondPart === 'module' && thirdPart === 'tank' && fourthPart === 'war') {
                const remainder = parts.slice(4);
                return {
                    groupLabel: '[Character Module] [Tank War]',
                    displayTitle: remainder.length > 0 ? toTitleCase(remainder.join(' ')) : base.replace(/_/g, ' ')
                };
            }
            
            // Match [Combat Module] [Tank War]
            if (firstPart === 'combat' && secondPart === 'module' && thirdPart === 'tank' && fourthPart === 'war') {
                const remainder = parts.slice(4);
                return {
                    groupLabel: '[Combat Module] [Tank War]',
                    displayTitle: remainder.length > 0 ? toTitleCase(remainder.join(' ')) : base.replace(/_/g, ' ')
                };
            }
            
            // Match [Game Mode Module] [Tank War]
            if (firstPart === 'game' && secondPart === 'mode' && thirdPart === 'module' && parts[3] === 'tank' && parts[4] === 'war') {
                const remainder = parts.slice(5);
                return {
                    groupLabel: '[Game Mode Module] [Tank War]',
                    displayTitle: remainder.length > 0 ? toTitleCase(remainder.join(' ')) : base.replace(/_/g, ' ')
                };
            }
            
            // Match [Monetization Module] [Tank War]
            if (firstPart === 'monetization' && secondPart === 'module' && thirdPart === 'tank' && fourthPart === 'war') {
                const remainder = parts.slice(4);
                return {
                    groupLabel: '[Monetization Module] [Tank War]',
                    displayTitle: remainder.length > 0 ? toTitleCase(remainder.join(' ')) : base.replace(/_/g, ' ')
                };
            }
            
            // Match [Multiplayer Module] [Tank War]
            if (firstPart === 'multiplayer' && secondPart === 'module' && thirdPart === 'tank' && fourthPart === 'war') {
                const remainder = parts.slice(4);
                return {
                    groupLabel: '[Multiplayer Module] [Tank War]',
                    displayTitle: remainder.length > 0 ? toTitleCase(remainder.join(' ')) : base.replace(/_/g, ' ')
                };
            }
            
            // Match [Progression Module] [Tank War]
            if (firstPart === 'progression' && secondPart === 'module' && thirdPart === 'tank' && fourthPart === 'war') {
                const remainder = parts.slice(4);
                return {
                    groupLabel: '[Progression Module] [Tank War]',
                    displayTitle: remainder.length > 0 ? toTitleCase(remainder.join(' ')) : base.replace(/_/g, ' ')
                };
            }
            
            // Match [Progression Module] [Tank Wars] (plural)
            if (firstPart === 'progression' && secondPart === 'module' && thirdPart === 'tank' && fourthPart === 'wars') {
                const remainder = parts.slice(4);
                return {
                    groupLabel: '[Progression Module] [Tank Wars]',
                    displayTitle: remainder.length > 0 ? toTitleCase(remainder.join(' ')) : base.replace(/_/g, ' ')
                };
            }
            
            // Match [World] [Tank War]
            if (firstPart === 'world' && secondPart === 'tank' && thirdPart === 'war') {
                const remainder = parts.slice(3);
                return {
                    groupLabel: '[World] [Tank War]',
                    displayTitle: remainder.length > 0 ? toTitleCase(remainder.join(' ')) : base.replace(/_/g, ' ')
                };
            }
        }
        
        // If no pattern matches, return as [Other]
        return { 
            groupLabel: '[Other]', 
            displayTitle: toTitleCase(base.replace(/_/g, ' '))
        };
    }

    function toTitleCase(str) {
        return str
            .split(' ')
            .filter(Boolean)
            .map(word => word.charAt(0).toUpperCase() + word.slice(1))
            .join(' ');
    }
    
    function addTypingIndicator() {
        const typingDiv = document.createElement('div');
        typingDiv.className = 'message bot-message typing-indicator';
        typingDiv.textContent = 'Thinking...';
        chatContainer.appendChild(typingDiv);
        chatContainer.scrollTop = chatContainer.scrollHeight;
        return typingDiv;
    }
    
    function removeTypingIndicator(indicator) {
        indicator.remove();
    }
    
    function loadDocumentSections(docId) {
        if (!docId) {
            documentSections = [];
            return;
        }
        
        console.log('[Section Dropdown] Loading sections for doc_id:', docId);
        fetch(`/api/gdd/sections?doc_id=${encodeURIComponent(docId)}`)
            .then(parseJsonSafe)
            .then(data => {
                console.log('[Section Dropdown] Received sections data:', data);
                if (data.sections && Array.isArray(data.sections)) {
                    documentSections = data.sections;
                    console.log('[Section Dropdown] Loaded', documentSections.length, 'sections');
                } else {
                    documentSections = [];
                    console.warn('[Section Dropdown] No sections in response:', data);
                }
            })
            .catch(error => {
                console.error('[Section Dropdown] Error loading sections:', error);
                documentSections = [];
            });
    }
    
    function handleSectionDropdown() {
        const inputValue = queryInput.value;
        const cursorPos = queryInput.selectionStart || inputValue.length;
        
        // Check if we have a document selected and sections loaded
        if (!selectedDocId || !selectedDocument || selectedDocument === 'All Documents') {
            hideSectionDropdown();
            return;
        }
        
        if (documentSections.length === 0) {
            console.log('[Section Dropdown] No sections loaded yet, hiding dropdown');
            hideSectionDropdown();
            return;
        }
        
        // Find all @ symbols in the input before cursor
        const textBeforeCursor = inputValue.substring(0, cursorPos);
        const atMatches = [...textBeforeCursor.matchAll(/@/g)];
        
        // Need at least 2 @ symbols (one for document, one for section)
        if (atMatches.length < 2) {
            hideSectionDropdown();
            return;
        }
        
        // Get the last @ position (this is the section @)
        const lastAtPos = atMatches[atMatches.length - 1].index;
        
        // Check if cursor is within a reasonable distance from the last @
        // This prevents dropdown from showing when typing far from the @
        const distanceFromAt = cursorPos - lastAtPos - 1;
        const textAfterLastAt = textBeforeCursor.substring(lastAtPos + 1);
        
        // Only show dropdown if:
        // 1. Cursor is right after @ (distance 0) OR
        // 2. Cursor is within the search term (no spaces after last @)
        const hasSpaceAfterAt = textAfterLastAt.includes(' ');
        if (hasSpaceAfterAt) {
            // User has already selected a section (indicated by space after section name)
            hideSectionDropdown();
            return;
        }
        
        // Extract search term after the last @
        const searchTerm = textAfterLastAt.trim();
        
        console.log('[Section Dropdown] Showing dropdown for search term:', searchTerm, 'at position', lastAtPos);
        showSectionDropdown(searchTerm, lastAtPos);
    }
    
    function showSectionDropdown(searchTerm, atPosition) {
        if (!documentSections || documentSections.length === 0) {
            console.log('[Section Dropdown] No sections available to show');
            hideSectionDropdown();
            return;
        }
        
        // Filter sections by search term
        const filtered = documentSections.filter(section => {
            const name = (section.section_name || section.section_path || '').toLowerCase();
            return name.includes(searchTerm.toLowerCase());
        });
        
        // Show all sections if no search term, otherwise show filtered
        const sectionsToShow = searchTerm.length > 0 ? filtered : documentSections.slice(0, 20); // Limit to 20 for performance
        
        if (sectionsToShow.length === 0) {
            console.log('[Section Dropdown] No sections match search term:', searchTerm);
            hideSectionDropdown();
            return;
        }
        
        console.log('[Section Dropdown] Showing', sectionsToShow.length, 'sections');
        
        // Create or update dropdown
        if (!sectionDropdown) {
            sectionDropdown = document.createElement('div');
            sectionDropdown.className = 'section-dropdown';
            sectionDropdown.id = 'section-dropdown';
            document.body.appendChild(sectionDropdown);
        }
        
        // Clear and populate dropdown
        sectionDropdown.innerHTML = '';
        
        sectionsToShow.forEach((section, index) => {
            const item = document.createElement('div');
            item.className = 'section-item';
            if (index === 0) {
                item.classList.add('highlighted');
            }
            item.textContent = section.section_name || section.section_path || 'Unknown Section';
            item.dataset.sectionName = section.section_name || section.section_path || '';
            item.dataset.sectionPath = section.section_path || '';
            
            item.addEventListener('click', function() {
                insertSectionIntoQuery(section.section_name || section.section_path || '');
            });
            
            item.addEventListener('mouseenter', function() {
                sectionDropdown.querySelectorAll('.section-item').forEach(i => i.classList.remove('highlighted'));
                item.classList.add('highlighted');
            });
            
            sectionDropdown.appendChild(item);
        });
        
        // Position dropdown ABOVE the input (fixed positioning is relative to viewport)
        const inputRect = queryInput.getBoundingClientRect();
        const dropdownHeight = 200; // Max height for dropdown
        
        sectionDropdown.style.display = 'block';
        sectionDropdown.style.position = 'fixed';
        // Position above the input, subtract dropdown height and add small gap
        sectionDropdown.style.bottom = (window.innerHeight - inputRect.top + 5) + 'px';
        sectionDropdown.style.left = inputRect.left + 'px';
        sectionDropdown.style.width = Math.min(inputRect.width, 400) + 'px';
        sectionDropdown.style.maxHeight = dropdownHeight + 'px';
        sectionDropdown.style.overflowY = 'auto';
        sectionDropdown.style.zIndex = '10000';
        
        console.log('[Section Dropdown] Positioned at:', {
            bottom: sectionDropdown.style.bottom,
            left: sectionDropdown.style.left,
            width: sectionDropdown.style.width,
            display: sectionDropdown.style.display
        });
    }
    
    function hideSectionDropdown() {
        if (sectionDropdown) {
            sectionDropdown.style.display = 'none';
        }
    }
    
    function insertSectionIntoQuery(sectionName) {
        const inputValue = queryInput.value;
        const cursorPos = queryInput.selectionStart || inputValue.length;
        
        // Find the last @ before cursor
        const textBeforeCursor = inputValue.substring(0, cursorPos);
        const lastAtPos = textBeforeCursor.lastIndexOf('@');
        
        if (lastAtPos === -1) {
            return;
        }
        
        // Replace text after @ with section name + space
        const textAfterCursor = inputValue.substring(cursorPos);
        const beforeAt = inputValue.substring(0, lastAtPos + 1);
        
        // Add section name with space after it
        const newValue = beforeAt + sectionName + ' ' + textAfterCursor;
        queryInput.value = newValue;
        
        // Set cursor after section name and space
        const newCursorPos = lastAtPos + 1 + sectionName.length + 1;
        queryInput.setSelectionRange(newCursorPos, newCursorPos);
        queryInput.focus();
        
        // Hide dropdown immediately
        hideSectionDropdown();
        
        console.log('[Section Dropdown] Inserted section:', sectionName);
    }
});

