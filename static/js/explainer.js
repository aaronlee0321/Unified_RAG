// Document Explainer functionality (Tab 2)
// Exact replication of keyword_extractor Gradio app behavior using vanilla JS

document.addEventListener('DOMContentLoaded', function() {
    // Only initialize if we're on the Explainer page
    // Check for unique explainer elements instead of a tab-specific ID
    const explainerKeyword = document.getElementById('explainer-keyword');
    if (!explainerKeyword) {
        return;
    }
    
    // Document Explainer elements
    const explainerSearchBtn = document.getElementById('explainer-search-btn');
    const explainerResultsContainer = document.getElementById('explainer-results-container');
    const explainerResultsCheckboxes = document.getElementById('explainer-results-checkboxes');
    const resultsCount = document.getElementById('results-count');
    const selectAllCheckbox = document.getElementById('select-all-checkbox');
    const selectNoneCheckbox = document.getElementById('select-none-checkbox');
    const explainBtn = document.getElementById('explain-btn');
    const explanationOutput = document.getElementById('explanation-output');
    const sourceChunksOutput = document.getElementById('source-chunks-output');
    const metadataOutput = document.getElementById('metadata-output');
    
    // State management (replaces Gradio State)
    let storedResults = []; // Replaces explainer_search_results_store
    let lastSearchKeyword = null; // Replaces last_search_keyword
    let deepSearchContext = null; // Track deep search: { originalKeyword, selectedKeyword }
    
    // Alias management state
    const aliasState = {
        keywords: [],
        expandedKeywords: new Set(),
        searchQuery: "",
        selectedLanguage: null,
        newAliasInput: {}
    };

    // Event handlers
    explainerSearchBtn.addEventListener('click', searchForExplainer);
    explainerKeyword.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            searchForExplainer();
        }
    });
    explainerKeyword.addEventListener('input', updateGenerateButtonState);
    selectAllCheckbox.addEventListener('change', handleSelectAll);
    selectNoneCheckbox.addEventListener('change', handleSelectNone);
    explainBtn.addEventListener('click', generateExplanation);

    // Collapsible Logic
    const selectionHeader = document.getElementById('selection-header');
    const selectionContent = document.getElementById('selection-content');
    const chevron = selectionHeader?.querySelector('.chevron-toggle');

    selectionHeader?.addEventListener('click', () => {
        selectionContent.classList.toggle('collapsed');
        if (chevron) {
            chevron.style.transform = selectionContent.classList.contains('collapsed') 
                ? 'rotate(-90deg)' : 'rotate(0deg)';
        }
    });
    
    // Manage Aliases UI elements
    const openAliasesBtn = document.getElementById('open-aliases-btn');
    const closeAliasesBtn = document.getElementById('close-aliases-btn');
    const aliasesDrawer = document.getElementById('aliases-drawer');
    const aliasKeywordsList = document.getElementById('alias-keywords-list');
    const aliasSearchInput = document.getElementById('alias-search-input');
    const aliasResultsStats = document.getElementById('alias-results-stats');
    const aliasAddKeywordBtn = document.getElementById('alias-add-keyword-btn');
    const addAliasKeywordDialog = document.getElementById('add-alias-keyword-dialog');
    const confirmAddAliasKeywordBtn = document.getElementById('confirm-add-alias-keyword');
    const aliasLangFilterBtns = document.querySelectorAll('#aliases-drawer .filter-tag');

    // Manage Aliases Event Listeners
    if (openAliasesBtn) openAliasesBtn.addEventListener('click', () => {
        aliasesDrawer.classList.add('open');
        loadAliases();
    });
    if (closeAliasesBtn) closeAliasesBtn.addEventListener('click', () => aliasesDrawer.classList.remove('open'));
    if (aliasSearchInput) aliasSearchInput.addEventListener('input', (e) => {
        aliasState.searchQuery = e.target.value;
        renderAliases();
    });
    if (aliasAddKeywordBtn) aliasAddKeywordBtn.addEventListener('click', () => {
        addAliasKeywordDialog.classList.remove('hidden');
        document.getElementById('new-alias-keyword-name').focus();
    });
    if (addAliasKeywordDialog) {
        addAliasKeywordDialog.querySelector('.close-dialog-btn').onclick = () => addAliasKeywordDialog.classList.add('hidden');
        addAliasKeywordDialog.onclick = (e) => { if (e.target === addAliasKeywordDialog) addAliasKeywordDialog.classList.add('hidden'); };
    }
    
    aliasLangFilterBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            aliasLangFilterBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            const lang = btn.dataset.lang;
            aliasState.selectedLanguage = lang === 'all' ? null : lang;
            renderAliases();
        });
    });

    const modalLangBtns = document.querySelectorAll('.lang-select-btn');
    modalLangBtns.forEach(btn => {
        btn.onclick = () => {
            modalLangBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
        };
    });

    if (confirmAddAliasKeywordBtn) confirmAddAliasKeywordBtn.onclick = handleConfirmAddKeyword;

    // Initialize button state
    updateGenerateButtonState();
    
    // Initialize empty state - show results container with count 0
    const resultsCountNumber = document.getElementById('results-count-number');
    const selectedCountBadge = document.getElementById('selected-count-badge');
    if (resultsCountNumber) resultsCountNumber.textContent = '0';
    if (selectedCountBadge) selectedCountBadge.textContent = '0';
    explainerResultsContainer.style.display = 'flex';
    const emptyLeft = document.getElementById('explainer-empty-left');
    if (emptyLeft) emptyLeft.style.display = 'none';
    
    // --- SEARCH LOGIC WITH ALIASES ---
    async function searchForExplainer() {
        const keyword = explainerKeyword.value.trim();
        const emptyLeft = document.getElementById('explainer-empty-left');
        const resultsCountNumber = document.getElementById('results-count-number');
        const selectedCountBadge = document.getElementById('selected-count-badge');
        
        if (!keyword) {
            // Always show results container, even when empty
            explainerResultsContainer.style.display = 'flex';
            if (emptyLeft) emptyLeft.style.display = 'none';
            resultsCount.style.display = 'none';
            storedResults = [];
            renderCheckboxes([]);
            if (resultsCountNumber) resultsCountNumber.textContent = '0';
            if (selectedCountBadge) selectedCountBadge.textContent = '0';
            updateGenerateButtonState();
            return;
        }
        
        try {
            explainerSearchBtn.disabled = true;
            resultsCount.style.display = 'block';
            resultsCount.innerHTML = '<div style="display:flex;align-items:center;gap:8px;"><div class="spinner" style="width:14px;height:14px;"></div> <span>Searching...</span></div>';
            
            // Check for aliases first
            let searchKeywords = [keyword];
            await loadAliases(); // Ensure keywords are loaded
            
            const foundAliasKW = aliasState.keywords.find(kw => 
                kw.aliases.some(a => a.name.toLowerCase() === keyword.toLowerCase())
            );
            
            if (foundAliasKW) {
                console.log(`Found alias for "${keyword}" -> Primary keyword: "${foundAliasKW.name}"`);
                searchKeywords.push(foundAliasKW.name);
                resultsCount.innerHTML = `<div style="display:flex;align-items:center;gap:8px;"><div class="spinner" style="width:14px;height:14px;"></div> <span>Searching for "${keyword}" and "${foundAliasKW.name}"...</span></div>`;
            }

            // Execute search for each keyword and merge results
            let allChoices = [];
            let allStoreData = [];
            let mergedKeys = new Set();

            for (const kw of searchKeywords) {
                const response = await fetch('/api/gdd/explainer/search', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ keyword: kw })
                });
                const result = await response.json();
                
                if (result.success && result.choices) {
                    result.choices.forEach((choice, idx) => {
                        const storeItem = result.store_data[idx];
                        const key = `${storeItem.doc_id}:${storeItem.section_heading}`;
                        if (!mergedKeys.has(key)) {
                            mergedKeys.add(key);
                            allChoices.push(choice);
                            allStoreData.push(storeItem);
                        }
                    });
                }
            }

            if (allChoices.length === 0) {
                // Show "No results" with "Search Deeper?" option
                resultsCount.innerHTML = `
                    <div style="display: flex; align-items: center; gap: 12px;">
                        <span>No results found.</span>
                        <button id="deep-search-btn" class="btn-secondary" style="height: 28px; padding: 0 12px; font-size: 0.75rem;">
                            Search Deeper?
                        </button>
                    </div>
                `;
                resultsCount.style.color = "var(--muted-foreground)";
                explainerResultsContainer.style.display = 'flex';
                if (emptyLeft) emptyLeft.style.display = 'none';
                renderCheckboxes([]);
                if (resultsCountNumber) resultsCountNumber.textContent = '0';
                if (selectedCountBadge) selectedCountBadge.textContent = '0';
                
                // Attach deep search handler
                const deepSearchBtn = document.getElementById('deep-search-btn');
                if (deepSearchBtn) {
                    deepSearchBtn.onclick = () => performDeepSearch(keyword);
                }
                return;
            }
            
            storedResults = allStoreData;
            lastSearchKeyword = keyword;
            
            // Always show results container
            explainerResultsContainer.style.display = 'flex';
            if (emptyLeft) emptyLeft.style.display = 'none';
            
            // Update count display
            const count = allChoices.length;
            if (resultsCountNumber) resultsCountNumber.textContent = count.toString();
            
            renderCheckboxes(allChoices);
            
            if (count > 0) {
                resultsCount.textContent = `Found ${count} result(s)`;
                resultsCount.style.color = "var(--muted-foreground)";
                
                // Show alias prompt if this was from deep search
                if (deepSearchContext && deepSearchContext.originalKeyword && deepSearchContext.selectedKeyword) {
                    // Delay slightly to let UI settle
                    setTimeout(() => {
                        showAddAliasPrompt(deepSearchContext.originalKeyword, deepSearchContext.selectedKeyword);
                        deepSearchContext = null; // Clear after showing
                    }, 500);
                }
            } else {
                resultsCount.textContent = "No results found.";
                resultsCount.style.color = "var(--muted-foreground)";
                deepSearchContext = null; // Clear if no results
            }
            
        } catch (error) {
            resultsCount.textContent = "Error: " + error.message;
            resultsCount.style.color = "var(--status-error)";
            explainerResultsContainer.style.display = 'flex';
            if (emptyLeft) emptyLeft.style.display = 'none';
            renderCheckboxes([]);
            if (resultsCountNumber) resultsCountNumber.textContent = '0';
            if (selectedCountBadge) selectedCountBadge.textContent = '0';
        } finally {
            explainerSearchBtn.disabled = false;
            updateGenerateButtonState();
        }
    }
    
    // Deep search functionality
    async function performDeepSearch(originalKeyword) {
        try {
            explainerSearchBtn.disabled = true;
            resultsCount.innerHTML = '<div style="display:flex;align-items:center;gap:8px;"><div class="spinner" style="width:14px;height:14px;"></div> <span>Searching deeper with AI...</span></div>';
            
            const response = await fetch('/api/gdd/explainer/deep-search', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ keyword: originalKeyword })
            });
            
            const deepResult = await response.json();
            
            if (deepResult.error) {
                resultsCount.textContent = `Error: ${deepResult.error}`;
                resultsCount.style.color = "var(--status-error)";
                return;
            }
            
            const matchedKeywords = deepResult.matched_keywords || [];
            
            if (matchedKeywords.length === 0) {
                resultsCount.textContent = "No matches found even with deep search. Try a different keyword.";
                resultsCount.style.color = "var(--muted-foreground)";
                return;
            }
            
            // Show modal for user to select keyword
            const selectedKeyword = await showKeywordSelectionModal(matchedKeywords, originalKeyword);
            
            if (selectedKeyword) {
                // Store deep search context for alias prompt
                deepSearchContext = {
                    originalKeyword: originalKeyword,
                    selectedKeyword: selectedKeyword
                };
                
                // Perform normal search with selected keyword
                explainerKeyword.value = selectedKeyword;
                await searchForExplainer();
                
                // After search completes, show alias prompt if results were found
                // This will be handled in searchForExplainer after results are displayed
            } else {
                deepSearchContext = null;
                resultsCount.textContent = "Search cancelled.";
                resultsCount.style.color = "var(--muted-foreground)";
            }
            
        } catch (error) {
            resultsCount.textContent = "Error in deep search: " + error.message;
            resultsCount.style.color = "var(--status-error)";
        } finally {
            explainerSearchBtn.disabled = false;
        }
    }
    
    function showKeywordSelectionModal(keywords, originalKeyword) {
        return new Promise((resolve) => {
            const modal = document.createElement('div');
            modal.className = 'modal';
            modal.style.cssText = 'position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0, 0, 0, 0.5); display: flex; align-items: center; justify-content: center; z-index: 1000;';
            
            modal.innerHTML = `
                <div class="modal-content" style="background: white; padding: 24px; border-radius: 8px; max-width: 500px; width: 90%; box-shadow: 0 10px 25px rgba(0,0,0,0.2);">
                    <h3 style="font-size: 1rem; font-weight: 600; margin: 0 0 12px 0;">Did you mean one of these?</h3>
                    <p style="font-size: 0.875rem; color: var(--muted-foreground); margin-bottom: 16px;">
                        We found these keywords that might match "${originalKeyword}":
                    </p>
                    <div class="keyword-options" style="display: flex; flex-direction: column; gap: 8px; margin: 16px 0; max-height: 300px; overflow-y: auto;">
                        ${keywords.map(kw => `
                            <button class="keyword-option-btn" data-keyword="${kw}" style="padding: 12px; background: var(--bg-muted); border: 1px solid var(--border); border-radius: 6px; cursor: pointer; text-align: left; transition: all 0.2s;">
                                ${kw}
                            </button>
                        `).join('')}
                    </div>
                    <div style="display: flex; gap: 8px; justify-content: flex-end; margin-top: 16px;">
                        <button class="cancel-btn btn-secondary" style="height: 36px; padding: 0 16px;">Cancel</button>
                    </div>
                </div>
            `;
            
            document.body.appendChild(modal);
            
            // Add hover effects
            const style = document.createElement('style');
            style.textContent = `
                .keyword-option-btn:hover {
                    background: var(--primary) !important;
                    color: white !important;
                    border-color: var(--primary) !important;
                }
            `;
            document.head.appendChild(style);
            
            modal.querySelectorAll('.keyword-option-btn').forEach(btn => {
                btn.addEventListener('click', () => {
                    const keyword = btn.dataset.keyword;
                    document.body.removeChild(modal);
                    document.head.removeChild(style);
                    resolve(keyword);
                });
            });
            
            modal.querySelector('.cancel-btn').addEventListener('click', () => {
                document.body.removeChild(modal);
                document.head.removeChild(style);
                resolve(null);
            });
            
            // Close on backdrop click
            modal.addEventListener('click', (e) => {
                if (e.target === modal) {
                    document.body.removeChild(modal);
                    document.head.removeChild(style);
                    resolve(null);
                }
            });
        });
    }
    
    // Show add alias prompt after deep search
    function showAddAliasPrompt(originalKeyword, selectedKeyword) {
        // Create a popup card on the right side (in explanation area)
        const explanationOutput = document.getElementById('explanation-output');
        if (!explanationOutput) return;
        
        // Check if there's already a prompt
        const existingPrompt = document.getElementById('add-alias-prompt');
        if (existingPrompt) {
            existingPrompt.remove();
        }
        
        // Create prompt card
        const promptCard = document.createElement('div');
        promptCard.id = 'add-alias-prompt';
        promptCard.style.cssText = `
            position: absolute;
            top: 20px;
            right: 20px;
            background: white;
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 16px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
            max-width: 320px;
            z-index: 100;
        `;
        
        promptCard.innerHTML = `
            <div style="display: flex; align-items: flex-start; gap: 12px;">
                <div style="flex: 1;">
                    <h4 style="font-size: 0.875rem; font-weight: 600; margin: 0 0 8px 0; color: var(--text-main);">
                        Add Alias?
                    </h4>
                    <p style="font-size: 0.75rem; color: var(--muted-foreground); margin: 0 0 12px 0; line-height: 1.4;">
                        Would you like to add <strong>"${originalKeyword}"</strong> as an alias for <strong>"${selectedKeyword}"</strong>?
                    </p>
                    <div style="display: flex; gap: 8px;">
                        <button id="confirm-add-alias-btn" class="btn-primary" style="height: 32px; padding: 0 12px; font-size: 0.75rem; flex: 1;">
                            Yes, Add
                        </button>
                        <button id="dismiss-alias-prompt-btn" class="btn-secondary" style="height: 32px; padding: 0 12px; font-size: 0.75rem;">
                            No
                        </button>
                    </div>
                </div>
                <button id="close-alias-prompt-btn" class="action-btn" style="padding: 4px; opacity: 0.5;">
                    <img src="/static/icons/close.svg" width="14" height="14">
                </button>
            </div>
        `;
        
        // Position relative to explanation bubble (right side panel)
        const explanationBubble = explanationOutput.closest('.explainer-bubble');
        if (explanationBubble) {
            // Ensure parent has relative positioning
            if (getComputedStyle(explanationBubble).position === 'static') {
                explanationBubble.style.position = 'relative';
            }
            explanationBubble.appendChild(promptCard);
        } else {
            // Fallback: append to explanation output
            if (getComputedStyle(explanationOutput).position === 'static') {
                explanationOutput.style.position = 'relative';
            }
            explanationOutput.appendChild(promptCard);
        }
        
        // Add event listeners
        const confirmBtn = promptCard.querySelector('#confirm-add-alias-btn');
        const dismissBtn = promptCard.querySelector('#dismiss-alias-prompt-btn');
        const closeBtn = promptCard.querySelector('#close-alias-prompt-btn');
        
        const removePrompt = () => {
            promptCard.style.opacity = '0';
            promptCard.style.transition = 'opacity 0.2s';
            setTimeout(() => {
                if (promptCard.parentNode) {
                    promptCard.parentNode.removeChild(promptCard);
                }
            }, 200);
        };
        
        confirmBtn.addEventListener('click', async () => {
            confirmBtn.disabled = true;
            confirmBtn.textContent = 'Adding...';
            
            try {
                // Detect language of original keyword
                const isVietnamese = /[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđĐ]/i.test(originalKeyword);
                const language = isVietnamese ? 'vi' : 'en';
                
                const response = await fetch('/api/manage/aliases', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        keyword: selectedKeyword,
                        alias: originalKeyword,
                        language: language
                    })
                });
                
                if (response.ok) {
                    confirmBtn.textContent = '✓ Added!';
                    confirmBtn.style.background = 'var(--status-success)';
                    setTimeout(removePrompt, 1000);
                } else {
                    const error = await response.json();
                    alert('Error adding alias: ' + (error.error || 'Unknown error'));
                    confirmBtn.disabled = false;
                    confirmBtn.textContent = 'Yes, Add';
                }
            } catch (error) {
                alert('Error adding alias: ' + error.message);
                confirmBtn.disabled = false;
                confirmBtn.textContent = 'Yes, Add';
            }
        });
        
        dismissBtn.addEventListener('click', removePrompt);
        closeBtn.addEventListener('click', removePrompt);
    }
    
    function renderCheckboxes(choices) {
        explainerResultsCheckboxes.innerHTML = '';
        
        if (!choices || choices.length === 0) {
            return;
        }
        
        choices.forEach((choice, index) => {
            const documentItem = document.createElement('div');
            documentItem.className = 'document-item explainer-item';
            documentItem.style.padding = '10px 12px';
            documentItem.style.cursor = 'pointer';
            
            const checkboxContainer = document.createElement('div');
            checkboxContainer.className = 'custom-checkbox';
            checkboxContainer.style.marginRight = '12px';
            
            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.id = `checkbox-${index}`;
            checkbox.value = choice;
            checkbox.name = 'explainer-choice';
            checkbox.style.display = 'none'; // Hidden, used for state
            
            // Visual Square icon
            const icon = document.createElement('div');
            icon.className = 'checkbox-icon';
            icon.innerHTML = `<img src="/static/icons/file.svg" width="16" height="16" style="opacity:0.3;">`; // Default empty state
            
            const label = document.createElement('span');
            label.style.fontSize = '0.8125rem';
            label.style.fontWeight = '500';
            label.textContent = choice;
            
            documentItem.appendChild(checkbox);
            documentItem.appendChild(icon);
            documentItem.appendChild(label);
            
            documentItem.addEventListener('click', () => {
                checkbox.checked = !checkbox.checked;
                updateItemVisualState(documentItem, checkbox.checked);
                updateGenerateButtonState();
                updateSelectAllNoneState();
            });

            documentItem.addEventListener('mouseenter', () => {
                documentItem.style.background = 'var(--muted)';
            });
            documentItem.addEventListener('mouseleave', () => {
                if (!checkbox.checked) documentItem.style.background = 'transparent';
            });
            
            explainerResultsCheckboxes.appendChild(documentItem);
        });
        
        // Reset select all/none checkboxes
        selectAllCheckbox.checked = false;
        selectNoneCheckbox.checked = false;
    }

    function updateItemVisualState(element, isChecked) {
        const icon = element.querySelector('.checkbox-icon');
        if (isChecked) {
            element.style.background = 'rgba(239, 68, 68, 0.05)';
            element.style.color = 'var(--primary)';
            icon.innerHTML = `<img src="/static/icons/success.svg" width="16" height="16" style="filter: invert(32%) sepia(85%) saturate(2853%) hue-rotate(345deg) brightness(101%) contrast(89%);">`;
        } else {
            element.style.background = 'transparent';
            element.style.color = 'inherit';
            icon.innerHTML = `<img src="/static/icons/file.svg" width="16" height="16" style="opacity:0.3;">`;
        }
    }

    function handleSelectAll() {
        if (selectAllCheckbox.checked) {
            selectNoneCheckbox.checked = false;
            const items = explainerResultsCheckboxes.querySelectorAll('.document-item');
            items.forEach(item => {
                const cb = item.querySelector('input');
                cb.checked = true;
                updateItemVisualState(item, true);
            });
            updateGenerateButtonState();
        }
    }

    function handleSelectNone() {
        if (selectNoneCheckbox.checked) {
            selectAllCheckbox.checked = false;
            const items = explainerResultsCheckboxes.querySelectorAll('.document-item');
            items.forEach(item => {
                const cb = item.querySelector('input');
                cb.checked = false;
                updateItemVisualState(item, false);
            });
            updateGenerateButtonState();
        }
    }
    
    function getSelectedChoices() {
        const checkboxes = explainerResultsCheckboxes.querySelectorAll('input[type="checkbox"][name="explainer-choice"]:checked');
        return Array.from(checkboxes).map(cb => cb.value);
    }
    
    async function generateExplanation() {
        const keyword = explainerKeyword.value.trim();
        const selectedChoices = getSelectedChoices();
        const genStatus = document.getElementById('gen-status');
        const chunksOutput = document.getElementById('source-chunks-output');
        const chunksLabel = document.getElementById('chunks-count-label');
        
        try {
            explainBtn.disabled = true;
            genStatus.innerHTML = '<div style="display:flex;align-items:center;gap:8px;color:var(--status-info)"><div class="spinner" style="width:12px;height:12px;"></div> Thinking...</div>';
            // Restore flex centering for placeholder state
            explanationOutput.style.display = 'flex';
            explanationOutput.style.alignItems = 'center';
            explanationOutput.style.justifyContent = 'center';
            explanationOutput.innerHTML = '<div class="placeholder-text" style="padding-top:100px;"><p>Synthesizing context from selected documents...</p></div>';
            chunksOutput.innerHTML = '<p class="placeholder-text">Retrieving relevant chunks...</p>';
            
            const response = await fetch('/api/gdd/explainer/explain', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    keyword,
                    selected_choices: selectedChoices,
                    stored_results: storedResults
                })
            });
            
            const result = await response.json();
            genStatus.textContent = result.success ? "✓ Completed" : "✕ Generation Failed";
            genStatus.style.color = result.success ? "var(--status-success)" : "var(--status-error)";
            
            if (!result.success) {
                // Keep block display for error message
                explanationOutput.style.display = 'block';
                explanationOutput.style.alignItems = 'stretch';
                explanationOutput.style.justifyContent = 'flex-start';
                explanationOutput.innerHTML = `<div class="placeholder-text"><p style="color:var(--status-error)">${result.explanation || 'Generation failed'}</p></div>`;
                return;
            }
            
            // Explanation formatting
            // Remove flex centering styles when content is present
            explanationOutput.style.display = 'block';
            explanationOutput.style.alignItems = 'stretch';
            explanationOutput.style.justifyContent = 'flex-start';
            explanationOutput.innerHTML = `<div class="generated-explanation" style="color: var(--foreground)">${renderMarkdown(result.explanation || '', 'Explanation', keyword)}</div>`;
            
            // Source Chunks formatting
            const chunks = result.source_chunks ? result.source_chunks.split('\n\n').filter(c => {
                const trimmed = c.trim();
                // Filter out the header "### Source Chunks (X chunks used)"
                return trimmed && !trimmed.startsWith('### Source Chunks');
            }) : [];
            if (chunksLabel) chunksLabel.textContent = `${chunks.length} chunks used`;
            
            chunksOutput.innerHTML = chunks.map((chunk, idx) => `
                <div class="source-chunk-card">
                    <div style="font-family: var(--font-mono); font-size: 11px; color: var(--muted-foreground); opacity: 0.8; margin-bottom: 6px;">CHUNK ${idx + 1}</div>
                    <div style="font-size: 12px; line-height: 1.5; color: rgba(0,0,0,0.7);">${chunk.replace(/^Chunk \d+:?\s*/i, '').replace(/^\*\*Chunk \d+\*\*.*?\n/i, '')}</div>
                </div>
            `).join('');

            // Metadata formatting
            const metaLines = result.metadata ? result.metadata.split('\n').filter(l => l.includes(': ')) : [];
            metadataOutput.innerHTML = `
                <div class="metadata-list">
                    ${metaLines.map(line => {
                        const [label, ...valParts] = line.split(': ');
                        return `
                            <div class="metadata-item">
                                <span class="metadata-label">${label}</span>
                                <span class="metadata-value">${valParts.join(': ')}</span>
                            </div>
                        `;
                    }).join('')}
                    <div class="metadata-item">
                        <span class="metadata-label">Timestamp</span>
                        <span class="metadata-value">${new Date().toLocaleString()}</span>
                    </div>
                </div>
            `;
            
        } catch (error) {
            genStatus.textContent = "Network Error";
            genStatus.style.color = "var(--status-error)";
            explanationOutput.innerHTML = `<p>Error: ${error.message}</p>`;
        } finally {
            explainBtn.disabled = false;
            updateGenerateButtonState();
        }
    }
    
    
    function updateSelectAllNoneState() {
        const checkboxes = explainerResultsCheckboxes.querySelectorAll('input[type="checkbox"][name="explainer-choice"]');
        const checkedCount = explainerResultsCheckboxes.querySelectorAll('input[type="checkbox"][name="explainer-choice"]:checked').length;
        const totalCount = checkboxes.length;

        // Update sticky badge
        const badge = document.getElementById('selected-count-badge');
        if (badge) badge.textContent = checkedCount;
        
        if (checkedCount === 0) {
            selectAllCheckbox.checked = false;
            selectNoneCheckbox.checked = false;
        } else if (checkedCount === totalCount) {
            selectAllCheckbox.checked = true;
            selectNoneCheckbox.checked = false;
        } else {
            selectAllCheckbox.checked = false;
            selectNoneCheckbox.checked = false;
        }
    }
    
    function updateGenerateButtonState() {
        const selectedChoices = getSelectedChoices();
        const keyword = explainerKeyword.value.trim();
        
        if (keyword && selectedChoices && selectedChoices.length > 0) {
            explainBtn.disabled = false;
        } else {
            explainBtn.disabled = true;
        }
    }
    
    function renderMarkdown(text, stripHeading, keyword = '') {
        if (!text) return '';
        
        // RENDERING ORDER: Process on plain text BEFORE markdown conversion
        let processedText = text;
        
        // Step 1: Process *word* syntax from LLM (highlight important keywords/phrases)
        // Use a temporary marker to avoid conflicts with markdown **bold** syntax
        // Replace *word* with a temporary marker, then convert to HTML after markdown processing
        const highlightMarkers = [];
        let markerIndex = 0;
        processedText = processedText.replace(/\*([^*]+?)\*/g, (match, content) => {
            const marker = `__HIGHLIGHT_MARKER_${markerIndex}__`;
            highlightMarkers.push(`<span class="keyword-highlight">${content}</span>`);
            markerIndex++;
            return marker;
        });
        
        // Step 2: Highlight search keyword in plain text (case-insensitive, whole words only)
        // This must happen BEFORE markdown rendering, but after *word* processing
        if (keyword && keyword.trim()) {
            const keywordEscaped = keyword.trim().replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
            const keywordRegex = new RegExp(`\\b(${keywordEscaped})\\b`, 'gi');
            
            // Find all existing markers to avoid overlapping highlights
            const markerPattern = /__HIGHLIGHT_MARKER_(\d+)__/g;
            const existingMarkers = [];
            let markerMatch;
            while ((markerMatch = markerPattern.exec(processedText)) !== null) {
                existingMarkers.push({
                    start: markerMatch.index,
                    end: markerMatch.index + markerMatch[0].length,
                    index: parseInt(markerMatch[1])
                });
            }
            
            // Only highlight if not overlapping with existing markers
            processedText = processedText.replace(keywordRegex, (match, offset, string) => {
                const matchStart = offset;
                const matchEnd = offset + match.length;
                
                // Check if this match overlaps with any existing marker
                for (const marker of existingMarkers) {
                    // If match is inside or overlaps with a marker, skip
                    if ((matchStart >= marker.start && matchStart < marker.end) ||
                        (matchEnd > marker.start && matchEnd <= marker.end) ||
                        (matchStart <= marker.start && matchEnd >= marker.end)) {
                        return match; // Skip, already highlighted via *word* syntax
                    }
                }
                
                // Add as a new highlight marker
                const marker = `__HIGHLIGHT_MARKER_${markerIndex}__`;
                highlightMarkers.push(`<span class="keyword-highlight">${match}</span>`);
                markerIndex++;
                return marker;
            });
        }
        
        // Step 3: Strip duplicate headings that match the bubble title
        if (stripHeading) {
            // Remove headings that exactly match the bubble title (case-insensitive)
            const headingPatterns = [
                new RegExp(`^#+\\s*${stripHeading}\\s*$`, 'gim'),
                new RegExp(`^#+\\s*${stripHeading.replace(/\s+/g, '\\s+')}\\s*$`, 'gim')
            ];
            
            headingPatterns.forEach(pattern => {
                processedText = processedText.replace(pattern, '');
            });
            
            // Also remove if it's the first line and matches
            const lines = processedText.split('\n');
            if (lines.length > 0) {
                const firstLine = lines[0].trim();
                const headingMatch = firstLine.match(/^#+\s*(.+)$/i);
                if (headingMatch && headingMatch[1].trim().toLowerCase() === stripHeading.toLowerCase()) {
                    lines.shift();
                    processedText = lines.join('\n');
                }
            }
        }
        
        // Step 4: Convert markdown to HTML
        let html = processedText;
        
        // Headers - NO <strong> wrapping, CSS will handle bold
        html = html.replace(/^### (.*$)/gim, '<h3>$1</h3>');
        html = html.replace(/^## (.*$)/gim, '<h2>$1</h2>');
        html = html.replace(/^# (.*$)/gim, '<h1>$1</h1>');
        
        // Markdown bold (**text**) - ONLY source of <strong> tags
        html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
        
        // Lists
        html = html.replace(/^\- (.*$)/gim, '<li>$1</li>');
        html = html.replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>');
        
        // Line breaks
        html = html.replace(/\n\n/g, '</p><p>');
        html = '<p>' + html + '</p>';
        
        // Fix nested lists
        html = html.replace(/<p><ul>/g, '<ul>');
        html = html.replace(/<\/ul><\/p>/g, '</ul>');
        html = html.replace(/<p><li>/g, '<li>');
        html = html.replace(/<\/li><\/p>/g, '</li>');
        html = html.replace(/<p><\/p>/g, '');
        
        // Step 5: Replace temporary highlight markers with actual HTML
        highlightMarkers.forEach((markerHtml, index) => {
            html = html.replace(`__HIGHLIGHT_MARKER_${index}__`, markerHtml);
        });
        
        return html;
    }

    // --- ALIAS MANAGEMENT CORE FUNCTIONS ---
    async function loadAliases() {
        try {
            const res = await fetch('/api/manage/aliases');
            const data = await res.json();
            aliasState.keywords = data.keywords || [];
            renderAliases();
        } catch (e) { console.error("Load aliases failed", e); }
    }

    async function saveAliases() {
        try {
            await fetch('/api/manage/aliases/save', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ keywords: aliasState.keywords })
            });
        } catch (e) { console.error("Save aliases failed", e); }
    }

    function renderAliases() {
        if (!aliasKeywordsList) return;

        const s = aliasState;
        let filtered = s.keywords.filter(kw => {
            if (s.selectedLanguage && kw.language !== s.selectedLanguage) return false;
            if (s.searchQuery.trim()) {
                const query = s.searchQuery.toLowerCase();
                const kwMatches = kw.name.toLowerCase().includes(query);
                const aliasMatches = kw.aliases.some(a => a.name.toLowerCase().includes(query));
                return kwMatches || aliasMatches;
            }
            return true;
        });

        // Alphabetical sorting in all three languages (English, Vietnamese, and general)
        filtered.sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: 'base' }));

        if (aliasResultsStats) {
            aliasResultsStats.textContent = `Results: ${filtered.length} of ${s.keywords.length} keywords`;
        }

        if (filtered.length === 0) {
            aliasKeywordsList.innerHTML = `
                <div class="flex flex-col items-center justify-center py-12 text-center opacity-40">
                    <i class="icon-database" style="font-size: 40px; margin-bottom: 12px;"></i>
                    <p style="font-size: 0.875rem;">
                        ${s.searchQuery ? `No results for "${s.searchQuery}"` : "No keywords yet."}
                    </p>
                </div>
            `;
            return;
        }

        aliasKeywordsList.innerHTML = filtered.map(kw => {
            const isExpanded = s.expandedKeywords.has(kw.id);
            return `
                <div class="alias-keyword-item" style="border-bottom: 1px solid var(--border);">
                    <div class="keyword-header" onclick="window.toggleKeywordExpansion('${kw.id}')" style="display: flex; align-items: center; justify-content: space-between; padding: 10px 12px; cursor: pointer;">
                        <div style="display: flex; align-items: center; gap: 8px; flex: 1; min-width: 0;">
                            <i class="icon-chevron-right" style="font-size: 14px; transition: transform 0.2s; ${isExpanded ? 'transform: rotate(90deg);' : ''}"></i>
                            <span style="font-weight: 500; font-size: 0.8125rem;" class="truncate">${kw.name}</span>
                            <span style="font-size: 0.7rem; color: var(--muted-foreground);">(${kw.aliases.length})</span>
                        </div>
                        <div style="display: flex; align-items: center; gap: 8px;">
                            <span class="badge badge-outline" style="font-size: 10px; padding: 1px 6px;">${kw.language}</span>
                            <button class="action-btn text-destructive" onclick="event.stopPropagation(); window.handleDeleteKeyword('${kw.id}')" style="color: var(--status-error);">
                                <i class="icon-trash-2" style="font-size: 14px;"></i>
                            </button>
                        </div>
                    </div>
                    ${isExpanded ? `
                        <div class="alias-expanded-content animate-in" style="background: rgba(0,0,0,0.02); padding: 8px 12px 12px 32px; border-top: 1px solid var(--border);">
                            <div class="alias-items-list" style="display: flex; flex-direction: column; gap: 2px;">
                                ${kw.aliases.map(a => `
                                    <div class="alias-item group" style="display: flex; align-items: center; justify-content: space-between; padding: 4px 8px; border-radius: 4px; font-size: 0.75rem;">
                                        <span style="color: var(--muted-foreground);">${a.name}</span>
                                        <button class="action-btn opacity-0 group-hover:opacity-100" onclick="window.handleDeleteAlias('${kw.id}', '${a.id}')" style="padding: 2px; color: var(--status-error);">
                                            <i class="icon-x" style="font-size: 12px;"></i>
                                        </button>
                                    </div>
                                `).join('')}
                            </div>
                            <div style="display: flex; gap: 6px; margin-top: 8px; pt-2; border-top: 1px solid rgba(0,0,0,0.05);">
                                <input 
                                    type="text" 
                                    placeholder="Add new alias..." 
                                    class="alias-input-field"
                                    id="input-${kw.id}"
                                    style="flex: 1; height: 28px; font-size: 0.75rem; border-radius: 4px; border: 1px solid var(--border); padding: 0 8px;"
                                    onkeydown="if(event.key==='Enter') window.handleAddAlias('${kw.id}', this.value)"
                                >
                                <button class="btn-primary" onclick="window.handleAddAlias('${kw.id}', document.getElementById('input-${kw.id}').value)" style="height: 28px; padding: 0 8px;">
                                    <i class="icon-plus" style="font-size: 14px;"></i>
                                </button>
                            </div>
                        </div>
                    ` : ''}
                </div>
            `;
        }).join('');
    }

    window.toggleKeywordExpansion = (id) => {
        if (aliasState.expandedKeywords.has(id)) {
            aliasState.expandedKeywords.delete(id);
        } else {
            aliasState.expandedKeywords.add(id);
        }
        renderAliases();
    };

    window.handleAddAlias = async (kwId, name) => {
        if (!name.trim()) return;
        const kw = aliasState.keywords.find(k => k.id === kwId);
        if (!kw) return;
        
        if (kw.aliases.some(a => a.name.toLowerCase() === name.trim().toLowerCase())) {
            alert("This alias already exists for this keyword");
            return;
        }
        
        try {
            // Detect language
            const isVietnamese = /[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđĐ]/i.test(name.trim());
            const language = isVietnamese ? 'vi' : 'en';
            
            const response = await fetch('/api/manage/aliases', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    keyword: kw.name,
                    alias: name.trim(),
                    language: language
                })
            });
            
            if (response.ok) {
                // Reload from server to get updated data
                await loadAliases();
            } else {
                const error = await response.json();
                alert('Error adding alias: ' + (error.error || 'Unknown error'));
            }
        } catch (error) {
            alert('Error adding alias: ' + error.message);
        }
    };

    window.handleDeleteAlias = async (kwId, aliasId) => {
        const kw = aliasState.keywords.find(k => k.id === kwId);
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

    window.handleDeleteKeyword = async (id) => {
        const kw = aliasState.keywords.find(k => k.id === id);
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
            aliasState.keywords = aliasState.keywords.filter(k => k.id !== id);
            aliasState.expandedKeywords.delete(id);
            renderAliases();
            
            // Reload from server to ensure sync
            await loadAliases();
        } catch (error) {
            alert('Error deleting keyword: ' + error.message);
        }
    };

    function handleConfirmAddKeyword() {
        const nameInput = document.getElementById('new-alias-keyword-name');
        const name = nameInput.value.trim();
        const lang = document.querySelector('.lang-select-btn.active').dataset.lang;
        
        if (!name) return;
        
        if (aliasState.keywords.some(k => k.name.toLowerCase() === name.toLowerCase())) {
            alert("Keyword already exists");
            return;
        }

        aliasState.keywords.push({
            id: `keyword-${Date.now()}`,
            name: name,
            language: lang,
            aliases: [],
            createdAt: new Date().toISOString()
        });
        
        saveAliases();
        renderAliases();
        addAliasKeywordDialog.classList.add('hidden');
        nameInput.value = "";
    }
});


