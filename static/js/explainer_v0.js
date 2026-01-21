// Keyword Finder v0 Implementation - Adapted to vanilla JS with existing backend endpoints

document.addEventListener('DOMContentLoaded', function() {
    // Check if we're on the explainer page
    const searchInput = document.getElementById('keyword-search-input');
    if (!searchInput) return;

    // State management
    const state = {
        documents: [], // [{id, name, sections: [{id, title, selected, doc_id, section_heading, choice_label}]}]
        storedResults: [], // Backend store_data format
        lastKeyword: null,
        expandedDocs: new Set(),
        resultsExpanded: true,
        sectionPreview: null,
        activePreviewId: null
    };

    // DOM elements
    const elements = {
        searchInput: document.getElementById('keyword-search-input'),
        searchBtn: document.getElementById('keyword-search-btn'),
        explainBtn: document.getElementById('explain-btn'),
        resultCountText: document.getElementById('result-count-text'),
        headerResultCount: document.getElementById('header-result-count'),
        selectedCountBadge: document.getElementById('selected-count-badge'),
        resultsToggle: document.getElementById('search-results-toggle'),
        chevronIcon: document.getElementById('chevron-icon'),
        resultsContent: document.getElementById('search-results-content'),
        documentsList: document.getElementById('documents-list'),
        selectAllCheckbox: document.getElementById('select-all-checkbox'),
        selectNoneCheckbox: document.getElementById('select-none-checkbox'),
        explanationOutput: document.getElementById('explanation-output'),
        sourceChunksOutput: document.getElementById('source-chunks-output'),
        metadataOutput: document.getElementById('metadata-output'),
        genStatus: document.getElementById('gen-status'),
        chunksCountLabel: document.getElementById('chunks-count-label'),
        openAliasesBtn: document.getElementById('open-aliases-btn')
    };

    // Event listeners
    elements.searchBtn.addEventListener('click', handleSearch);
    elements.searchInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') handleSearch();
    });
    elements.explainBtn.addEventListener('click', handleGenerateExplanation);
    elements.resultsToggle.addEventListener('click', toggleResults);
    elements.selectAllCheckbox.addEventListener('change', handleSelectAll);
    elements.selectNoneCheckbox.addEventListener('change', handleSelectNone);

    // Alias management state
    const aliasState = {
        keywords: [],
        expandedKeywords: new Set(),
        searchQuery: "",
        selectedLanguage: null,
        newAliasInput: {}
    };

    // Alias management DOM elements
    const aliasesDrawer = document.getElementById('aliases-drawer');
    const closeAliasesBtn = document.getElementById('close-aliases-btn');
    const aliasKeywordsList = document.getElementById('alias-keywords-list');
    const aliasSearchInput = document.getElementById('alias-search-input');
    const aliasResultsStats = document.getElementById('alias-results-stats');
    const aliasAddKeywordBtn = document.getElementById('alias-add-keyword-btn');
    const addAliasKeywordDialog = document.getElementById('add-alias-keyword-dialog');
    const confirmAddAliasKeywordBtn = document.getElementById('confirm-add-alias-keyword');
    const aliasLangFilterBtns = document.querySelectorAll('#aliases-drawer .filter-tag');

    // Alias management functions
    async function loadAliases() {
        try {
            const res = await fetch('/api/manage/aliases');
            const data = await res.json();
            aliasState.keywords = data.keywords || [];
            renderAliases();
        } catch (e) { 
            console.error("Load aliases failed", e);
        }
    }

    async function saveAliases() {
        try {
            await fetch('/api/manage/aliases/save', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ keywords: aliasState.keywords })
            });
        } catch (e) { 
            console.error("Save aliases failed", e);
        }
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

        filtered.sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: 'base' }));

        if (aliasResultsStats) {
            aliasResultsStats.textContent = `Results: ${filtered.length} of ${s.keywords.length} keywords`;
        }

        if (filtered.length === 0) {
            aliasKeywordsList.innerHTML = `
                <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 48px 0; text-align: center; opacity: 0.4;">
                    <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-bottom: 12px;">
                        <path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1 0-5H20"></path>
                    </svg>
                    <p style="font-size: 0.875rem;">
                        ${s.searchQuery ? `No results for "${escapeHtml(s.searchQuery)}"` : "No keywords yet."}
                    </p>
                </div>
            `;
            return;
        }

        aliasKeywordsList.innerHTML = filtered.map(kw => {
            const isExpanded = s.expandedKeywords.has(kw.id);
            return `
                <div class="alias-keyword-item" style="border-bottom: 1px solid var(--border);">
                    <div class="keyword-header" onclick="window.explainerV0.toggleKeywordExpansion('${kw.id}')" style="display: flex; align-items: center; justify-content: space-between; padding: 10px 12px; cursor: pointer;">
                        <div style="display: flex; align-items: center; gap: 8px; flex: 1; min-width: 0;">
                            <svg class="v0-icon" style="font-size: 14px; transition: transform 0.2s; ${isExpanded ? 'transform: rotate(90deg);' : ''}" xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <path d="m9 18 6-6-6-6"></path>
                            </svg>
                            <span style="font-weight: 500; font-size: 0.8125rem;" class="truncate">${escapeHtml(kw.name)}</span>
                            <span style="font-size: 0.7rem; color: var(--muted-foreground);">(${kw.aliases.length})</span>
                        </div>
                        <div style="display: flex; align-items: center; gap: 8px;">
                            <span class="badge badge-outline" style="font-size: 10px; padding: 1px 6px;">${kw.language}</span>
                            <button class="action-btn text-destructive" onclick="event.stopPropagation(); window.explainerV0.handleDeleteKeyword('${kw.id}')" style="color: var(--status-error);">
                                <svg class="v0-icon" xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                    <path d="M3 6h18"></path>
                                    <path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"></path>
                                    <path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"></path>
                                </svg>
                            </button>
                        </div>
                    </div>
                    ${isExpanded ? `
                        <div class="alias-expanded-content animate-in" style="background: rgba(0,0,0,0.02); padding: 8px 12px 12px 32px; border-top: 1px solid var(--border);">
                            <div class="alias-items-list" style="display: flex; flex-direction: column; gap: 2px;">
                                ${kw.aliases.map(a => `
                                    <div class="alias-item group" style="display: flex; align-items: center; justify-content: space-between; padding: 4px 8px; border-radius: 4px; font-size: 0.75rem;">
                                        <span style="color: var(--muted-foreground);">${escapeHtml(a.name)}</span>
                                        <button class="action-btn opacity-0 group-hover:opacity-100" onclick="window.explainerV0.handleDeleteAlias('${kw.id}', '${a.id}')" style="padding: 2px; color: var(--status-error);">
                                            <svg class="v0-icon" xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                                <path d="M18 6 6 18"></path>
                                                <path d="M6 6l12 12"></path>
                                            </svg>
                                        </button>
                                    </div>
                                `).join('')}
                            </div>
                            <div style="display: flex; gap: 6px; margin-top: 8px; padding-top: 8px; border-top: 1px solid rgba(0,0,0,0.05);">
                                <input 
                                    type="text" 
                                    placeholder="Add new alias..." 
                                    class="alias-input-field"
                                    id="input-${kw.id}"
                                    style="flex: 1; height: 28px; font-size: 0.75rem; border-radius: 4px; border: 1px solid var(--border); padding: 0 8px;"
                                    onkeydown="if(event.key==='Enter') window.explainerV0.handleAddAlias('${kw.id}', this.value)"
                                >
                                <button class="btn-primary" onclick="window.explainerV0.handleAddAlias('${kw.id}', document.getElementById('input-${kw.id}').value)" style="height: 28px; padding: 0 8px;">
                                    <svg class="v0-icon" xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                        <path d="M5 12h14"></path>
                                        <path d="M12 5v14"></path>
                                    </svg>
                                </button>
                            </div>
                        </div>
                    ` : ''}
                </div>
            `;
        }).join('');
    }

    // Alias management window functions
    window.explainerV0.toggleKeywordExpansion = function(id) {
        if (aliasState.expandedKeywords.has(id)) {
            aliasState.expandedKeywords.delete(id);
        } else {
            aliasState.expandedKeywords.add(id);
        }
        renderAliases();
    };

    window.explainerV0.handleAddAlias = async function(kwId, name) {
        if (!name.trim()) return;
        const kw = aliasState.keywords.find(k => k.id === kwId);
        if (!kw) return;
        
        if (kw.aliases.some(a => a.name.toLowerCase() === name.trim().toLowerCase())) {
            alert("This alias already exists for this keyword");
            return;
        }
        
        try {
            let language = 'en';
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
                await loadAliases();
            } else {
                const error = await response.json();
                alert('Error adding alias: ' + (error.error || 'Unknown error'));
            }
        } catch (error) {
            alert('Error adding alias: ' + error.message);
        }
    };

    window.explainerV0.handleDeleteAlias = async function(kwId, aliasId) {
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
                kw.aliases = kw.aliases.filter(a => a.id !== aliasId);
                renderAliases();
                await loadAliases();
            } else {
                alert('Error deleting alias: ' + (result.error || 'Unknown error'));
            }
        } catch (error) {
            alert('Error deleting alias: ' + error.message);
        }
    };

    window.explainerV0.handleDeleteKeyword = async function(id) {
        const kw = aliasState.keywords.find(k => k.id === id);
        if (!kw) return;
        
        if (!confirm(`Delete keyword "${kw.name}" and all its ${kw.aliases.length} alias(es)?`)) {
            return;
        }
        
        try {
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
            
            aliasState.keywords = aliasState.keywords.filter(k => k.id !== id);
            aliasState.expandedKeywords.delete(id);
            renderAliases();
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
        if (addAliasKeywordDialog) addAliasKeywordDialog.classList.add('hidden');
        if (nameInput) nameInput.value = "";
    }

    // Alias management event listeners
    if (elements.openAliasesBtn) {
        elements.openAliasesBtn.addEventListener('click', () => {
            if (aliasesDrawer) {
                aliasesDrawer.classList.add('open');
                loadAliases();
            }
        });
    }

    if (closeAliasesBtn) {
        closeAliasesBtn.addEventListener('click', () => {
            if (aliasesDrawer) {
                aliasesDrawer.classList.remove('open');
            }
        });
    }

    if (aliasSearchInput) {
        aliasSearchInput.addEventListener('input', (e) => {
            aliasState.searchQuery = e.target.value;
            renderAliases();
        });
    }

    if (aliasAddKeywordBtn) {
        aliasAddKeywordBtn.addEventListener('click', () => {
            if (addAliasKeywordDialog) {
                addAliasKeywordDialog.classList.remove('hidden');
                const nameInput = document.getElementById('new-alias-keyword-name');
                if (nameInput) nameInput.focus();
            }
        });
    }

    if (addAliasKeywordDialog) {
        const closeBtn = addAliasKeywordDialog.querySelector('.close-dialog-btn');
        if (closeBtn) {
            closeBtn.onclick = () => addAliasKeywordDialog.classList.add('hidden');
        }
        addAliasKeywordDialog.onclick = (e) => { 
            if (e.target === addAliasKeywordDialog) addAliasKeywordDialog.classList.add('hidden');
        };
    }

    if (aliasLangFilterBtns.length > 0) {
        aliasLangFilterBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                aliasLangFilterBtns.forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                const lang = btn.dataset.lang;
                aliasState.selectedLanguage = lang === 'all' ? null : lang;
                renderAliases();
            });
        });
    }

    if (confirmAddAliasKeywordBtn) {
        confirmAddAliasKeywordBtn.onclick = handleConfirmAddKeyword;
    }

    // Close drawer when clicking outside
    document.addEventListener('click', (e) => {
        if (aliasesDrawer && aliasesDrawer.classList.contains('open')) {
            const isInsideDrawer = aliasesDrawer.contains(e.target);
            const isButton = elements.openAliasesBtn && elements.openAliasesBtn.contains(e.target);
            const isModal = addAliasKeywordDialog && addAliasKeywordDialog.contains(e.target);
            
            if (!isInsideDrawer && !isButton && !isModal) {
                aliasesDrawer.classList.remove('open');
            }
        }
    });

    // Main search function
    async function handleSearch() {
        const keyword = elements.searchInput.value.trim();
        if (!keyword) return;

        state.lastKeyword = keyword;
        elements.searchBtn.disabled = true;
        elements.resultCountText.textContent = 'Searching...';

        try {
            const response = await fetch('/api/gdd/explainer/search', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ keyword })
            });

            const result = await response.json();

            if (!result.success || !result.choices || result.choices.length === 0) {
                elements.resultCountText.textContent = 'Found 0 result(s)';
                state.documents = [];
                state.storedResults = [];
                renderDocuments();
                updateUI();
                return;
            }

            // Parse backend response into document/section structure
            const documentsMap = new Map();
            
            result.choices.forEach((choice, idx) => {
                const storeItem = result.store_data[idx];
                if (!storeItem) return;

                const docId = storeItem.doc_id;
                const sectionHeading = storeItem.section_heading || '(No section)';
                
                // Extract doc name from choice label (format: "doc_name → section")
                const parts = choice.split(' → ');
                const docName = parts[0] || docId;
                const sectionTitle = parts[1] || sectionHeading;

                if (!documentsMap.has(docId)) {
                    documentsMap.set(docId, {
                        id: docId,
                        name: docName,
                        sections: []
                    });
                }

                const doc = documentsMap.get(docId);
                doc.sections.push({
                    id: `${docId}:${sectionHeading}`,
                    title: sectionTitle,
                    selected: false,
                    doc_id: docId,
                    section_heading: storeItem.section_heading,
                    choice_label: choice
                });
            });

            state.documents = Array.from(documentsMap.values());
            state.storedResults = result.store_data;
            
            elements.resultCountText.textContent = `Found ${result.choices.length} result(s)`;
            elements.headerResultCount.textContent = `(${result.choices.length})`;
            
            renderDocuments();
            updateUI();
            elements.explainBtn.disabled = false;

        } catch (error) {
            console.error('Search error:', error);
            elements.resultCountText.textContent = 'Search failed';
        } finally {
            elements.searchBtn.disabled = false;
        }
    }

    // Render documents with expandable sections
    function renderDocuments() {
        if (state.documents.length === 0) {
            elements.documentsList.innerHTML = '<p class="v0-placeholder-text">No results</p>';
            return;
        }

        elements.documentsList.innerHTML = state.documents.map(doc => {
            const selectedSections = doc.sections.filter(s => s.selected).length;
            const allSelected = doc.sections.length > 0 && doc.sections.every(s => s.selected);
            const partiallySelected = selectedSections > 0 && selectedSections < doc.sections.length;
            const isExpanded = state.expandedDocs.has(doc.id);

            return `
                <div class="v0-document-item">
                    <div class="v0-document-header" onclick="window.explainerV0.toggleDocument('${doc.id}')">
                        <button class="v0-expand-btn">
                            ${isExpanded 
                                ? '<svg class="v0-icon" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"></path></svg>'
                                : '<svg class="v0-icon" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m9 18 6-6-6-6"></path></svg>'
                            }
                        </button>
                        <input 
                            type="checkbox" 
                            class="v0-checkbox"
                            ${allSelected ? 'checked' : ''}
                            ${partiallySelected ? 'data-partial="true"' : ''}
                            onchange="window.explainerV0.toggleDocumentSelection('${doc.id}', this.checked)"
                            onclick="event.stopPropagation()"
                        />
                        <svg class="v0-icon" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"></path>
                            <polyline points="14 2 14 8 20 8"></polyline>
                        </svg>
                        <span class="v0-doc-name">${escapeHtml(doc.name)}</span>
                        <span class="v0-doc-count">(${selectedSections}/${doc.sections.length})</span>
                    </div>
                    ${isExpanded ? `
                        <div class="v0-sections-list">
                            ${doc.sections.map(section => {
                                const isActive = state.activePreviewId === section.id;
                                return `
                                    <div class="v0-section-item ${isActive ? 'v0-section-active' : ''}">
                                        <input 
                                            type="checkbox" 
                                            class="v0-checkbox"
                                            ${section.selected ? 'checked' : ''}
                                            onchange="window.explainerV0.toggleSection('${doc.id}', '${section.id}', this.checked)"
                                        />
                                        <span class="v0-section-title">${escapeHtml(section.title)}</span>
                                        <button 
                                            class="v0-preview-btn ${isActive ? 'v0-preview-btn-active' : ''}"
                                            onclick="window.explainerV0.handleSectionPreview('${doc.id}', '${section.id}')"
                                        >
                                            <svg class="v0-icon" xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                                <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path>
                                                <circle cx="12" cy="12" r="3"></circle>
                                            </svg>
                                            Preview
                                        </button>
                                    </div>
                                `;
                            }).join('')}
                        </div>
                    ` : ''}
                </div>
            `;
        }).join('');
    }

    // Toggle document expansion
    window.explainerV0 = window.explainerV0 || {};
    window.explainerV0.toggleDocument = function(docId) {
        if (state.expandedDocs.has(docId)) {
            state.expandedDocs.delete(docId);
        } else {
            state.expandedDocs.add(docId);
        }
        renderDocuments();
    };

    // Toggle document selection (all sections)
    window.explainerV0.toggleDocumentSelection = function(docId, selected) {
        const doc = state.documents.find(d => d.id === docId);
        if (doc) {
            doc.sections.forEach(section => {
                section.selected = selected;
            });
            renderDocuments();
            updateUI();
        }
    };

    // Toggle section selection
    window.explainerV0.toggleSection = function(docId, sectionId, selected) {
        const doc = state.documents.find(d => d.id === docId);
        if (doc) {
            const section = doc.sections.find(s => s.id === sectionId);
            if (section) {
                section.selected = selected;
                renderDocuments();
                updateUI();
            }
        }
    };

    // Handle section preview (placeholder - can be enhanced)
    window.explainerV0.handleSectionPreview = function(docId, sectionId) {
        if (state.activePreviewId === sectionId) {
            closePreview();
            return;
        }

        const doc = state.documents.find(d => d.id === docId);
        if (!doc) return;

        const section = doc.sections.find(s => s.id === sectionId);
        if (!section) return;

        state.activePreviewId = sectionId;
        state.sectionPreview = {
            docName: doc.name,
            sectionTitle: section.title,
            content: 'Section content preview - Click "Generate Explanation" to see full content.'
        };

        elements.previewDocName.textContent = doc.name;
        elements.previewSectionTitle.textContent = section.title;
        elements.previewContent.textContent = state.sectionPreview.content;
        elements.sectionPreviewContainer.style.display = 'block';

        renderDocuments(); // Re-render to show active state
    };

    function closePreview() {
        state.activePreviewId = null;
        state.sectionPreview = null;
        elements.sectionPreviewContainer.style.display = 'none';
        renderDocuments();
    }

    // Select all/none
    function handleSelectAll() {
        state.documents.forEach(doc => {
            doc.sections.forEach(section => {
                section.selected = true;
            });
        });
        renderDocuments();
        updateUI();
    }

    function handleSelectNone() {
        state.documents.forEach(doc => {
            doc.sections.forEach(section => {
                section.selected = false;
            });
        });
        renderDocuments();
        updateUI();
    }

    // Toggle results visibility
    function toggleResults() {
        state.resultsExpanded = !state.resultsExpanded;
        if (state.resultsExpanded) {
            elements.resultsContent.style.display = 'block';
            elements.chevronIcon.style.transform = 'rotate(0deg)';
        } else {
            elements.resultsContent.style.display = 'none';
            elements.chevronIcon.style.transform = 'rotate(180deg)';
        }
    }

    // Generate explanation
    async function handleGenerateExplanation() {
        if (!state.lastKeyword || state.storedResults.length === 0) {
            return;
        }

        const selectedChoices = [];
        state.documents.forEach(doc => {
            doc.sections.forEach(section => {
                if (section.selected && section.choice_label) {
                    selectedChoices.push(section.choice_label);
                }
            });
        });

        if (selectedChoices.length === 0) {
            alert('Please select at least one document/section to explain.');
            return;
        }

        elements.explainBtn.disabled = true;
        if (elements.genStatus) elements.genStatus.textContent = "Generating...";
        if (elements.explanationOutput) {
            elements.explanationOutput.style.display = 'flex';
            elements.explanationOutput.style.alignItems = 'center';
            elements.explanationOutput.style.justifyContent = 'center';
            elements.explanationOutput.innerHTML = '<p class="placeholder-text">Generating explanation...</p>';
        }

        try {
            const response = await fetch('/api/gdd/explainer/explain', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    keyword: state.lastKeyword,
                    selected_choices: selectedChoices,
                    stored_results: state.storedResults
                })
            });

            const result = await response.json();
            
            if (elements.genStatus) {
                elements.genStatus.textContent = result.success ? "✓ Completed" : "✕ Generation Failed";
                elements.genStatus.style.color = result.success ? "var(--status-success)" : "var(--status-error)";
            }

            if (!result.success) {
                if (elements.explanationOutput) {
                    elements.explanationOutput.style.display = 'block';
                    elements.explanationOutput.style.alignItems = 'stretch';
                    elements.explanationOutput.style.justifyContent = 'flex-start';
                    elements.explanationOutput.innerHTML = `<div class="placeholder-text"><p style="color:var(--status-error)">${result.explanation || 'Generation failed'}</p></div>`;
                }
                return;
            }

            // Explanation formatting (Previous Implementation)
            if (elements.explanationOutput) {
                elements.explanationOutput.style.display = 'block';
                elements.explanationOutput.style.alignItems = 'stretch';
                elements.explanationOutput.style.justifyContent = 'flex-start';
                elements.explanationOutput.innerHTML = `<div class="generated-explanation" style="color: var(--foreground)">${renderMarkdown(result.explanation || '', 'Explanation', state.lastKeyword)}</div>`;
            }

            // Source Chunks formatting (Previous Implementation)
            const chunks = result.source_chunks ? result.source_chunks.split('\n\n').filter(c => {
                const trimmed = c.trim();
                return trimmed && !trimmed.startsWith('### Source Chunks');
            }) : [];
            
            if (elements.chunksCountLabel) {
                elements.chunksCountLabel.textContent = `${chunks.length} chunks used`;
            }
            
            if (elements.sourceChunksOutput) {
                elements.sourceChunksOutput.innerHTML = chunks.map((chunk, idx) => `
                    <div class="source-chunk-card">
                        <div style="font-family: var(--font-mono); font-size: 11px; color: var(--muted-foreground); opacity: 0.8; margin-bottom: 6px;">CHUNK ${idx + 1}</div>
                        <div style="font-size: 12px; line-height: 1.5; color: rgba(0,0,0,0.7);">${chunk.replace(/^Chunk \d+:?\s*/i, '').replace(/^\*\*Chunk \d+\*\*.*?\n/i, '')}</div>
                    </div>
                `).join('');
            }

            // Metadata formatting (Previous Implementation)
            if (elements.metadataOutput) {
                const metaLines = result.metadata ? result.metadata.split('\n').filter(l => l.includes(': ')) : [];
                elements.metadataOutput.innerHTML = `
                    <div class="metadata-list">
                        ${metaLines.map(line => {
                            const [label, ...valParts] = line.split(': ');
                            return `
                                <div class="metadata-item">
                                    <span class="metadata-label">${escapeHtml(label)}</span>
                                    <span class="metadata-value">${escapeHtml(valParts.join(': '))}</span>
                                </div>
                            `;
                        }).join('')}
                        <div class="metadata-item">
                            <span class="metadata-label">Timestamp</span>
                            <span class="metadata-value">${new Date().toLocaleString()}</span>
                        </div>
                    </div>
                `;
            }

        } catch (error) {
            console.error('Error generating explanation:', error);
            if (elements.genStatus) {
                elements.genStatus.textContent = "Network Error";
                elements.genStatus.style.color = "var(--status-error)";
            }
            if (elements.explanationOutput) {
                elements.explanationOutput.innerHTML = `<p>Error: ${error.message}</p>`;
            }
        } finally {
            elements.explainBtn.disabled = false;
        }
    }

    // Update UI state
    function updateUI() {
        const totalSections = state.documents.reduce((sum, doc) => sum + doc.sections.length, 0);
        const selectedCount = state.documents.reduce((sum, doc) => 
            sum + doc.sections.filter(s => s.selected).length, 0
        );

        elements.selectedCountBadge.textContent = selectedCount;
        elements.selectAllCheckbox.checked = totalSections > 0 && selectedCount === totalSections;
        elements.selectNoneCheckbox.checked = selectedCount === 0;
    }

    // Utility functions
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    function renderMarkdown(text, stripHeading, keyword = '') {
        if (!text) return '';
        
        // RENDERING ORDER: Process on plain text BEFORE markdown conversion
        let processedText = text;
        
        // Step 1: Process *word* syntax from LLM (highlight important keywords/phrases)
        const highlightMarkers = [];
        let markerIndex = 0;
        processedText = processedText.replace(/\*([^*]+?)\*/g, (match, content) => {
            const marker = `__HIGHLIGHT_MARKER_${markerIndex}__`;
            highlightMarkers.push(`<span class="keyword-highlight">${content}</span>`);
            markerIndex++;
            return marker;
        });
        
        // Step 2: Highlight search keyword in plain text (case-insensitive, whole words only)
        if (keyword && keyword.trim()) {
            const keywordEscaped = keyword.trim().replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
            const keywordRegex = new RegExp(`\\b(${keywordEscaped})\\b`, 'gi');
            
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
            
            processedText = processedText.replace(keywordRegex, (match, offset) => {
                const matchStart = offset;
                const matchEnd = offset + match.length;
                
                for (const marker of existingMarkers) {
                    if ((matchStart >= marker.start && matchStart < marker.end) ||
                        (matchEnd > marker.start && matchEnd <= marker.end) ||
                        (matchStart <= marker.start && matchEnd >= marker.end)) {
                        return match;
                    }
                }
                
                const marker = `__HIGHLIGHT_MARKER_${markerIndex}__`;
                highlightMarkers.push(`<span class="keyword-highlight">${match}</span>`);
                markerIndex++;
                return marker;
            });
        }
        
        // Step 3: Strip duplicate headings that match the bubble title
        if (stripHeading) {
            const headingPatterns = [
                new RegExp(`^#+\\s*${stripHeading}\\s*$`, 'gim'),
                new RegExp(`^#+\\s*${stripHeading.replace(/\s+/g, '\\s+')}\\s*$`, 'gim')
            ];
            
            headingPatterns.forEach(pattern => {
                processedText = processedText.replace(pattern, '');
            });
            
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
        
        // Headers
        html = html.replace(/^### (.*$)/gim, '<h3>$1</h3>');
        html = html.replace(/^## (.*$)/gim, '<h2>$1</h2>');
        html = html.replace(/^# (.*$)/gim, '<h1>$1</h1>');
        
        // Markdown bold (**text**)
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

    function parseChunks(chunksText) {
        if (!chunksText) return [];
        return chunksText.split(/\n\n/).filter(c => c.trim() && !c.trim().startsWith('###'));
    }

    function parseMetadata(metadataText) {
        const metadata = {};
        if (!metadataText) return metadata;
        
        const lines = metadataText.split('\n');
        lines.forEach(line => {
            const match = line.match(/^- \*\*(.*?):\*\* (.*)/);
            if (match) {
                metadata[match[1].trim()] = match[2].trim();
            }
        });
        
        return metadata;
    }

    // Initialize
    updateUI();
});
