// Document Explainer functionality - Keyword Finder tab

document.addEventListener('DOMContentLoaded', function () {
    // Early exit if not on the Keyword Finder page
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
    const languageToggle = document.getElementById('language-toggle');

    // State management (replaces Gradio State)
    let storedResults = []; // Replaces explainer_search_results_store
    let lastSearchKeyword = null; // Replaces last_search_keyword
    let deepSearchContext = null; // Track deep search: { originalKeyword, selectedKeyword }
    let selectedLanguage = 'en'; // Language preference: 'en' or 'vn'

    // Hierarchical view state
    let expandedDocs = new Set(); // Track which documents are expanded
    let activePreviewId = null; // Track which section is being previewed
    let groupedResults = {}; // { docName: [{ choice, storeItem, index }] }

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
    explainerKeyword.addEventListener('keypress', function (e) {
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
        // Trigger 1-second animation
        openAliasesBtn.classList.add('animating');
        setTimeout(() => openAliasesBtn.classList.remove('animating'), 1000);

        aliasesDrawer.classList.add('open');
        loadAliases();
    });
    if (closeAliasesBtn) closeAliasesBtn.addEventListener('click', () => aliasesDrawer.classList.remove('open'));

    // Prevent clicks inside the drawer from propagating (e.g., collapsing sidebar)
    if (aliasesDrawer) {
        aliasesDrawer.addEventListener('click', (e) => {
            e.stopPropagation();
        });
    }

    // Close drawer when clicking outside
    document.addEventListener('click', (e) => {
        // Only attempt to close if drawer is open
        if (aliasesDrawer && aliasesDrawer.classList.contains('open')) {
            // "Outside" means not in the drawer, not on the button, and not in the modal
            const isInsideDrawer = aliasesDrawer.contains(e.target);
            const isButton = openAliasesBtn && openAliasesBtn.contains(e.target);
            const isModal = addAliasKeywordDialog && addAliasKeywordDialog.contains(e.target);

            if (!isInsideDrawer && !isButton && !isModal) {
                aliasesDrawer.classList.remove('open');
            }
        }
    });

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

    // Language toggle handler
    if (languageToggle) {
        languageToggle.addEventListener('change', function () {
            selectedLanguage = this.checked ? 'vn' : 'en';
            // Store in sessionStorage for persistence
            sessionStorage.setItem('explainer_language', selectedLanguage);
        });

        // Load saved language preference
        const savedLanguage = sessionStorage.getItem('explainer_language');
        if (savedLanguage) {
            selectedLanguage = savedLanguage;
            languageToggle.checked = savedLanguage === 'vn';
        }
    }

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

    // Helper function to display progress messages sequentially
    function displayProgressMessages(messages, container) {
        if (!messages || messages.length === 0) return;

        // Show the last progress message with spinner and animation
        const lastMessage = messages[messages.length - 1];
        container.innerHTML = `<div class="progress-message" style="display:flex;align-items:center;gap:8px;"><div class="spinner" style="width:14px;height:14px;"></div> <span>${lastMessage}</span></div>`;
    }

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
                searchKeywords.push(foundAliasKW.name);
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

            // Display progress messages if available
            if (deepResult.progress_messages && deepResult.progress_messages.length > 0) {
                displayProgressMessages(deepResult.progress_messages, resultsCount);
            }


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

            const closeModal = (result) => {
                document.body.removeChild(modal);
                document.head.removeChild(style);
                resolve(result);
            };

            modal.querySelectorAll('.keyword-option-btn').forEach(btn => {
                btn.addEventListener('click', () => {
                    closeModal(btn.dataset.keyword);
                });
            });

            modal.querySelector('.cancel-btn').addEventListener('click', () => {
                closeModal(null);
            });

            // Close on backdrop click
            modal.addEventListener('click', (e) => {
                if (e.target === modal) {
                    closeModal(null);
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
                // Use parent keyword's language instead of detecting from alias name
                // Find the selected keyword in the keywords list to get its language
                let language = 'en'; // default
                const selectedKw = aliasState.keywords.find(k => k.name.toLowerCase() === selectedKeyword.toLowerCase());
                if (selectedKw && selectedKw.language) {
                    const kwLang = selectedKw.language.toUpperCase();
                    if (kwLang === 'VN' || kwLang === 'VI') {
                        language = 'vi';
                    } else if (kwLang === 'EN') {
                        language = 'en';
                    }
                }

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
        groupedResults = {};

        if (!choices || choices.length === 0) {
            expandedDocs.clear();
            activePreviewId = null;
            closePreviewPanel();
            return;
        }

        // Group choices by document name
        // Choice format from API: "DocName → SectionHeading"
        choices.forEach((choice, index) => {
            const storeItem = storedResults[index];

            // Parse choice string: "DocName → SectionHeading"
            const parts = choice.split(' → ');
            const docName = parts[0] || 'Unknown Document';
            const sectionTitle = parts.length > 1 ? parts.slice(1).join(' → ') : choice;

            if (!groupedResults[docName]) {
                groupedResults[docName] = [];
            }
            groupedResults[docName].push({
                choice: choice,
                storeItem: storeItem,
                index: index,
                sectionTitle: sectionTitle
            });
        });

        // Render hierarchical structure
        Object.keys(groupedResults).forEach(docName => {
            const sections = groupedResults[docName];

            // Sort sections by chunk_id with natural/numeric sorting
            sections.sort((sectionA, sectionB) => {
                const chunkIdA = sectionA.storeItem?.chunk_id || '';
                const chunkIdB = sectionB.storeItem?.chunk_id || '';
                return chunkIdA.localeCompare(chunkIdB, undefined, { numeric: true, sensitivity: 'base' });
            });

            const docId = `doc-${hashString(docName)}`;

            // Document row
            const docRow = document.createElement('div');
            docRow.className = 'doc-row';
            docRow.dataset.docId = docId;

            // Document header
            const docHeader = document.createElement('div');
            docHeader.className = 'doc-row-header';

            // Chevron
            const chevron = document.createElement('img');
            chevron.src = '/static/icons/chevron-right.svg';
            chevron.className = `doc-row-chevron ${expandedDocs.has(docId) ? 'expanded' : ''}`;
            chevron.onclick = (e) => {
                e.stopPropagation();
                toggleDocExpanded(docId);
            };

            // Document checkbox
            const docCheckbox = document.createElement('input');
            docCheckbox.type = 'checkbox';
            docCheckbox.className = 'doc-row-checkbox';
            docCheckbox.id = `doc-checkbox-${docId}`;
            docCheckbox.onclick = (e) => {
                e.stopPropagation();
                toggleDocumentSelection(docId, docCheckbox.checked);
            };

            // File icon
            const fileIcon = document.createElement('img');
            fileIcon.src = '/static/icons/file.svg';
            fileIcon.className = 'doc-row-icon';

            // Document name
            const docNameSpan = document.createElement('span');
            docNameSpan.className = 'doc-row-name';
            docNameSpan.textContent = formatDocName(docName);
            docNameSpan.title = docName;

            // Selection count
            const countSpan = document.createElement('span');
            countSpan.className = 'doc-row-count';
            countSpan.id = `doc-count-${docId}`;
            countSpan.textContent = `(0/${sections.length})`;

            docHeader.appendChild(chevron);
            docHeader.appendChild(docCheckbox);
            docHeader.appendChild(fileIcon);
            docHeader.appendChild(docNameSpan);
            docHeader.appendChild(countSpan);

            // Click on header row to toggle expand
            docHeader.onclick = () => toggleDocExpanded(docId);

            docRow.appendChild(docHeader);

            // Sections container
            const sectionsContainer = document.createElement('div');
            sectionsContainer.className = `doc-sections ${expandedDocs.has(docId) ? 'expanded' : ''}`;
            sectionsContainer.id = `sections-${docId}`;

            sections.forEach((item, sectionIdx) => {
                const sectionId = `section-${item.index}`;

                const sectionRow = document.createElement('div');
                sectionRow.className = 'section-row';
                sectionRow.dataset.sectionId = sectionId;
                sectionRow.dataset.docId = docId;
                sectionRow.dataset.index = item.index;

                if (activePreviewId === sectionId) {
                    sectionRow.classList.add('preview-active');
                }

                // Section checkbox
                const sectionCheckbox = document.createElement('input');
                sectionCheckbox.type = 'checkbox';
                sectionCheckbox.className = 'section-row-checkbox';
                sectionCheckbox.id = `checkbox-${item.index}`;
                sectionCheckbox.value = item.choice;
                sectionCheckbox.name = 'explainer-choice';
                sectionCheckbox.onclick = (e) => {
                    e.stopPropagation();
                    updateSectionSelection(sectionRow, sectionCheckbox.checked);
                    updateDocCheckboxState(docId);
                    updateGenerateButtonState();
                    updateSelectAllNoneState();
                };

                // Section title
                const sectionTitle = document.createElement('span');
                sectionTitle.className = 'section-row-title';
                sectionTitle.textContent = item.sectionTitle;
                sectionTitle.title = item.choice;

                // Preview button
                const previewBtn = document.createElement('button');
                previewBtn.className = `preview-btn ${activePreviewId === sectionId ? 'active' : ''}`;
                previewBtn.innerHTML = `
                    <img src="/static/icons/eye.svg" width="12" height="12">
                    <span>Preview</span>
                `;
                previewBtn.onclick = (e) => {
                    e.stopPropagation();
                    // Get doc_id and section_heading from store item
                    const previewDocName = item.storeItem?.doc_name || docName;
                    const docId = item.storeItem?.doc_id || '';
                    const sectionHeading = item.storeItem?.section_heading || item.sectionTitle;
                    const previewContent = item.storeItem?.content || ''; // Fallback, but won't be used
                    togglePreview(sectionId, previewDocName, item.sectionTitle, previewContent, docId, sectionHeading);
                };

                sectionRow.appendChild(sectionCheckbox);
                sectionRow.appendChild(sectionTitle);
                sectionRow.appendChild(previewBtn);

                // Click on row to toggle checkbox
                sectionRow.onclick = () => {
                    sectionCheckbox.checked = !sectionCheckbox.checked;
                    updateSectionSelection(sectionRow, sectionCheckbox.checked);
                    updateDocCheckboxState(docId);
                    updateGenerateButtonState();
                    updateSelectAllNoneState();
                };

                sectionsContainer.appendChild(sectionRow);
            });

            docRow.appendChild(sectionsContainer);
            explainerResultsCheckboxes.appendChild(docRow);
        });

        // Reset select all/none checkboxes
        selectAllCheckbox.checked = false;
        selectNoneCheckbox.checked = false;
    }

    // Helper functions for hierarchical view
    function hashString(str) {
        let hash = 0;
        for (let i = 0; i < str.length; i++) {
            const char = str.charCodeAt(i);
            hash = ((hash << 5) - hash) + char;
            hash = hash & hash;
        }
        return Math.abs(hash).toString(36);
    }

    function formatDocName(docName) {
        // Truncate long document names for display
        if (docName.length > 40) {
            return docName.substring(0, 37) + '...';
        }
        return docName;
    }

    function toggleDocExpanded(docId) {
        if (expandedDocs.has(docId)) {
            expandedDocs.delete(docId);
        } else {
            expandedDocs.add(docId);
        }

        const sectionsContainer = document.getElementById(`sections-${docId}`);
        const chevron = document.querySelector(`[data-doc-id="${docId}"] .doc-row-chevron`);

        if (sectionsContainer) {
            sectionsContainer.classList.toggle('expanded', expandedDocs.has(docId));
        }
        if (chevron) {
            chevron.classList.toggle('expanded', expandedDocs.has(docId));
        }
    }

    function toggleDocumentSelection(docId, selected) {
        const sectionsContainer = document.getElementById(`sections-${docId}`);
        if (!sectionsContainer) return;

        const sectionRows = sectionsContainer.querySelectorAll('.section-row');
        sectionRows.forEach(row => {
            const checkbox = row.querySelector('.section-row-checkbox');
            if (checkbox) {
                checkbox.checked = selected;
                updateSectionSelection(row, selected);
            }
        });

        updateDocCheckboxState(docId);
        updateGenerateButtonState();
        updateSelectAllNoneState();
    }

    function updateSectionSelection(row, selected) {
        if (selected) {
            row.classList.add('selected');
        } else {
            row.classList.remove('selected');
        }
    }

    function updateDocCheckboxState(docId) {
        const docCheckbox = document.getElementById(`doc-checkbox-${docId}`);
        const countSpan = document.getElementById(`doc-count-${docId}`);
        const sectionsContainer = document.getElementById(`sections-${docId}`);

        if (!sectionsContainer || !docCheckbox) return;

        const checkboxes = sectionsContainer.querySelectorAll('.section-row-checkbox');
        const checkedCount = sectionsContainer.querySelectorAll('.section-row-checkbox:checked').length;
        const totalCount = checkboxes.length;

        // Update count display
        if (countSpan) {
            countSpan.textContent = `(${checkedCount}/${totalCount})`;
        }

        // Update document checkbox state
        if (checkedCount === 0) {
            docCheckbox.checked = false;
            docCheckbox.indeterminate = false;
            docCheckbox.classList.remove('partial');
        } else if (checkedCount === totalCount) {
            docCheckbox.checked = true;
            docCheckbox.indeterminate = false;
            docCheckbox.classList.remove('partial');
        } else {
            docCheckbox.checked = false;
            docCheckbox.indeterminate = true;
            docCheckbox.classList.add('partial');
        }
    }

    // Preview functions
    async function togglePreview(sectionId, docName, sectionTitle, content, docId, sectionHeading) {
        const previewPanel = document.getElementById('section-preview-panel');
        const explainerRight = document.querySelector('.explainer-right');
        const previewContent = document.getElementById('preview-content');

        if (activePreviewId === sectionId) {
            // Close preview
            closePreviewPanel();
        } else {
            // Open/switch preview
            activePreviewId = sectionId;

            // Update preview panel header
            document.getElementById('preview-doc-name').textContent = docName;
            document.getElementById('preview-section-title').textContent = sectionTitle;

            // Show loading state (matching v0 style)
            previewContent.innerHTML = `
                <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 32px; gap: 12px;">
                    <div class="spinner" style="width: 24px; height: 24px; border: 2px solid var(--border); border-top-color: var(--primary); border-radius: 50%; animation: spin 0.8s linear infinite;"></div>
                    <p style="font-size: 0.875rem; color: var(--muted-foreground); margin: 0;">Generating summary...</p>
                </div>
            `;

            // Show panel
            previewPanel.classList.remove('hidden');
            explainerRight.classList.add('preview-open');

            // Update active state in sidebar
            updatePreviewActiveState();

            // Fetch LLM summary
            try {
                const response = await fetch('/api/gdd/explainer/preview', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        doc_id: docId,
                        section_heading: sectionHeading,
                        doc_name: docName,
                        language: selectedLanguage
                    })
                });

                const result = await response.json();

                if (result.success && result.summary) {
                    // Format and display the summary (similar to chatbox response)
                    previewContent.innerHTML = formatPreviewContent(result.summary);
                } else {
                    previewContent.innerHTML = `<p class="placeholder-text" style="color: var(--status-error);">Error: ${result.error || 'Failed to generate summary'}</p>`;
                }
            } catch (error) {
                console.error('Error fetching preview:', error);
                previewContent.innerHTML = `<p class="placeholder-text" style="color: var(--status-error);">Error: ${error.message}</p>`;
            }
        }
    }

    function closePreviewPanel() {
        const previewPanel = document.getElementById('section-preview-panel');
        const explainerRight = document.querySelector('.explainer-right');

        activePreviewId = null;

        if (previewPanel) {
            previewPanel.classList.add('hidden');
        }
        if (explainerRight) {
            explainerRight.classList.remove('preview-open');
        }

        updatePreviewActiveState();
    }

    function updatePreviewActiveState() {
        // Remove active state from all sections and preview buttons
        document.querySelectorAll('.section-row').forEach(row => {
            row.classList.remove('preview-active');
            const btn = row.querySelector('.preview-btn');
            if (btn) btn.classList.remove('active');
        });

        // Add active state to current preview section
        if (activePreviewId) {
            const activeRow = document.querySelector(`[data-section-id="${activePreviewId}"]`);
            if (activeRow) {
                activeRow.classList.add('preview-active');
                const btn = activeRow.querySelector('.preview-btn');
                if (btn) btn.classList.add('active');
            }
        }
    }

    function formatPreviewContent(content) {
        if (!content) return '<p class="placeholder-text">No content available.</p>';

        // Format markdown-like content (similar to chatbox response)
        let html = escapeHtml(content);

        // Convert markdown bold (**text**)
        html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');

        // Convert headers
        html = html.replace(/^### (.*$)/gim, '<h3>$1</h3>');
        html = html.replace(/^## (.*$)/gim, '<h2>$1</h2>');
        html = html.replace(/^# (.*$)/gim, '<h1>$1</h1>');

        // Convert line breaks to paragraphs
        const paragraphs = html.split(/\n\n+/).filter(p => p.trim());
        if (paragraphs.length === 0) {
            return `<p>${html}</p>`;
        }

        // Wrap each paragraph, but preserve headers
        return paragraphs.map(p => {
            const trimmed = p.trim();
            if (trimmed.startsWith('<h')) {
                return trimmed;
            }
            return `<p>${trimmed}</p>`;
        }).join('');
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // Initialize close preview button
    const closePreviewBtn = document.getElementById('close-preview-btn');
    if (closePreviewBtn) {
        closePreviewBtn.addEventListener('click', closePreviewPanel);
    }

    function handleSelectAll() {
        if (selectAllCheckbox.checked) {
            selectNoneCheckbox.checked = false;

            // Select all sections in all documents
            const sectionRows = explainerResultsCheckboxes.querySelectorAll('.section-row');
            sectionRows.forEach(row => {
                const checkbox = row.querySelector('.section-row-checkbox');
                if (checkbox) {
                    checkbox.checked = true;
                    updateSectionSelection(row, true);
                }
            });

            // Update all document checkboxes
            Object.keys(groupedResults).forEach(docName => {
                const docId = `doc-${hashString(docName)}`;
                updateDocCheckboxState(docId);
            });

            updateGenerateButtonState();
        }
    }

    function handleSelectNone() {
        if (selectNoneCheckbox.checked) {
            selectAllCheckbox.checked = false;

            // Deselect all sections in all documents
            const sectionRows = explainerResultsCheckboxes.querySelectorAll('.section-row');
            sectionRows.forEach(row => {
                const checkbox = row.querySelector('.section-row-checkbox');
                if (checkbox) {
                    checkbox.checked = false;
                    updateSectionSelection(row, false);
                }
            });

            // Update all document checkboxes
            Object.keys(groupedResults).forEach(docName => {
                const docId = `doc-${hashString(docName)}`;
                updateDocCheckboxState(docId);
            });

            updateGenerateButtonState();
        }
    }

    function getSelectedChoices() {
        const checkboxes = explainerResultsCheckboxes.querySelectorAll('.section-row-checkbox:checked');
        return Array.from(checkboxes).map(cb => cb.value);
    }

    async function generateExplanation() {
        const keyword = explainerKeyword.value.trim();
        const selectedChoices = getSelectedChoices();
        const genStatus = document.getElementById('gen-status');

        try {
            explainBtn.disabled = true;
            genStatus.innerHTML = '<div style="display:flex;align-items:center;gap:8px;color:var(--status-info)"><div class="spinner" style="width:12px;height:12px;"></div> Thinking...</div>';
            // Restore flex centering for placeholder state
            explanationOutput.style.display = 'flex';
            explanationOutput.style.alignItems = 'center';
            explanationOutput.style.justifyContent = 'center';
            explanationOutput.innerHTML = `
                <div class="explainer-skeleton">
                    <div class="wrapper">
                        <div class="circle"></div>
                        <div class="line-1"></div>
                        <div class="line-2"></div>
                        <div class="line-3"></div>
                        <div class="line-4"></div>
                    </div>
                </div>
            `;

            // Resolve alias to parent keyword for explanation generation
            // This ensures we use the actual keyword that exists in documents, not the alias
            let explanationKeyword = keyword;
            await loadAliases(); // Ensure aliases are loaded

            const foundAliasKW = aliasState.keywords.find(kw =>
                kw.aliases.some(a => a.name.toLowerCase() === keyword.toLowerCase())
            );

            if (foundAliasKW) {
                explanationKeyword = foundAliasKW.name;
            }

            const response = await fetch('/api/gdd/explainer/explain', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    keyword: explanationKeyword,
                    selected_choices: selectedChoices,
                    stored_results: storedResults,
                    language: selectedLanguage
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

            // Build timing breakdown if available
            let timingHTML = '';
            if (result.timing_metadata) {
                timingHTML = buildTimingBreakdown(result.timing_metadata);
            }

            explanationOutput.innerHTML = timingHTML + `<div class="generated-explanation" style="color: var(--foreground)">${renderMarkdown(result.explanation || '', 'Explanation', keyword)}</div>`;

            // Add toggle functionality for timing breakdown
            if (result.timing_metadata) {
                const toggleBtn = explanationOutput.querySelector('.timing-toggle');
                const timingContent = explanationOutput.querySelector('.timing-content');
                if (toggleBtn && timingContent) {
                    toggleBtn.addEventListener('click', () => {
                        const isHidden = timingContent.style.display === 'none';
                        timingContent.style.display = isHidden ? 'block' : 'none';
                        toggleBtn.textContent = isHidden
                            ? `⏱️ Hide Timing Details (Total: ${result.timing_metadata.total_time}s)`
                            : `⏱️ Show Timing Details (Total: ${result.timing_metadata.total_time}s)`;
                    });
                }
            }

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
        const checkboxes = explainerResultsCheckboxes.querySelectorAll('.section-row-checkbox');
        const checkedCount = explainerResultsCheckboxes.querySelectorAll('.section-row-checkbox:checked').length;
        const totalCount = checkboxes.length;

        // Update sticky badge
        const badge = document.getElementById('selected-count-badge');
        if (badge) badge.textContent = checkedCount;

        if (checkedCount === 0) {
            selectAllCheckbox.checked = false;
            selectNoneCheckbox.checked = true;
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

    function buildTimingBreakdown(timingMetadata) {
        if (!timingMetadata) return '';

        const validationTime = timingMetadata.validation_time || 0;
        const hydeTime = timingMetadata.hyde_expansion_time || 0;
        const sectionTimings = timingMetadata.section_timings || [];
        const formattingTime = timingMetadata.formatting_time || 0;
        const totalTime = timingMetadata.total_time || 0;

        let html = `
            <div class="timing-breakdown">
                <button class="timing-toggle" type="button">
                    ⏱️ Show Timing Details (Total: ${totalTime}s)
                </button>
                <div class="timing-content" style="display: none;">
                    <div class="timing-row">
                        <span class="timing-label">Validation</span>
                        <span class="timing-value">${validationTime}s</span>
                    </div>
                    <div class="timing-row">
                        <span class="timing-label">HYDE Expansion</span>
                        <span class="timing-value">${hydeTime}s</span>
                    </div>`;

        if (sectionTimings.length > 0) {
            html += `<div class="timing-section-header">LLM Calls (by Section):</div>`;
            sectionTimings.forEach(section => {
                html += `
                    <div class="timing-row timing-section">
                        <span class="timing-label">${section.label}</span>
                        <span class="timing-value">${section.time}s</span>
                    </div>`;
            });
        }

        html += `
                    <div class="timing-row">
                        <span class="timing-label">Formatting</span>
                        <span class="timing-value">${formattingTime}s</span>
                    </div>
                    <div class="timing-row timing-total">
                        <span class="timing-label">Total</span>
                        <span class="timing-value">${totalTime}s</span>
                    </div>
                </div>
            </div>
        `;

        return html;
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
            // Use parent keyword's language instead of detecting from alias name
            // Map keyword language codes to API language codes
            let language = 'en'; // default
            if (kw.language) {
                const kwLang = kw.language.toUpperCase();
                if (kwLang === 'VN' || kwLang === 'VI') {
                    language = 'vi';
                } else if (kwLang === 'EN') {
                    language = 'en';
                }
            }

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
        const langRadio = document.querySelector('input[name="new-alias-keyword-lang"]:checked');
        const lang = langRadio ? langRadio.value : 'EN';

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
    // Sidebar Horizontal Resize Functionality
    const sidebar = document.querySelector('.explainer-left');
    const sidebarResizeHandle = document.getElementById('sidebar-resize-handle');

    if (sidebar && sidebarResizeHandle) {
        let isResizing = false;
        let startX = 0;
        let startWidth = 0;
        const minWidth = 400; // Current size is minimum
        const maxWidth = 800;

        sidebarResizeHandle.addEventListener('mousedown', (e) => {
            isResizing = true;
            startX = e.clientX;
            startWidth = sidebar.offsetWidth;
            sidebarResizeHandle.classList.add('resizing');
            document.body.style.cursor = 'col-resize';
            document.body.style.userSelect = 'none';
            e.preventDefault();
        });

        document.addEventListener('mousemove', (e) => {
            if (!isResizing) return;

            const delta = e.clientX - startX;
            let newWidth = startWidth + delta;

            // Constrain to min/max width
            newWidth = Math.max(minWidth, Math.min(maxWidth, newWidth));

            sidebar.style.width = `${newWidth}px`;
        });

        document.addEventListener('mouseup', () => {
            if (isResizing) {
                isResizing = false;
                sidebarResizeHandle.classList.remove('resizing');
                document.body.style.cursor = '';
                document.body.style.userSelect = '';

                // Save the width to sessionStorage
                sessionStorage.setItem('explainer_sidebar_width', sidebar.offsetWidth);
            }
        });

        // Load saved width on page load
        const savedWidth = sessionStorage.getItem('explainer_sidebar_width');
        if (savedWidth) {
            const width = parseInt(savedWidth, 10);
            if (width >= minWidth && width <= maxWidth) {
                sidebar.style.width = `${width}px`;
            }
        }
    }

    // Preview Panel Vertical Resize Functionality
    const previewPanel = document.getElementById('section-preview-panel');
    const previewResizeHandle = document.getElementById('preview-resize-handle');

    if (previewPanel && previewResizeHandle) {
        let isResizingPreview = false;
        let startY = 0;
        let startHeight = 0;
        const minHeight = 300; // Current size is minimum (uppermost boundary)
        const maxHeight = window.innerHeight * 0.8; // 80vh

        previewResizeHandle.addEventListener('mousedown', (e) => {
            isResizingPreview = true;
            startY = e.clientY;
            startHeight = previewPanel.offsetHeight;
            previewResizeHandle.classList.add('resizing');
            document.body.style.cursor = 'row-resize';
            document.body.style.userSelect = 'none';
            e.preventDefault();
        });

        document.addEventListener('mousemove', (e) => {
            if (!isResizingPreview) return;

            const delta = e.clientY - startY;
            let newHeight = startHeight + delta;

            // Constrain to min/max height
            newHeight = Math.max(minHeight, Math.min(maxHeight, newHeight));

            previewPanel.style.height = `${newHeight}px`;
        });

        document.addEventListener('mouseup', () => {
            if (isResizingPreview) {
                isResizingPreview = false;
                previewResizeHandle.classList.remove('resizing');
                document.body.style.cursor = '';
                document.body.style.userSelect = '';

                // Save the height to sessionStorage
                sessionStorage.setItem('explainer_preview_height', previewPanel.offsetHeight);
            }
        });

        // Load saved height on page load
        const savedHeight = sessionStorage.getItem('explainer_preview_height');
        if (savedHeight) {
            const height = parseInt(savedHeight, 10);
            if (height >= minHeight && height <= maxHeight) {
                previewPanel.style.height = `${height}px`;
            }
        }
    }
});


