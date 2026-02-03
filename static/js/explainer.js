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
    const queryCheckboxEn = document.getElementById('query-checkbox-en');
    const queryCheckboxVn = document.getElementById('query-checkbox-vn');
    const queryLabelEn = document.getElementById('query-label-en');
    const queryLabelVn = document.getElementById('query-label-vn');
    const queryFilterContainer = document.getElementById('query-filter-container');
    const explainBtn = document.getElementById('explain-btn');
    const explanationOutput = document.getElementById('explanation-output');
    const languageToggle = document.getElementById('language-toggle');

    // State management (replaces Gradio State)
    let storedResults = []; // Replaces explainer_search_results_store
    let lastSearchKeyword = null; // Replaces last_search_keyword
    let deepSearchContext = null; // Track deep search: { originalKeyword, selectedKeyword }
    let selectedLanguage = 'en'; // Language preference: 'en' or 'vn'
    let translationInfo = null; // Store translation info from search: { original, translation }
    let currentCitations = {}; // Store citations map from explanation response: { citation_number: { doc_id, doc_name, section_heading, chunk_id } }
    let generationInProgress = false; // Track if explanation generation is in progress
    let previewLoadingInProgress = false; // Track if preview is being loaded

    // Hierarchical view state
    let expandedDocs = new Set(); // Track which documents are expanded
    let activePreviewId = null; // Track which section is being previewed
    let activePreviewDocIds = {}; // Map sectionId -> docId for all active previews (supports multiple docs)
    let groupedResults = {}; // { docName: [{ choice, storeItem, index }] }

    // View Images sidebar (right sidebar, toggled by "View Images" button)
    let previewImageUrls = []; // Image URLs from current chunk content
    let imageSidebarOpen = false;
    let currentImageIndex = 0;
    let isJumping = false;

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

    // Query filter event listeners
    if (queryCheckboxEn) {
        queryCheckboxEn.addEventListener('change', applyQueryFilter);
    }
    if (queryCheckboxVn) {
        queryCheckboxVn.addEventListener('change', applyQueryFilter);
    }

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
        // Check if drawer is already open - toggle it
        const isOpen = aliasesDrawer && aliasesDrawer.classList.contains('open');

        if (isOpen) {
            // Close the drawer
            aliasesDrawer.classList.remove('open');
            saveExplainerState(); // Save state when drawer closes
        } else {
            // Open the drawer
            openAliasesBtn.classList.add('animating');
            setTimeout(() => openAliasesBtn.classList.remove('animating'), ANIMATION_DURATION);

            aliasesDrawer.classList.add('open');
            loadAliases();
            saveExplainerState(); // Save state when drawer opens
        }
    });
    if (closeAliasesBtn) closeAliasesBtn.addEventListener('click', () => {
        aliasesDrawer.classList.remove('open');
        saveExplainerState(); // Save state when drawer closes
    });

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
                saveExplainerState(); // Save state when drawer closes
            }
        }

        // Close View Images sidebar when clicking outside (sidebar, View Images button, or expanded modal)
        const imagesSidebar = document.getElementById('preview-images-sidebar');
        const viewImagesBtn = document.getElementById('view-images-btn');
        const expandedModal = document.getElementById('preview-image-expanded-modal');
        if (imagesSidebar && imagesSidebar.classList.contains('open')) {
            const isInsideSidebar = imagesSidebar.contains(e.target);
            const isViewImagesButton = viewImagesBtn && viewImagesBtn.contains(e.target);
            const clickedExpandedModalOrInside = expandedModal && expandedModal.contains(e.target);
            const expandedModalVisible = expandedModal && !expandedModal.classList.contains('hidden');
            // Don't close if click was in sidebar, on button, in modal, or when expanded image is open (thumbnail click replaces DOM so target can be detached)
            if (!isInsideSidebar && !isViewImagesButton && !clickedExpandedModalOrInside && !expandedModalVisible) {
                closeImageSidebar();
            }
        }

        // Close all metadata chat bubbles when clicking outside
        const openBubbles = document.querySelectorAll('.metadata-chat-bubble[style*="flex"]');
        if (openBubbles.length > 0) {
            const clickedBubble = Array.from(openBubbles).find(bubble => bubble.contains(e.target));
            const clickedVersionBubble = e.target.closest('[data-version-bubble]');

            // Close if click is outside any bubble and not on a version bubble
            if (!clickedBubble && !clickedVersionBubble) {
                openBubbles.forEach(bubble => {
                    bubble.style.display = 'none';
                });
            }
        }
    });

    if (aliasSearchInput) aliasSearchInput.addEventListener('input', (e) => {
        aliasState.searchQuery = e.target.value;
        renderAliases();
    });
    if (aliasAddKeywordBtn) aliasAddKeywordBtn.addEventListener('click', () => {
        addAliasKeywordDialog.classList.remove('hidden');
        const newKeywordInput = getElement('new-alias-keyword-name');
        if (newKeywordInput) newKeywordInput.focus();
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
            // Save state after language toggle changes
            saveExplainerState();
        });

        // Sync selectedLanguage with checkbox's current state on initialization
        // This ensures the visual state matches the actual value used for generation
        selectedLanguage = languageToggle.checked ? 'vn' : 'en';
    }

    // Flag to prevent saving during restore
    let isRestoring = false;

    // Constants
    const STORAGE_KEY = 'explainer_state';
    const RESTORE_DELAY_SHORT = 50;
    const RESTORE_DELAY_MEDIUM = 150;
    const RESTORE_DELAY_LONG = 250;
    const ANIMATION_DURATION = 1000;

    // Helper: Get DOM element safely
    function getElement(id) {
        return document.getElementById(id);
    }

    // State persistence functions
    function saveExplainerState() {
        if (isRestoring) {
            return;
        }
        try {
            const selectedChoices = getSelectedChoices();
            const previewPanel = getElement('section-preview-panel');
            const previewContent = getElement('preview-content');
            const previewDocName = getElement('preview-doc-name');
            const previewSectionTitle = getElement('preview-section-title');
            const documentViewerSidebar = getElement('document-viewer-sidebar');
            const documentViewerContent = getElement('document-viewer-content');
            const documentViewerDocName = getElement('document-viewer-doc-name');

            const state = {
                keyword: explainerKeyword.value,
                storedResults: storedResults,
                lastSearchKeyword: lastSearchKeyword,
                selectedLanguage: selectedLanguage,
                translationInfo: translationInfo,
                expandedDocs: Array.from(expandedDocs),
                activePreviewId: activePreviewId,
                activePreviewDocIds: activePreviewDocIds,
                queryCheckboxEn: queryCheckboxEn ? queryCheckboxEn.checked : true,
                queryCheckboxVn: queryCheckboxVn ? queryCheckboxVn.checked : false,
                explanationOutput: explanationOutput ? explanationOutput.innerHTML : '',
                currentCitations: currentCitations,
                selectedChoices: selectedChoices,
                aliasesDrawerOpen: aliasesDrawer ? aliasesDrawer.classList.contains('open') : false,
                previewPanelOpen: previewPanel ? !previewPanel.classList.contains('hidden') : false,
                previewContent: previewContent ? previewContent.innerHTML : '',
                previewDocName: previewDocName ? previewDocName.textContent : '',
                previewSectionTitle: previewSectionTitle ? previewSectionTitle.textContent : '',
                generationInProgress: generationInProgress,
                previewLoadingInProgress: previewLoadingInProgress,
                documentViewerOpen: documentViewerSidebar ? documentViewerSidebar.style.transform === 'translateX(0)' : false,
                documentViewerContent: documentViewerContent ? documentViewerContent.innerHTML : '',
                documentViewerDocName: documentViewerDocName ? documentViewerDocName.textContent : ''
            };

            const stateJson = JSON.stringify(state);
            localStorage.setItem(STORAGE_KEY, stateJson);

            // Verify save succeeded
            const verify = localStorage.getItem(STORAGE_KEY);
            if (verify !== stateJson) {
                console.error('[Explainer] State verification failed - saved state does not match');
            }
        } catch (e) {
            console.error('[Explainer] Error saving state:', e);
        }
    }

    function restoreExplainerState() {
        isRestoring = true;
        try {
            const savedState = localStorage.getItem(STORAGE_KEY);
            if (!savedState) {
                isRestoring = false;
                return false;
            }

            const state = JSON.parse(savedState);

            // Restore basic state
            if (state.keyword) {
                explainerKeyword.value = state.keyword;
            }
            if (state.storedResults) {
                storedResults = state.storedResults;
            }
            if (state.lastSearchKeyword) {
                lastSearchKeyword = state.lastSearchKeyword;
            }
            if (state.selectedLanguage) {
                selectedLanguage = state.selectedLanguage;
            }
            if (state.translationInfo) {
                translationInfo = state.translationInfo;
            }
            if (state.expandedDocs) {
                expandedDocs = new Set(state.expandedDocs);
            }
            if (state.activePreviewId) {
                activePreviewId = state.activePreviewId;
            }
            if (state.activePreviewDocIds) {
                activePreviewDocIds = state.activePreviewDocIds;
            }
            if (state.currentCitations) {
                currentCitations = state.currentCitations;
            }
            if (state.generationInProgress !== undefined) {
                generationInProgress = state.generationInProgress;
            }
            if (state.previewLoadingInProgress !== undefined) {
                previewLoadingInProgress = state.previewLoadingInProgress;
            }

            // Restore language toggle
            if (languageToggle) {
                languageToggle.checked = selectedLanguage === 'vn';
            }

            // Restore filter checkboxes
            if (queryCheckboxEn && state.queryCheckboxEn !== undefined) {
                queryCheckboxEn.checked = state.queryCheckboxEn;
            }
            if (queryCheckboxVn && state.queryCheckboxVn !== undefined) {
                queryCheckboxVn.checked = state.queryCheckboxVn;
            }

            // Always show results container if we have a keyword or stored results
            if (state.keyword || (storedResults && storedResults.length > 0)) {
                explainerResultsContainer.style.display = 'flex';
                const emptyLeft = getElement('explainer-empty-left');
                if (emptyLeft) {
                    emptyLeft.style.display = 'none';
                }
            }

            // Restore UI if we have stored results
            if (storedResults && storedResults.length > 0) {
                // Convert storedResults back to choice labels (format: "docName → section")
                const choiceLabels = storedResults.map(item => {
                    if (typeof item === 'string') return item;
                    const displayName = item?.doc_name || 'Unknown Document';
                    const sectionDisplay = item?.section_heading || "(No section)";
                    return `${displayName} → ${sectionDisplay}`;
                }).filter(label => label && typeof label === 'string');

                // Wait for DOM to be ready before rendering
                setTimeout(() => {
                    try {
                        if (explainerResultsCheckboxes) {
                            renderCheckboxes(choiceLabels);
                            setTimeout(() => {
                                applyQueryFilter();
                            }, RESTORE_DELAY_SHORT);
                        } else {
                            isRestoring = false;
                        }
                    } catch (e) {
                        console.error('[Explainer] Error during restore renderCheckboxes:', e);
                        isRestoring = false;
                    }
                }, RESTORE_DELAY_SHORT);

                // Restore expanded documents (after renderCheckboxes completes)
                setTimeout(() => {
                    expandedDocs.forEach(docId => {
                        const sectionsContainer = getElement(`sections-${docId}`);
                        if (sectionsContainer) {
                            sectionsContainer.classList.add('expanded');
                            const chevron = document.querySelector(`[data-doc-id="${docId}"] .doc-row-chevron`);
                            if (chevron) {
                                chevron.classList.add('expanded');
                            }
                        }
                    });

                    // Restore selected checkboxes based on stored selectedChoices
                    if (state.selectedChoices && state.selectedChoices.length > 0) {
                        state.selectedChoices.forEach(choiceLabel => {
                            const sectionRows = explainerResultsCheckboxes.querySelectorAll('.section-row');
                            sectionRows.forEach(row => {
                                const checkbox = row.querySelector('.section-row-checkbox');
                                if (checkbox && checkbox.value === choiceLabel) {
                                    checkbox.checked = true;
                                    updateSectionSelection(row, true);
                                }
                            });
                        });

                        // Update document checkbox states
                        const allDocIds = new Set();
                        storedResults.forEach(item => {
                            if (item.doc_id) allDocIds.add(item.doc_id);
                        });
                        allDocIds.forEach(docId => {
                            updateDocCheckboxState(docId);
                        });
                    }

                    isRestoring = false;
                }, RESTORE_DELAY_LONG);

                // Restore explanation output if it exists
                if (state.explanationOutput && explanationOutput) {
                    explanationOutput.innerHTML = state.explanationOutput;
                    explanationOutput.style.display = 'block';
                    // If explanation exists, generation is no longer in progress
                    generationInProgress = false;

                    // Re-attach citation click handlers
                    setTimeout(() => {
                        setupCitationClickHandlers();
                    }, 100);
                }
            } else {
                isRestoring = false;
            }

            // Check for interrupted generation
            if (state.generationInProgress && !state.explanationOutput && explanationOutput) {
                explanationOutput.style.display = 'block';
                explanationOutput.innerHTML = `
                    <div class="placeholder-text" style="text-align: center; padding: 32px;">
                        <p style="color: var(--muted-foreground); margin-bottom: 12px;">
                            Explanation generation was interrupted when you switched tabs.
                        </p>
                        <p style="color: var(--muted-foreground); font-size: 0.875rem;">
                            Please click "Generate Explanation" again to regenerate.
                        </p>
                    </div>
                `;
                generationInProgress = false;
                saveExplainerState();
            }

            // Restore aliases drawer state
            if (state.aliasesDrawerOpen && aliasesDrawer) {
                aliasesDrawer.classList.add('open');
                loadAliases();
            }

            // Restore document viewer state
            if (state.documentViewerOpen && documentViewerSidebar) {
                setTimeout(() => {
                    try {
                        documentViewerSidebar.style.transform = 'translateX(0)';
                        const documentViewerContent = getElement('document-viewer-content');
                        const documentViewerDocName = getElement('document-viewer-doc-name');
                        if (documentViewerContent && state.documentViewerContent) {
                            documentViewerContent.innerHTML = state.documentViewerContent;
                        }
                        if (documentViewerDocName && state.documentViewerDocName) {
                            documentViewerDocName.textContent = state.documentViewerDocName;
                        }
                        if (previewFullDocBtn) {
                            previewFullDocBtn.classList.add('active');
                        }
                    } catch (e) {
                        console.error('[Explainer] Error restoring document viewer:', e);
                    }
                }, RESTORE_DELAY_MEDIUM);
            }

            // Restore preview panel state
            if (state.previewPanelOpen && state.activePreviewId && state.previewContent) {
                setTimeout(() => {
                    try {
                        const previewPanel = getElement('section-preview-panel');
                        const previewContent = getElement('preview-content');
                        const previewDocName = getElement('preview-doc-name');
                        const previewSectionTitle = getElement('preview-section-title');
                        const explainerRight = document.querySelector('.explainer-right');

                        if (previewPanel && previewContent) {
                            previewContent.innerHTML = state.previewContent;
                            if (state.previewDocName && previewDocName) {
                                previewDocName.textContent = state.previewDocName;
                            }
                            if (state.previewSectionTitle && previewSectionTitle) {
                                previewSectionTitle.textContent = state.previewSectionTitle;
                            }
                            previewPanel.classList.remove('hidden');
                            if (explainerRight) {
                                explainerRight.classList.add('preview-open');
                            }
                            updatePreviewActiveState();
                        }
                    } catch (e) {
                        console.error('[Explainer] Error restoring preview panel:', e);
                    }
                }, RESTORE_DELAY_MEDIUM + RESTORE_DELAY_SHORT);
            }

            updateGenerateButtonState();
            return true;
        } catch (e) {
            console.error('[Explainer] Error restoring state:', e);
            isRestoring = false;
            return false;
        }
    }

    // Save state before page unload and warn if operations are in progress
    window.addEventListener('beforeunload', (e) => {
        saveExplainerState();
        if (generationInProgress || previewLoadingInProgress) {
            e.preventDefault();
            e.returnValue = '';
            return 'Explanation generation or preview loading is in progress. Are you sure you want to leave?';
        }
    });

    // Save state when page becomes hidden (user switches tabs)
    document.addEventListener('visibilitychange', () => {
        if (document.hidden) {
            saveExplainerState();
        }
    });

    // Save state on pagehide (more reliable than beforeunload in some browsers)
    window.addEventListener('pagehide', () => {
        saveExplainerState();
    });

    // Also save state periodically and on key state changes
    setInterval(saveExplainerState, 5000); // Save every 5 seconds

    // Initialize button state
    updateGenerateButtonState();

    // Try to restore state on page load
    const restored = restoreExplainerState();

    // Only initialize empty state if restore failed (no saved state)
    if (!restored) {
        // Initialize empty state - show results container with count 0
        updateResultCounts(0, 0);
        explainerResultsContainer.style.display = 'flex';
        const emptyLeft = document.getElementById('explainer-empty-left');
        if (emptyLeft) emptyLeft.style.display = 'none';
    }

    // Helper function to display progress messages sequentially
    function displayProgressMessages(messages, container) {
        if (!messages || messages.length === 0) return;

        // Show the last progress message with spinner and animation
        const lastMessage = messages[messages.length - 1];
        container.innerHTML = `<div class="progress-message" style="display:flex;align-items:center;gap:8px;"><div class="spinner" style="width:14px;height:14px;"></div> <span>${lastMessage}</span></div>`;
    }

    // --- SEARCH LOGIC WITH ALIASES ---
    // Helper: Update result counts display
    function updateResultCounts(resultsCount, selectedCount) {
        const resultsCountNumber = getElement('results-count-number');
        const selectedCountBadge = getElement('selected-count-badge');
        if (resultsCountNumber) resultsCountNumber.textContent = String(resultsCount);
        if (selectedCountBadge) selectedCountBadge.textContent = String(selectedCount);
    }

    // Helper: Show empty results state
    function showEmptyResultsState() {
        explainerResultsContainer.style.display = 'flex';
        const emptyLeft = getElement('explainer-empty-left');
        if (emptyLeft) emptyLeft.style.display = 'none';
        resultsCount.style.display = 'none';
        if (!isRestoring) {
            storedResults = [];
            renderCheckboxes([]);
            updateResultCounts(0, 0);
            updateGenerateButtonState();
            saveExplainerState();
        }
    }

    async function searchForExplainer() {
        const keyword = explainerKeyword.value.trim();
        const emptyLeft = getElement('explainer-empty-left');

        if (!keyword) {
            if (queryFilterContainer) {
                queryFilterContainer.style.display = 'none';
            }
            showEmptyResultsState();
            return;
        }

        try {
            explainerSearchBtn.disabled = true;
            resultsCount.style.display = 'block';
            resultsCount.innerHTML = '<div style="display:flex;align-items:center;gap:8px;"><div class="spinner" style="width:14px;height:14px;"></div> <span>Searching...</span></div>';

            // Reset translation info for new search
            translationInfo = null;

            // Hide query filter container at start of new search
            if (queryFilterContainer) {
                queryFilterContainer.style.display = 'none';
            }

            // Reset query labels to defaults
            if (queryLabelEn) queryLabelEn.textContent = 'Query';
            if (queryLabelVn) queryLabelVn.textContent = 'VN';
            if (queryCheckboxVn) {
                queryCheckboxVn.disabled = false;
                queryCheckboxVn.checked = true;
            }
            if (queryCheckboxEn) queryCheckboxEn.checked = true;

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

                // Capture translation_info: when alias was found use parent keyword's response (labels show parent + its translation)
                const captureForThisKw = foundAliasKW ? kw === foundAliasKW.name : kw === keyword;
                if (result.translation_info && !translationInfo && captureForThisKw) {
                    translationInfo = result.translation_info;
                    // When user searched by alias, EN filter must match alias OR parent keyword
                    translationInfo.effectiveOriginals = searchKeywords.map(k => k.toLowerCase());

                    // Update labels: parent keyword and its translation (not the alias)
                    if (translationInfo.original) {
                        queryLabelEn.textContent = translationInfo.original;
                    }
                    if (translationInfo.translation) {
                        queryLabelVn.textContent = translationInfo.translation;
                        queryCheckboxVn.disabled = false;
                    } else {
                        queryLabelVn.textContent = 'VN';
                        queryCheckboxVn.disabled = true;
                        queryCheckboxVn.checked = false;
                    }

                    // Show query filter container after translation info is captured
                    if (queryFilterContainer && translationInfo.original) {
                        queryFilterContainer.style.display = 'flex';
                    }
                }

                if (result.success && result.choices) {
                    result.choices.forEach((choice, idx) => {
                        const storeItem = result.store_data[idx];
                        const key = `${storeItem.doc_id}:${storeItem.section_heading}`;
                        if (!mergedKeys.has(key)) {
                            mergedKeys.add(key);
                            allChoices.push(choice);
                            allStoreData.push(storeItem);
                        } else {
                            // Merge matching keywords for existing results
                            const existingItem = allStoreData.find(item => `${item.doc_id}:${item.section_heading}` === key);
                            if (existingItem && storeItem._matching_keywords) {
                                if (!existingItem._matching_keywords) existingItem._matching_keywords = [];
                                storeItem._matching_keywords.forEach(mk => {
                                    if (!existingItem._matching_keywords.includes(mk)) {
                                        existingItem._matching_keywords.push(mk);
                                    }
                                });
                            }
                        }
                    });
                }
            }

            if (allChoices.length === 0) {
                // Hide query filter container when no results
                if (queryFilterContainer) {
                    queryFilterContainer.style.display = 'none';
                }

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
                updateResultCounts(0, 0);

                // Attach deep search handler
                const deepSearchBtn = getElement('deep-search-btn');
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
            updateResultCounts(count, getSelectedChoices().length);

            renderCheckboxes(allChoices);

            // Apply query filter after rendering
            applyQueryFilter();

            // Save state after search completes
            saveExplainerState();

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
            updateResultCounts(0, 0);
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

    function groupChoicesByDocument(choices) {
        const grouped = {};
        choices.forEach((choice, index) => {
            const storeItem = storedResults[index];
            const parts = choice.split(' → ');
            const docName = parts[0] || 'Unknown Document';
            const sectionTitle = parts.length > 1 ? parts.slice(1).join(' → ') : choice;

            if (!grouped[docName]) {
                grouped[docName] = [];
            }
            grouped[docName].push({
                choice: choice,
                storeItem: storeItem,
                index: index,
                sectionTitle: sectionTitle
            });
        });
        return grouped;
    }

    function sortSectionsByChunkId(sections) {
        return sections.sort((sectionA, sectionB) => {
            const chunkIdA = sectionA.storeItem?.chunk_id || '';
            const chunkIdB = sectionB.storeItem?.chunk_id || '';
            return chunkIdA.localeCompare(chunkIdB, undefined, { numeric: true, sensitivity: 'base' });
        });
    }

    function createDocumentHeader(docName, docId, sections) {
        const docHeader = document.createElement('div');
        docHeader.className = 'doc-row-header';

        const chevron = document.createElement('img');
        chevron.src = '/static/icons/chevron-right.svg';
        chevron.className = `doc-row-chevron ${expandedDocs.has(docId) ? 'expanded' : ''}`;
        chevron.onclick = (e) => {
            e.stopPropagation();
            toggleDocExpanded(docId);
        };

        const docCheckbox = document.createElement('input');
        docCheckbox.type = 'checkbox';
        docCheckbox.className = 'doc-row-checkbox';
        docCheckbox.id = `doc-checkbox-${docId}`;
        docCheckbox.onclick = (e) => {
            e.stopPropagation();
            toggleDocumentSelection(docId, docCheckbox.checked);
        };

        const fileIcon = document.createElement('img');
        fileIcon.src = '/static/icons/file.svg';
        fileIcon.className = 'doc-row-icon';

        const docNameSpan = document.createElement('span');
        docNameSpan.className = 'doc-row-name';
        docNameSpan.textContent = docName;
        docNameSpan.title = docName;

        // Find metadata (version, author, date) from storedResults for this document
        let version = null;
        let author = null;
        let date = null;

        if (sections && sections.length > 0 && sections[0].storeItem) {
            // Try to get metadata from the first section's storeItem
            const firstStoreItem = sections[0].storeItem;
            if (firstStoreItem.gdd_version) {
                version = firstStoreItem.gdd_version;
            }
            if (firstStoreItem.gdd_author) {
                author = firstStoreItem.gdd_author;
            }
            if (firstStoreItem.gdd_date) {
                date = firstStoreItem.gdd_date;
            }
        }

        // If not found in storeItem, try to find it from storedResults by doc_name
        if ((!version || !author || !date) && storedResults && storedResults.length > 0) {
            const matchingResult = storedResults.find(item => item.doc_name === docName);
            if (matchingResult) {
                if (!version && matchingResult.gdd_version) {
                    version = matchingResult.gdd_version;
                }
                if (!author && matchingResult.gdd_author) {
                    author = matchingResult.gdd_author;
                }
                if (!date && matchingResult.gdd_date) {
                    date = matchingResult.gdd_date;
                }
            }
        }

        // Use actual version if available, otherwise default to "v1.0"
        let displayVersion = version || 'v1.0';

        // Add "v" prefix if version doesn't start with "v"
        if (displayVersion && !displayVersion.toLowerCase().startsWith('v')) {
            displayVersion = 'v' + displayVersion;
        }

        const countSpan = document.createElement('span');
        countSpan.className = 'doc-row-count';
        countSpan.id = `doc-count-${docId}`;
        countSpan.textContent = `(0/${sections.length})`;
        // Set fixed width to ensure version bubbles align consistently
        // Width accommodates double-digit counts like "(0/99)"
        countSpan.style.width = '45px';
        countSpan.style.textAlign = 'right';
        countSpan.style.display = 'inline-block';
        countSpan.style.flexShrink = '0';

        docHeader.appendChild(chevron);
        docHeader.appendChild(docCheckbox);
        docHeader.appendChild(fileIcon);
        docHeader.appendChild(docNameSpan);

        // Always add version bubble with lighter green - smaller and aligned
        const versionBubble = document.createElement('div');
        versionBubble.textContent = displayVersion;
        versionBubble.setAttribute('data-version-bubble', 'true'); // For click-outside detection
        const lightGreen = 'rgb(108, 226, 151)';
        const darkGreen = '#22c55e';
        versionBubble.style.cssText = `background-color: ${lightGreen}; color: white; font-size: 0.65rem; font-weight: 600; padding: 2px 6px; border-radius: 9999px; white-space: nowrap; cursor: pointer; margin-left: 16px; margin-right: -14px; display: inline-flex; align-items: center; justify-content: center; height: 18px; line-height: 1; flex-shrink: 0; position: relative;`;
        versionBubble.onmouseenter = function () { this.style.backgroundColor = darkGreen; };
        versionBubble.onmouseleave = function () { this.style.backgroundColor = lightGreen; };

        // Create metadata chat bubble (matching provided HTML structure)
        const metadataBubble = document.createElement('div');
        metadataBubble.className = 'metadata-chat-bubble';
        metadataBubble.style.cssText = 'display: none; position: fixed; width: 240px; padding: 20px; background: rgba(248, 248, 248, 0.95); border-radius: 8px; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15); z-index: 99999; align-items: center; line-height: 1.6; flex-direction: column; justify-content: center;';

        // Append to body to ensure it's above everything
        document.body.appendChild(metadataBubble);

        // Build metadata content matching the provided HTML structure
        const metadataContent = document.createElement('p');
        metadataContent.style.cssText = 'font-size: 0.8125rem; color: var(--text-body, #333); display: flex; flex-direction: column; gap: 12px; margin: 0; width: 100%;';

        // Version
        const versionRow = document.createElement('span');
        versionRow.style.cssText = 'display: block;';
        versionRow.innerHTML = `<span style="font-weight: 600; color: var(--text-heading, #1a1a1a);">Version:</span> ${displayVersion}`;
        metadataContent.appendChild(versionRow);

        // Author
        const authorRow = document.createElement('span');
        authorRow.style.cssText = 'display: block;';
        authorRow.innerHTML = `<span style="font-weight: 600; color: var(--text-heading, #1a1a1a);">Author:</span> ${author || 'N/A'}`;
        metadataContent.appendChild(authorRow);

        // Date
        const dateRow = document.createElement('span');
        dateRow.style.cssText = 'display: block;';
        dateRow.innerHTML = `<span style="font-weight: 600; color: var(--text-heading, #1a1a1a);">Date:</span> ${date || 'N/A'}`;
        metadataContent.appendChild(dateRow);

        metadataBubble.appendChild(metadataContent);

        // Function to position the bubble relative to version bubble
        const positionBubble = () => {
            const rect = versionBubble.getBoundingClientRect();
            // Position bottom-left of bubble at top-right of version bubble
            metadataBubble.style.left = (rect.right + 4) + 'px';
            metadataBubble.style.bottom = (window.innerHeight - rect.top + 4) + 'px';
        };

        // Toggle chat bubble on click
        versionBubble.onclick = function (e) {
            e.stopPropagation(); // Prevent document expansion
            e.preventDefault(); // Prevent any default behavior
            // Close all other open bubbles first
            document.querySelectorAll('.metadata-chat-bubble').forEach(bubble => {
                if (bubble !== metadataBubble) {
                    bubble.style.display = 'none';
                }
            });
            // Toggle this bubble
            const isCurrentlyOpen = metadataBubble.style.display === 'flex';
            if (!isCurrentlyOpen) {
                positionBubble();
                metadataBubble.style.display = 'flex';
            } else {
                metadataBubble.style.display = 'none';
            }
        };

        // Prevent clicks on the bubble itself from propagating
        metadataBubble.onclick = function (e) {
            e.stopPropagation();
        };

        // Reposition on scroll or resize
        window.addEventListener('scroll', () => {
            if (metadataBubble.style.display === 'flex') {
                positionBubble();
            }
        }, true);

        window.addEventListener('resize', () => {
            if (metadataBubble.style.display === 'flex') {
                positionBubble();
            }
        });

        docHeader.appendChild(versionBubble);

        docHeader.appendChild(countSpan);
        docHeader.onclick = (e) => {
            // Don't toggle if clicking on version bubble or its chat bubble
            if (e.target.closest('[data-version-bubble]') || e.target.closest('.metadata-chat-bubble')) {
                return;
            }
            toggleDocExpanded(docId);
        };

        return docHeader;
    }

    function createSectionRow(item, docName, docId) {
        const sectionId = `section-${item.index}`;
        const sectionRow = document.createElement('div');
        sectionRow.className = 'section-row';
        sectionRow.dataset.sectionId = sectionId;
        sectionRow.dataset.docId = docId;
        sectionRow.dataset.index = item.index;

        if (activePreviewId === sectionId) {
            sectionRow.classList.add('preview-active');
        }

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

        const sectionTitle = document.createElement('span');
        sectionTitle.className = 'section-row-title';
        sectionTitle.textContent = item.sectionTitle;
        sectionTitle.title = item.choice;

        const previewBtn = document.createElement('button');
        previewBtn.className = `preview-btn ${activePreviewId === sectionId ? 'active' : ''}`;
        previewBtn.innerHTML = `
            <img src="/static/icons/eye.svg" width="12" height="12">
            <span>Preview</span>
        `;
        previewBtn.onclick = (e) => {
            e.stopPropagation();
            const previewDocName = item.storeItem?.doc_name || docName;
            const docId = item.storeItem?.doc_id || '';
            const sectionHeading = item.storeItem?.section_heading || item.sectionTitle;
            const previewContent = item.storeItem?.content || '';
            togglePreview(sectionId, previewDocName, item.sectionTitle, previewContent, docId, sectionHeading);
        };

        sectionRow.appendChild(sectionCheckbox);
        sectionRow.appendChild(sectionTitle);
        sectionRow.appendChild(previewBtn);

        sectionRow.onclick = () => {
            sectionCheckbox.checked = !sectionCheckbox.checked;
            updateSectionSelection(sectionRow, sectionCheckbox.checked);
            updateDocCheckboxState(docId);
            updateGenerateButtonState();
            updateSelectAllNoneState();
        };

        return sectionRow;
    }

    function renderCheckboxes(choices) {
        explainerResultsCheckboxes.innerHTML = '';
        groupedResults = {};

        // Update query variant labels with actual keywords
        if (translationInfo) {
            // Always use original keyword for EN label
            if (translationInfo.original) {
                queryLabelEn.textContent = translationInfo.original;
            } else if (lastSearchKeyword) {
                queryLabelEn.textContent = lastSearchKeyword;
            }

            // Use translation for VN label if available
            if (translationInfo.translation) {
                queryLabelVn.textContent = translationInfo.translation;
                queryCheckboxVn.disabled = false;
            } else {
                // No translation available - disable VN checkbox
                queryLabelVn.textContent = 'VN';
                queryCheckboxVn.disabled = true;
                queryCheckboxVn.checked = false;
            }
        } else if (lastSearchKeyword) {
            // Fallback: use lastSearchKeyword if translationInfo not available
            queryLabelEn.textContent = lastSearchKeyword;
            queryLabelVn.textContent = 'VN';
            queryCheckboxVn.disabled = true;
            queryCheckboxVn.checked = false;
        }

        if (!choices || choices.length === 0) {
            expandedDocs.clear();
            activePreviewId = null;
            activePreviewDocIds = {}; // Clear all docId mappings when clearing results
            closePreviewPanel();
            return;
        }

        groupedResults = groupChoicesByDocument(choices);

        // Render hierarchical structure
        Object.keys(groupedResults).forEach(docName => {
            const sections = sortSectionsByChunkId(groupedResults[docName]);
            const docId = `doc-${hashString(docName)}`;

            const docRow = document.createElement('div');
            docRow.className = 'doc-row';
            docRow.dataset.docId = docId;

            const docHeader = createDocumentHeader(docName, docId, sections);
            docRow.appendChild(docHeader);

            const sectionsContainer = document.createElement('div');
            sectionsContainer.className = `doc-sections ${expandedDocs.has(docId) ? 'expanded' : ''}`;
            sectionsContainer.id = `sections-${docId}`;

            sections.forEach(item => {
                const sectionRow = createSectionRow(item, docName, docId);
                sectionsContainer.appendChild(sectionRow);
            });

            docRow.appendChild(sectionsContainer);
            explainerResultsCheckboxes.appendChild(docRow);
        });

        // Reset select all/none checkboxes
        selectAllCheckbox.checked = false;
        selectNoneCheckbox.checked = false;

        // Apply query filter after rendering
        applyQueryFilter();
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


    function toggleDocExpanded(docId) {
        if (expandedDocs.has(docId)) {
            expandedDocs.delete(docId);
        } else {
            expandedDocs.add(docId);
        }

        const sectionsContainer = getElement(`sections-${docId}`);
        const chevron = document.querySelector(`[data-doc-id="${docId}"] .doc-row-chevron`);

        if (sectionsContainer) {
            sectionsContainer.classList.toggle('expanded', expandedDocs.has(docId));
        }
        if (chevron) {
            chevron.classList.toggle('expanded', expandedDocs.has(docId));
        }

        // Save state after expansion changes
        saveExplainerState();
    }

    function toggleDocumentSelection(docId, selected) {
        const sectionsContainer = getElement(`sections-${docId}`);
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
        // Save state after selection changes (but not during restore)
        if (!isRestoring) {
            saveExplainerState();
        }
    }

    function updateDocCheckboxState(docId) {
        const docCheckbox = getElement(`doc-checkbox-${docId}`);
        const countSpan = getElement(`doc-count-${docId}`);
        const sectionsContainer = getElement(`sections-${docId}`);

        if (!sectionsContainer || !docCheckbox) {
            return;
        }

        const checkboxes = sectionsContainer.querySelectorAll('.section-row-checkbox');
        const checkedCount = sectionsContainer.querySelectorAll('.section-row-checkbox:checked').length;

        // Count only visible sections (not hidden by filter)
        const sectionRows = sectionsContainer.querySelectorAll('.section-row');
        let visibleCount = 0;
        sectionRows.forEach(row => {
            const inlineStyle = row.style.display;
            const computedStyle = window.getComputedStyle(row);
            // Row is visible if inline style is not 'none' AND computed style is not 'none'
            if (inlineStyle !== 'none' && computedStyle.display !== 'none') {
                visibleCount++;
            }
        });
        const totalCount = visibleCount > 0 ? visibleCount : checkboxes.length; // Fallback to all if no visible

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

    /**
     * Extract image URLs from chunk content (markdown image syntax ![...](url)).
     * @param {string} content - Raw chunk text
     * @returns {string[]} Array of image URLs
     */
    function extractImageUrlsFromContent(content) {
        if (!content || typeof content !== 'string') return [];
        const urls = [];
        const re = /!\[[^\]]*\]\(([^)]+)\)/g;
        let m;
        while ((m = re.exec(content)) !== null) {
            const url = m[1].trim();
            if (url && !urls.includes(url)) urls.push(url);
        }
        return urls;
    }

    function closeImageSidebar() {
        imageSidebarOpen = false;
        const sidebar = document.getElementById('preview-images-sidebar');
        if (sidebar) sidebar.classList.remove('open');
    }

    function openImageSidebar() {
        if (previewImageUrls.length === 0) return;
        imageSidebarOpen = true;
        const sidebar = document.getElementById('preview-images-sidebar');
        if (sidebar) sidebar.classList.add('open');
        renderPreviewImagesSidebar();
    }

    function renderPreviewImagesSidebar() {
        const listEl = document.getElementById('preview-images-sidebar-list');
        if (!listEl) return;

        listEl.innerHTML = '';
        const n = previewImageUrls.length;
        if (n === 0) return;

        previewImageUrls.forEach((src, index) => {
            const wrap = document.createElement('div');
            wrap.className = 'preview-images-sidebar-thumb' + (index === currentImageIndex ? ' selected' : '');
            wrap.dataset.index = String(index);
            const inner = document.createElement('div');
            inner.className = 'preview-images-sidebar-thumb-inner';
            const img = document.createElement('img');
            img.src = src;
            img.alt = 'Chunk image ' + (index + 1);
            img.loading = 'lazy';
            inner.appendChild(img);
            wrap.appendChild(inner);
            const cap = document.createElement('div');
            cap.className = 'preview-images-sidebar-thumb-caption';
            cap.textContent = 'Image ' + (index + 1);
            wrap.appendChild(cap);
            wrap.addEventListener('click', () => {
                currentImageIndex = index;
                renderPreviewImagesSidebar();
                const modal = document.getElementById('preview-image-expanded-modal');
                const imgEl = document.getElementById('preview-image-expanded-img');
                if (modal && imgEl) {
                    imgEl.src = previewImageUrls[index];
                    modal.classList.remove('hidden');
                    updateExpandedNav();
                }
            });
            listEl.appendChild(wrap);
        });
    }

    function updateExpandedNav() {
        const countEl = document.getElementById('preview-expanded-count');
        const prevBtn = document.getElementById('preview-expanded-prev-btn');
        const nextBtn = document.getElementById('preview-expanded-next-btn');
        const imgEl = document.getElementById('preview-image-expanded-img');
        const n = previewImageUrls.length;
        if (countEl) countEl.textContent = n ? `Image ${currentImageIndex + 1} of ${n}` : 'Image 0 of 0';
        if (prevBtn) prevBtn.disabled = n === 0 || currentImageIndex <= 0;
        if (nextBtn) nextBtn.disabled = n === 0 || currentImageIndex >= n - 1;
        if (imgEl && n && previewImageUrls[currentImageIndex]) imgEl.src = previewImageUrls[currentImageIndex];
    }

    // Preview functions
    async function togglePreview(sectionId, docName, sectionTitle, content, docId, sectionHeading) {
        const previewPanel = getElement('section-preview-panel');
        const explainerRight = document.querySelector('.explainer-right');
        const previewContent = getElement('preview-content');

        if (activePreviewId === sectionId) {
            // Close preview (this will reset previewLoadingInProgress)
            closePreviewPanel();
            return; // Exit early after closing
        } else {
            // Open/switch preview
            activePreviewId = sectionId;

            // Store docId for this sectionId (supports both preview button and citation clicks)
            if (docId) {
                activePreviewDocIds[sectionId] = docId;
            }

            // Update preview panel header
            const previewDocNameEl = getElement('preview-doc-name');
            const previewSectionTitleEl = getElement('preview-section-title');
            if (previewDocNameEl) previewDocNameEl.textContent = docName;
            if (previewSectionTitleEl) previewSectionTitleEl.textContent = sectionTitle;

            // View Images button and previewImageUrls are set from API response (single source of truth for both document-list and citation paths)
            previewImageUrls = [];
            closeImageSidebar();
            const viewImagesBtn = document.getElementById('view-images-btn');
            if (viewImagesBtn) viewImagesBtn.classList.add('hidden');

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
            previewLoadingInProgress = true; // Mark preview as loading
            saveExplainerState(); // Save state immediately

            try {
                const response = await fetch('/api/gdd/explainer/preview', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        doc_id: docId,
                        section_heading: sectionHeading,
                        doc_name: docName,
                        language: selectedLanguage
                    }),
                    keepalive: true // Allow request to complete even after page navigation
                });

                const result = await response.json();

                if (result.success && result.summary) {
                    // Format and display the summary (similar to chatbox response)
                    previewContent.innerHTML = formatPreviewContent(result.summary);
                    // Single source of truth: set View Images from API raw_content (works for both document-list and citation paths)
                    const rawContent = result.raw_content || '';
                    previewImageUrls = extractImageUrlsFromContent(rawContent);
                    currentImageIndex = 0;
                    const viewImagesBtnEl = document.getElementById('view-images-btn');
                    if (viewImagesBtnEl) {
                        if (previewImageUrls.length > 0) {
                            viewImagesBtnEl.classList.remove('hidden');
                        } else {
                            viewImagesBtnEl.classList.add('hidden');
                        }
                    }
                } else {
                    previewContent.innerHTML = `<p class="placeholder-text" style="color: var(--status-error);">Error: ${result.error || 'Failed to generate summary'}</p>`;
                }

                previewLoadingInProgress = false; // Mark preview as complete
                // Save state after preview content is loaded
                saveExplainerState();
            } catch (error) {
                console.error('Error fetching preview:', error);
                previewContent.innerHTML = `<p class="placeholder-text" style="color: var(--status-error);">Error: ${error.message}</p>`;
                previewLoadingInProgress = false; // Mark preview as failed/complete
                saveExplainerState(); // Save state even on error
            }
        }

        // Save state when preview is opened/closed
        saveExplainerState();
    }

    function closePreviewPanel() {
        const previewPanel = document.getElementById('section-preview-panel');
        const explainerRight = document.querySelector('.explainer-right');

        // Clear the docId mapping for the current preview
        if (activePreviewId && activePreviewDocIds[activePreviewId]) {
            delete activePreviewDocIds[activePreviewId];
        }

        activePreviewId = null;
        previewLoadingInProgress = false; // Reset preview loading flag when closing
        previewImageUrls = [];
        closeImageSidebar();
        const viewImagesBtn = document.getElementById('view-images-btn');
        if (viewImagesBtn) viewImagesBtn.classList.add('hidden');

        if (previewPanel) {
            previewPanel.classList.add('hidden');
        }
        if (explainerRight) {
            explainerRight.classList.remove('preview-open');
        }

        updatePreviewActiveState();

        // Save state when preview is closed
        saveExplainerState();
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

    function setupCitationClickHandlers() {
        // Add click handlers to all citation markers in the explanation
        const citationMarkers = document.querySelectorAll('.citation-marker');

        citationMarkers.forEach((marker) => {
            marker.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();

                const citationNumber = parseInt(marker.getAttribute('data-citation-number'));

                if (!citationNumber || !currentCitations[citationNumber]) {
                    return;
                }

                const citationInfo = currentCitations[citationNumber];
                const docId = citationInfo.doc_id;
                const docName = citationInfo.doc_name || docId;
                const sectionHeading = citationInfo.section_heading || '';
                const chunkId = citationInfo.chunk_id || '';

                // Create a unique section ID for this citation (using chunk_id if available, otherwise doc_id + section_heading)
                const sectionId = chunkId || `citation-${docId}-${sectionHeading}`;

                // Check if this is the same chunk already being previewed
                if (activePreviewId === sectionId) {
                    // Same chunk, do nothing
                    return;
                }

                // Call togglePreview with the citation's chunk info
                // Note: content is empty since we'll fetch it via the preview API
                togglePreview(sectionId, docName, sectionHeading || 'No section', '', docId, sectionHeading);
            });
        });
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

    // View Images button: toggle right sidebar + jump animation
    const viewImagesBtnEl = document.getElementById('view-images-btn');
    if (viewImagesBtnEl) {
        viewImagesBtnEl.addEventListener('click', () => {
            imageSidebarOpen = !imageSidebarOpen;
            const sidebar = document.getElementById('preview-images-sidebar');
            if (imageSidebarOpen) {
                openImageSidebar();
            } else if (sidebar) {
                sidebar.classList.remove('open');
            }
            isJumping = true;
            viewImagesBtnEl.classList.add('jump-animate');
            setTimeout(() => {
                isJumping = false;
                viewImagesBtnEl.classList.remove('jump-animate');
            }, 400);
        });
    }

    // Close images sidebar
    const closeImagesSidebarBtn = document.getElementById('close-images-sidebar-btn');
    if (closeImagesSidebarBtn) {
        closeImagesSidebarBtn.addEventListener('click', () => {
            closeImageSidebar();
        });
    }

    // Prev/Next in expanded image modal (bottom of screen)
    const previewExpandedPrevBtn = document.getElementById('preview-expanded-prev-btn');
    const previewExpandedNextBtn = document.getElementById('preview-expanded-next-btn');
    if (previewExpandedPrevBtn) {
        previewExpandedPrevBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            if (currentImageIndex > 0) {
                currentImageIndex--;
                updateExpandedNav();
                renderPreviewImagesSidebar();
            }
        });
    }
    if (previewExpandedNextBtn) {
        previewExpandedNextBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            if (currentImageIndex < previewImageUrls.length - 1) {
                currentImageIndex++;
                updateExpandedNav();
                renderPreviewImagesSidebar();
            }
        });
    }

    // Expanded image modal: close button
    const closeExpandedImageBtn = document.getElementById('close-expanded-image-btn');
    const expandedImageModal = document.getElementById('preview-image-expanded-modal');
    if (closeExpandedImageBtn && expandedImageModal) {
        closeExpandedImageBtn.addEventListener('click', () => expandedImageModal.classList.add('hidden'));
        expandedImageModal.addEventListener('click', (e) => {
            if (e.target === expandedImageModal) expandedImageModal.classList.add('hidden');
        });
    }

    // Document Viewer Sidebar functions
    const documentViewerSidebar = document.getElementById('document-viewer-sidebar');
    const previewFullDocBtn = document.getElementById('preview-full-doc-btn');
    const closeDocumentViewerBtn = document.getElementById('close-document-viewer-btn');

    async function openDocumentViewer() {
        if (!documentViewerSidebar) return;

        // Get doc_id from the active preview
        let docId = null;
        let docName = 'Document';

        if (activePreviewId) {
            // First, try to get docId from the activePreviewDocIds map
            if (activePreviewDocIds[activePreviewId]) {
                docId = activePreviewDocIds[activePreviewId];
            } else {
                // Fallback: Find the section row with the active preview ID
                const activeRow = document.querySelector(`[data-section-id="${activePreviewId}"]`);
                if (activeRow) {
                    const index = parseInt(activeRow.dataset.index);
                    if (!isNaN(index) && storedResults && storedResults[index]) {
                        docId = storedResults[index].doc_id;
                        activePreviewDocIds[activePreviewId] = docId;
                    }
                }
            }

            // Get doc name from preview panel header
            const previewDocNameEl = document.getElementById('preview-doc-name');
            if (previewDocNameEl) {
                docName = previewDocNameEl.textContent;
            }
        }

        if (!docId) {
            console.warn('[Document Viewer] No doc_id found for active preview');
            // Still open the sidebar but show error message
            documentViewerSidebar.style.transform = 'translateX(0)';
            if (previewFullDocBtn) {
                previewFullDocBtn.classList.add('active');
            }
            const content = document.getElementById('document-viewer-content');
            if (content) {
                content.innerHTML = `
                    <div class="placeholder-text" style="text-align: center; padding: 32px;">
                        <p style="color: var(--status-error);">No document selected for preview.</p>
                    </div>
                `;
            }
            return;
        }

        // Update document name in sidebar
        const docNameEl = document.getElementById('document-viewer-doc-name');
        if (docNameEl) {
            docNameEl.textContent = docName;
        }

        // Show loading state
        const content = document.getElementById('document-viewer-content');
        if (content) {
            content.style.display = 'flex';
            content.style.alignItems = 'center';
            content.style.justifyContent = 'center';
            content.innerHTML = `
                <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 32px; gap: 12px;">
                    <div class="spinner" style="width: 24px; height: 24px; border: 2px solid var(--border); border-top-color: var(--primary); border-radius: 50%; animation: spin 0.8s linear infinite;"></div>
                    <p style="font-size: 0.875rem; color: var(--muted-foreground); margin: 0;">Loading document...</p>
                </div>
            `;
        }

        // Open the sidebar
        documentViewerSidebar.style.transform = 'translateX(0)';
        if (previewFullDocBtn) {
            previewFullDocBtn.classList.add('active');
        }

        // Fetch PDF URL
        try {
            const response = await fetch('/api/gdd/explainer/get-pdf-url', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ doc_id: docId })
            });

            const result = await response.json();

            if (result.success && result.pdf_url) {
                // Display PDF in iframe - ensure it takes full height
                // Add #toolbar=0 to hide the PDF viewer toolbar (download, print, menu icons)
                const pdfUrlWithParams = result.pdf_url.includes('#')
                    ? result.pdf_url.replace(/#.*$/, '') + '#toolbar=0&navpanes=0'
                    : result.pdf_url + '#toolbar=0&navpanes=0';

                if (content) {
                    content.style.display = 'block';
                    content.style.alignItems = 'stretch';
                    content.style.justifyContent = 'stretch';
                    content.innerHTML = `
                        <iframe src="${pdfUrlWithParams}" width="100%" height="100%" style="border: none; display: block; flex: 1; min-height: 0;"></iframe>
                    `;
                    saveExplainerState(); // Save state after PDF is loaded
                }
            } else {
                // Show error message
                if (content) {
                    content.style.display = 'flex';
                    content.style.alignItems = 'center';
                    content.style.justifyContent = 'center';
                    content.innerHTML = `
                        <div class="placeholder-text" style="text-align: center; padding: 32px;">
                            <p style="color: var(--status-error); margin-bottom: 12px;">No PDF found for this document.</p>
                            <p style="color: var(--muted-foreground); font-size: 0.875rem;">${result.error || 'The document PDF is not available in Supabase Storage.'}</p>
                        </div>
                    `;
                }
            }
        } catch (error) {
            console.error('Error fetching document PDF:', error);
            if (content) {
                content.style.display = 'flex';
                content.style.alignItems = 'center';
                content.style.justifyContent = 'center';
                content.innerHTML = `
                    <div class="placeholder-text" style="text-align: center; padding: 32px;">
                        <p style="color: var(--status-error);">Error: ${error.message || 'Failed to load document'}</p>
                    </div>
                `;
            }
        }
    }

    function closeDocumentViewer() {
        if (documentViewerSidebar) {
            documentViewerSidebar.style.transform = 'translateX(100%)';
            if (previewFullDocBtn) {
                previewFullDocBtn.classList.remove('active');
            }
            saveExplainerState(); // Save state when viewer closes
        }
    }

    // Initialize document viewer buttons
    if (previewFullDocBtn) {
        previewFullDocBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            if (isDocumentViewerOpen()) {
                closeDocumentViewer();
            } else {
                openDocumentViewer();
            }
        });
    }

    if (closeDocumentViewerBtn) {
        closeDocumentViewerBtn.addEventListener('click', closeDocumentViewer);
    }

    // Note: We don't need stopPropagation here because we check contains() in the click-outside handler
    // This allows the click-outside handler to work properly

    // Helper function to check if document viewer is open
    function isDocumentViewerOpen() {
        if (!documentViewerSidebar) return false;
        // Check inline style first (most reliable)
        if (documentViewerSidebar.style.transform === 'translateX(0)') {
            return true;
        }
        // Fallback: check computed style
        const computedStyle = window.getComputedStyle(documentViewerSidebar);
        const transform = computedStyle.transform;
        // When open: translateX(0) becomes matrix(1, 0, 0, 1, 0, 0) or 'none'
        // When closed: translateX(100%) becomes matrix(1, 0, 0, 1, 600, 0) or similar (600px is sidebar width)
        if (transform === 'none' || transform === 'matrix(1, 0, 0, 1, 0, 0)') {
            return true;
        }
        // Check if transform indicates sidebar is visible (not translated 100% to the right)
        if (transform.includes('matrix')) {
            // Extract the X translation value (5th value in matrix)
            const match = transform.match(/matrix\([^,]+,\s*[^,]+,\s*[^,]+,\s*[^,]+,\s*([^,]+)/);
            if (match) {
                const translateX = parseFloat(match[1]);
                // If translateX is 0 or close to 0, sidebar is open
                return Math.abs(translateX) < 10;
            }
        }
        return false;
    }

    // Close document viewer when clicking outside
    document.addEventListener('click', (e) => {
        if (isDocumentViewerOpen()) {
            const isInsideViewer = documentViewerSidebar && documentViewerSidebar.contains(e.target);
            const isButton = previewFullDocBtn && previewFullDocBtn.contains(e.target);

            if (!isInsideViewer && !isButton) {
                closeDocumentViewer();
                saveExplainerState();
            }
        }
    }, true); // Use capture phase to catch events earlier

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
            saveExplainerState(); // Save state after selection changes
        } else {
            // When "All" is unchecked, uncheck all sections
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
            saveExplainerState(); // Save state after selection changes
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
            saveExplainerState(); // Save state after selection changes
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
            generationInProgress = true; // Mark generation as in progress
            saveExplainerState(); // Save state immediately

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

            // Always collect both original and translation keywords (if translation exists)
            // Language toggle only affects output language, not which keywords are queried
            // ALWAYS search with both keywords regardless of checkbox state or language toggle
            let selectedKeywords = [explanationKeyword]; // Start with the keyword user searched

            // If translation info exists, always add the translation keyword
            // This ensures we search with BOTH the original keyword AND its translation
            if (translationInfo && translationInfo.translation && translationInfo.translation.trim()) {
                const translation = translationInfo.translation.trim();
                // Only add if it's different from the original keyword (avoid duplicates)
                if (translation.toLowerCase() !== explanationKeyword.trim().toLowerCase()) {
                    selectedKeywords.push(translation);
                }
            }

            // Debug logging to console
            console.log('='.repeat(100));
            console.log('[EXPLAINER] ===== KEYWORD SELECTION DEBUG =====');
            console.log('[EXPLAINER] User searched keyword:', keyword);
            console.log('[EXPLAINER] Explanation keyword (after alias resolution):', explanationKeyword);
            console.log('[EXPLAINER] Translation info:', translationInfo);
            console.log('[EXPLAINER] Selected keywords to query:', selectedKeywords);
            console.log('[EXPLAINER] Language toggle (output language only):', selectedLanguage);
            console.log('[EXPLAINER] Number of selected choices:', selectedChoices.length);
            console.log('='.repeat(100));

            const requestBody = JSON.stringify({
                keyword: explanationKeyword,
                selected_keywords: selectedKeywords,
                selected_choices: selectedChoices,
                stored_results: storedResults,
                language: selectedLanguage
            });

            // Note: Don't use keepalive for large payloads (>64KB limit)
            // The body size can exceed 64KB with many results
            const response = await fetch('/api/gdd/explainer/explain', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: requestBody
            });

            const result = await response.json();
            genStatus.textContent = result.success ? "✓ Completed" : "✕ Generation Failed";
            genStatus.style.color = result.success ? "var(--status-success)" : "var(--status-error)";

            function setExplanationDisplay() {
                explanationOutput.style.display = 'block';
                explanationOutput.style.alignItems = 'stretch';
                explanationOutput.style.justifyContent = 'flex-start';
            }

            if (!result.success) {
                setExplanationDisplay();
                explanationOutput.innerHTML = `<div class="placeholder-text"><p style="color:var(--status-error)">${result.explanation || 'Generation failed'}</p></div>`;
                return;
            }

            setExplanationDisplay();

            // Build timing breakdown if available
            let timingHTML = '';
            if (result.timing_metadata) {
                timingHTML = buildTimingBreakdown(result.timing_metadata);
            }

            explanationOutput.innerHTML = timingHTML + `<div class="generated-explanation" style="color: var(--foreground)">${renderMarkdown(result.explanation || '', 'Explanation', keyword)}</div>`;

            // Store citations map for citation click handling
            if (result.citations) {
                currentCitations = result.citations;
            } else {
                currentCitations = {};
            }

            // Mark generation as complete
            generationInProgress = false;

            // Save state after explanation is generated
            saveExplainerState();

            // Add click handlers to citation markers (use setTimeout to ensure DOM is ready)
            setTimeout(() => {
                setupCitationClickHandlers();
            }, 100);

            // Add toggle functionality for timing breakdown
            if (result.timing_metadata) {
                const toggleBtn = explanationOutput.querySelector('.timing-toggle');
                const timingContent = explanationOutput.querySelector('.timing-content');
                const toggleSpan = toggleBtn?.querySelector('span');
                const toggleIcon = toggleBtn?.querySelector('.icon');

                if (toggleBtn && timingContent && toggleSpan) {
                    const totalTime = result.timing_metadata.total_time || 0;
                    toggleBtn.addEventListener('click', () => {
                        const isHidden = timingContent.style.display === 'none';
                        timingContent.style.display = isHidden ? 'block' : 'none';
                        toggleSpan.textContent = isHidden
                            ? `⏱️ Hide Timing Details (Total: ${totalTime.toFixed(2)}s)`
                            : `⏱️ Show Timing Details (Total: ${totalTime.toFixed(2)}s)`;
                        if (toggleIcon) {
                            toggleIcon.style.transform = isHidden ? 'rotate(90deg)' : 'rotate(0deg)';
                        }
                        toggleBtn.classList.toggle('expanded', isHidden);
                    });
                }
            }

        } catch (error) {
            generationInProgress = false; // Mark generation as failed/complete
            saveExplainerState(); // Save state even on error

            genStatus.textContent = "Network Error";
            genStatus.style.color = "var(--status-error)";
            explanationOutput.style.display = 'block';
            explanationOutput.style.alignItems = 'stretch';
            explanationOutput.style.justifyContent = 'flex-start';
            explanationOutput.innerHTML = `<div class="placeholder-text"><p style="color:var(--status-error)">Error: ${error.message || 'Unknown error occurred'}</p></div>`;
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
                    <span>⏱️ Show Timing Details (Total: ${totalTime.toFixed(2)}s)</span>
                    <svg class="icon" xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m9 18 6-6-6-6"/></svg>
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

    function applyQueryFilter() {
        if (!translationInfo) {
            // No translation info, show all results
            const allRows = explainerResultsCheckboxes.querySelectorAll('.doc-row, .section-row');
            allRows.forEach(row => {
                row.style.display = '';
            });
            return;
        }

        const enChecked = queryCheckboxEn ? queryCheckboxEn.checked : true;
        const vnChecked = queryCheckboxVn ? queryCheckboxVn.checked : false;
        const vnEnabled = queryCheckboxVn ? !queryCheckboxVn.disabled : false;

        // If neither is checked, hide all results
        if (!enChecked && (!vnChecked || !vnEnabled)) {
            const allRows = explainerResultsCheckboxes.querySelectorAll('.doc-row, .section-row');
            allRows.forEach(row => {
                row.style.display = 'none';
            });
            // Update counts to show 0
            const allDocRows = explainerResultsCheckboxes.querySelectorAll('.doc-row');
            allDocRows.forEach(docRow => {
                const docId = docRow.dataset.docId;
                if (docId) {
                    updateDocCheckboxState(docId);
                }
            });
            return;
        }

        const originalKeyword = translationInfo.original?.toLowerCase() || '';
        const translatedKeyword = translationInfo.translation?.toLowerCase() || '';
        const effectiveOriginals = Array.isArray(translationInfo.effectiveOriginals) && translationInfo.effectiveOriginals.length > 0
            ? translationInfo.effectiveOriginals
            : [originalKeyword].filter(Boolean);

        // Filter results based on matching keywords
        const allRows = explainerResultsCheckboxes.querySelectorAll('.section-row');

        allRows.forEach(row => {
            const index = parseInt(row.dataset.index);
            if (isNaN(index)) {
                row.style.display = 'none';
                return;
            }

            const storeItem = storedResults[index];
            if (!storeItem) {
                row.style.display = 'none';
                return;
            }

            // Get matching keywords for this chunk
            const matchingKeywords = storeItem._matching_keywords || [];
            let shouldShow = false;

            if (matchingKeywords.length > 0) {
                // Check if chunk matches any "original" term (alias + parent keyword when searched by alias)
                const hasOriginal = matchingKeywords.some(kw =>
                    effectiveOriginals.includes(kw.toLowerCase())
                );

                // Check if chunk contains translated keyword
                const hasTranslation = matchingKeywords.some(kw =>
                    kw.toLowerCase() === translatedKeyword
                );

                // Show if:
                // - EN checked and chunk has original keyword, OR
                // - VN checked and chunk has translated keyword
                if (enChecked && hasOriginal) {
                    shouldShow = true;
                } else if (vnChecked && vnEnabled && hasTranslation) {
                    shouldShow = true;
                }

                // Special case: if chunk contains both keywords, show if either checkbox is checked
                if (hasOriginal && hasTranslation) {
                    shouldShow = enChecked || (vnChecked && vnEnabled);
                }
            } else {
                // No matching keywords info - hide by default (user must check a filter to see results)
                shouldShow = false;
            }

            row.style.display = shouldShow ? '' : 'none';
        });

        // Update document row visibility based on child sections
        const docRows = explainerResultsCheckboxes.querySelectorAll('.doc-row');
        docRows.forEach(docRow => {
            const docId = docRow.dataset.docId;
            const childSections = explainerResultsCheckboxes.querySelectorAll(
                `.section-row[data-doc-id="${docId}"]`
            );
            let hasVisibleChild = false;
            childSections.forEach(sectionRow => {
                if (sectionRow.style.display !== 'none') {
                    hasVisibleChild = true;
                }
            });
            docRow.style.display = hasVisibleChild ? '' : 'none';
        });

        // After filtering, uncheck all hidden sections
        // This ensures that when a filter checkbox is unchecked, excluded sections are also deselected
        const allSectionRows = explainerResultsCheckboxes.querySelectorAll('.section-row');
        allSectionRows.forEach(row => {
            if (row.style.display === 'none') {
                const checkbox = row.querySelector('.section-row-checkbox');
                if (checkbox && checkbox.checked) {
                    checkbox.checked = false;
                    updateSectionSelection(row, false);
                }
            }
        });

        // Update document counts after filtering
        const allDocRows = explainerResultsCheckboxes.querySelectorAll('.doc-row');
        allDocRows.forEach(docRow => {
            const docId = docRow.dataset.docId;
            if (docId) {
                updateDocCheckboxState(docId);
            }
        });

        // Save state after filter changes (but not during restore)
        if (!isRestoring) {
            saveExplainerState();
        }
    }
});


