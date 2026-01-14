// Code Q&A functionality
document.addEventListener('DOMContentLoaded', function() {
    const chatContainer = document.getElementById('chat-container');
    const queryInput = document.getElementById('query-input');
    const sendBtn = document.getElementById('send-btn');
    const filesList = document.getElementById('files-list');
    const fileSearch = document.getElementById('file-search');
    const alphabetNav = document.getElementById('alphabet-nav');
    const fileCountSpan = document.getElementById('file-count');
    
    let selectedFiles = []; // Track selected files
    let allFilesData = null; // Store all files for filtering
    const CHAT_STORAGE_KEY = 'code_chat_history';
    let isUpdatingFromSelection = false; // Flag to prevent circular updates
    
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
    
    // Load files on page load
    loadFiles();
    // Restore chat history
    loadChatHistory();
    
    // Search functionality
    fileSearch.addEventListener('input', function() {
        filterFiles(this.value);
    });
    
    // Send query
    sendBtn.addEventListener('click', sendQuery);
    queryInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            sendQuery();
        }
    });
    
    // Sync input box with @filename patterns
    queryInput.addEventListener('input', function() {
        if (!isUpdatingFromSelection) {
            syncSelectionFromInput();
        }
    });
    
    function sendQuery() {
        const query = queryInput.value.trim();
        if (!query) return;
        
        // Extract query text (remove @filename patterns for the actual query)
        const queryParts = query.split(/\s+/);
        const queryText = queryParts.filter(part => !part.startsWith('@')).join(' ');
        
        // Add user message (show the full input including @patterns)
        addMessage(query, 'user');
        
        // Clear input but preserve @filename patterns if files are selected
        if (selectedFiles.length > 0) {
            // Reset input so that only @filename patterns remain after this send.
            // This ensures the question text is cleared while keeping the file filter.
            queryInput.value = '';
            syncInputFromSelection();
        } else {
            queryInput.value = '';
        }
        
        // Show typing indicator
        const typingIndicator = addTypingIndicator();
        
        // Send to API (use the text query, file_filters are already set from selectedFiles)
        fetch('/api/code/query', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                query: queryText || query, // Use queryText if available, fallback to full query
                file_filters: selectedFiles.length > 0 ? selectedFiles : null,
                rerank: false  // Reranking disabled
            })
        })
        .then(response => response.json())
        .then(data => {
            removeTypingIndicator(typingIndicator);
            if (data.status === 'error') {
                addMessage('Error: ' + (data.response || data.error || 'Query failed'), 'bot');
            } else if (data.requires_method_selection && data.methods) {
                // Show method selection UI
                addMethodSelectionUI(data.response, data.methods, data.file_path, queryText || query, data.global_variables);
            } else {
                addMessage(data.response || 'No response received', 'bot');
            }
        })
        .catch(error => {
            removeTypingIndicator(typingIndicator);
            addMessage('Error: ' + error.message, 'bot');
        });
    }
    
    function loadFiles() {
        fetch('/api/code/files')
            .then(response => response.json())
            .then(data => {
                // Handle both formats: {files: [...]} or just [...]
                allFilesData = data.files || data || [];
                console.log(`Loaded ${allFilesData.length} files`);
                renderFiles(allFilesData);
            })
            .catch(error => {
                console.error('Error loading files:', error);
                filesList.innerHTML = '<p style="font-size:0.85rem;color:#d32f2f;">Error loading files: ' + error.message + '</p>';
            });
    }
    
    const EXTENSION_COLORS = {
        ts: 'ext-ts', tsx: 'ext-tsx', js: 'ext-js', jsx: 'ext-jsx',
        py: 'ext-py', cs: 'ext-cs', cpp: 'ext-cpp', json: 'ext-json',
        md: 'ext-md', css: 'ext-css', html: 'ext-html'
    };

    function renderFiles(files) {
        filesList.innerHTML = '';
        if (alphabetNav) alphabetNav.innerHTML = '';
        
        if (!files || files.length === 0) {
            filesList.innerHTML = '<p style="font-size:0.75rem;padding:20px;opacity:0.5;">No files indexed yet.</p>';
            if (fileCountSpan) fileCountSpan.textContent = '(0)';
            return;
        }
        
        const searchTerm = fileSearch.value.toLowerCase().trim();
        const filteredFiles = files.filter(file => {
            if (!searchTerm) return true;
            const name = (file.file_name || file.name || '').toLowerCase();
            return name.includes(searchTerm) || (file.file_path || '').toLowerCase().includes(searchTerm);
        });
        
        if (fileCountSpan) fileCountSpan.textContent = `(${filteredFiles.length})`;

        // Group files by first letter
        const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'.split('');
        const grouped = {};
        const availableLetters = new Set();

        filteredFiles.forEach(file => {
            const name = file.file_name || file.name || 'Unknown';
            const firstLetter = name[0].toUpperCase();
            if (!grouped[firstLetter]) grouped[firstLetter] = [];
            grouped[firstLetter].push(file);
            availableLetters.add(firstLetter);
        });

        // Render Alphabet Nav
        alphabet.forEach(letter => {
            const btn = document.createElement('button');
            btn.textContent = letter;
            btn.disabled = !availableLetters.has(letter);
            btn.addEventListener('click', () => {
                const target = document.getElementById(`letter-${letter}`);
                if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
            });
            alphabetNav.appendChild(btn);
        });

        // Render Groups
        alphabet.filter(l => grouped[l]).forEach(letter => {
            const groupDiv = document.createElement('div');
            groupDiv.className = 'document-group';
            groupDiv.id = `letter-${letter}`;

            const heading = document.createElement('div');
            heading.className = 'document-group-title';
            heading.innerHTML = `
                <div style="display:flex; align-items:center; gap:6px;">
                    <img src="/static/icons/chevron-down.svg" class="chevron" width="12">
                    <span>${letter}</span>
                </div>
                <span class="group-count">(${grouped[letter].length})</span>
            `;
            heading.addEventListener('click', () => groupDiv.classList.toggle('collapsed'));
            groupDiv.appendChild(heading);

            const list = document.createElement('ul');
            list.className = 'document-list';

            grouped[letter].sort((a, b) => (a.file_name || a.name).localeCompare(b.file_name || b.name)).forEach(file => {
                const path = file.file_path || file.path || '';
                const name = file.file_name || file.name || 'Unknown';
                const ext = name.split('.').pop().toLowerCase();
                const badgeClass = EXTENSION_COLORS[ext] || 'ext-default';

                const item = document.createElement('li');
                item.className = 'document-item';
                if (selectedFiles.includes(path)) item.classList.add('selected');
                
                item.innerHTML = `
                    <div style="display:flex; flex-direction:column; min-width:0; flex:1;">
                        <div style="display:flex; align-items:center; gap:8px;">
                            <span class="ext-badge ${badgeClass}">.${ext}</span>
                            <span class="name">${name}</span>
                        </div>
                        <div class="file-path">${path}</div>
                    </div>
                `;
                item.addEventListener('click', () => toggleFileSelection(path, item));
                list.appendChild(item);
            });

            groupDiv.appendChild(list);
            filesList.appendChild(groupDiv);
        });
    }
    
    function filterFiles(searchTerm) {
        if (allFilesData) {
            renderFiles(allFilesData);
        } else {
            loadFiles();
        }
    }
    
    function toggleFileSelection(filePath, element) {
        if (selectedFiles.includes(filePath)) {
            // Deselect
            selectedFiles = selectedFiles.filter(f => f !== filePath);
            element.classList.remove('selected');
        } else {
            // Select
            selectedFiles.push(filePath);
            element.classList.add('selected');
        }
        
        // Re-render files to move selected files to top
        if (allFilesData) {
            renderFiles(allFilesData);
        }
        
        // Update input box with @filename patterns
        syncInputFromSelection();
    }
    
    function syncInputFromSelection() {
        if (!allFilesData) return;
        
        isUpdatingFromSelection = true;
        
        // Get current input value
        const currentValue = queryInput.value;
        
        // Extract the query part (everything that's not @filename)
        const queryParts = currentValue.split(/\s+/);
        const queryText = queryParts.filter(part => !part.startsWith('@')).join(' ');
        
        // Build new input value with @filename patterns
        const atPatterns = selectedFiles.map(filePath => {
            const file = allFilesData.find(f => (f.file_path || f.path) === filePath);
            const fileName = file ? (file.file_name || file.name) : filePath.split(/[/\\]/).pop();
            return `@${fileName} `; // Add space after each @filename
        });
        
        // Combine @patterns and query text
        const newValue = [...atPatterns, queryText].filter(s => s.trim()).join(' ').trim();
        queryInput.value = newValue;
        
        isUpdatingFromSelection = false;
    }
    
    function syncSelectionFromInput() {
        if (!allFilesData) return;
        
        const inputValue = queryInput.value;
        
        // Extract all @filename patterns from input
        const atPatterns = inputValue.match(/@(\S+)/g) || [];
        const fileNamesFromInput = atPatterns.map(pattern => pattern.substring(1)); // Remove @
        
        // Find matching files
        const newSelectedFiles = [];
        fileNamesFromInput.forEach(fileName => {
            // Try to find exact match by file_name
            const file = allFilesData.find(f => {
                const fName = (f.file_name || f.name || '').toLowerCase();
                const fPath = (f.file_path || f.path || '').toLowerCase();
                return fName === fileName.toLowerCase() || 
                       fPath.toLowerCase().endsWith(fileName.toLowerCase());
            });
            if (file) {
                const filePath = file.file_path || file.path;
                if (filePath && !newSelectedFiles.includes(filePath)) {
                    newSelectedFiles.push(filePath);
                }
            }
        });
        
        // Update selectedFiles
        const selectionChanged = JSON.stringify(selectedFiles.sort()) !== JSON.stringify(newSelectedFiles.sort());
        selectedFiles = newSelectedFiles;
        
        // Re-render files to move selected files to top if selection changed
        if (selectionChanged && allFilesData) {
            renderFiles(allFilesData);
        } else {
            // Update UI to reflect selection
            updateFileSelectionUI();
        }
    }
    
    function updateFileSelectionUI() {
        // Update all file items to show selection state
        const fileItems = filesList.querySelectorAll('.document-item');
        fileItems.forEach(item => {
            const filePath = item.title; // We store filePath in title attribute
            if (selectedFiles.includes(filePath)) {
                item.classList.add('selected');
            } else {
                item.classList.remove('selected');
            }
        });
    }
    
    function addMessage(text, type, fromHistory) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${type}-message`;
        
        // Format text with code block support
        const formattedText = formatMessage(text);
        messageDiv.innerHTML = formattedText;
        
        chatContainer.appendChild(messageDiv);
        chatContainer.scrollTop = chatContainer.scrollHeight;

        // Persist to localStorage unless loading from history
        if (!fromHistory) {
            saveMessageToHistory(text, type);
        }
    }
    
    function formatMessage(text) {
        if (!text) return '';
        
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
            // Optional: cap history length
            if (existing.length > 200) {
                existing.splice(0, existing.length - 200);
            }
            localStorage.setItem(CHAT_STORAGE_KEY, JSON.stringify(existing));
        } catch (e) {
            console.error('Failed to save chat history:', e);
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
            console.error('Failed to load chat history:', e);
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
            } catch (e) {
                console.error('Failed to clear chat history:', e);
            }
            // Restore welcome message
            chatContainer.innerHTML = '';
            const welcome = document.createElement('div');
            welcome.className = 'message bot-message';
            welcome.textContent = 'Welcome! Ask questions about your C# codebase. Use @filename.cs to filter to specific files.';
            chatContainer.appendChild(welcome);
        });
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
    
    function addMethodSelectionUI(message, methods, filePath, originalQuery, globalVariables) {
        // Add the message first
        addMessage(message, 'bot');
        
        // Build checkbox HTML with Global Variables first
        let checkboxesHTML = '';
        
        // Add Global Variables option at the top if they exist
        if (globalVariables && globalVariables.length > 0) {
            checkboxesHTML += `
                <label class="method-checkbox-label" style="font-weight: bold; border-bottom: 1px solid #ddd; padding-bottom: 8px; margin-bottom: 8px;">
                    <input type="checkbox" class="method-checkbox" value="__GLOBAL_VARIABLES__" data-type="global">
                    <span>Global Variables <span style="color: #666; font-size: 0.9em;">(${globalVariables.length} fields/properties)</span></span>
                </label>
            `;
        }
        
        // Add methods
        checkboxesHTML += methods.map((method, idx) => `
            <label class="method-checkbox-label">
                <input type="checkbox" class="method-checkbox" value="${method.name}" data-line="${method.line}" data-type="method">
                <span>${method.name} <span style="color: #666; font-size: 0.9em;">(line ${method.line})</span></span>
            </label>
        `).join('');
        
        // Create method selection UI
        const selectionDiv = document.createElement('div');
        selectionDiv.className = 'message bot-message method-selection-ui';
        selectionDiv.innerHTML = `
            <div class="method-selection-container">
                <p style="margin-bottom: 12px; font-weight: 500;">Select method(s) or Global Variables to view variables:</p>
                <div class="method-checkboxes" id="method-checkboxes-${Date.now()}">
                    ${checkboxesHTML}
                </div>
                <div style="margin-top: 16px;">
                    <button class="btn-primary method-submit-btn" style="padding: 8px 16px; font-size: 0.9em;">Get Variables</button>
                    <button class="btn-secondary method-cancel-btn" style="padding: 8px 16px; font-size: 0.9em; margin-left: 8px;">Cancel</button>
                </div>
            </div>
        `;
        
        chatContainer.appendChild(selectionDiv);
        chatContainer.scrollTop = chatContainer.scrollHeight;
        
        // Store data for submission
        const containerId = selectionDiv.querySelector('.method-checkboxes').id;
        const submitBtn = selectionDiv.querySelector('.method-submit-btn');
        const cancelBtn = selectionDiv.querySelector('.method-cancel-btn');
        
        submitBtn.addEventListener('click', function() {
            const checkboxes = selectionDiv.querySelectorAll('.method-checkbox:checked');
            const selectedMethods = [];
            
            Array.from(checkboxes).forEach(cb => {
                selectedMethods.push(cb.value);
            });
            
            if (selectedMethods.length === 0) {
                alert('Please select at least one method or Global Variables.');
                return;
            }
            
            // Remove the selection UI
            selectionDiv.remove();
            
            // Show typing indicator
            const typingIndicator = addTypingIndicator();
            
            // Send query with selected methods (including __GLOBAL_VARIABLES__ if selected)
            fetch('/api/code/query', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    query: originalQuery,
                    file_filters: filePath ? [filePath] : (selectedFiles.length > 0 ? selectedFiles : null),
                    selected_methods: selectedMethods,
                    rerank: false
                })
            })
            .then(response => response.json())
            .then(data => {
                removeTypingIndicator(typingIndicator);
                if (data.status === 'error') {
                    addMessage('Error: ' + (data.response || data.error || 'Query failed'), 'bot');
                } else {
                    addMessage(data.response || 'No response received', 'bot');
                }
            })
            .catch(error => {
                removeTypingIndicator(typingIndicator);
                addMessage('Error: ' + error.message, 'bot');
            });
        });
        
        cancelBtn.addEventListener('click', function() {
            selectionDiv.remove();
        });
    }
});

