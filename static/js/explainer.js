// Document Explainer functionality (Tab 2)
// Exact replication of keyword_extractor Gradio app behavior using vanilla JS

document.addEventListener('DOMContentLoaded', function() {
    // Only initialize if we're on the GDD tab page
    const explainerTab = document.getElementById('tab-explainer');
    if (!explainerTab) {
        return;
    }
    
    // Tab switching logic
    const tabBtns = document.querySelectorAll('.tab-btn');
    const tabContents = document.querySelectorAll('.tab-content');
    
    tabBtns.forEach(btn => {
        btn.addEventListener('click', function() {
            const tabName = this.getAttribute('data-tab');
            
            // Update active tab button
            tabBtns.forEach(b => b.classList.remove('active'));
            this.classList.add('active');
            
            // Update active tab content
            tabContents.forEach(content => {
                content.classList.remove('active');
                content.style.display = 'none';
            });
            
            const targetTab = document.getElementById(`tab-${tabName}`);
            if (targetTab) {
                targetTab.classList.add('active');
                targetTab.style.display = 'block';
            }
        });
    });
    
    // Document Explainer elements
    const explainerKeyword = document.getElementById('explainer-keyword');
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
    
    // Initialize button state
    updateGenerateButtonState();
    
    async function searchForExplainer() {
        const keyword = explainerKeyword.value.trim();
        
        if (!keyword) {
            explainerResultsContainer.style.display = 'none';
            resultsCount.style.display = 'none';
            storedResults = [];
            updateGenerateButtonState();
            return;
        }
        
        try {
            explainerSearchBtn.disabled = true;
            
            const response = await fetch('/api/gdd/explainer/search', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ keyword: keyword })
            });
            
            const result = await response.json();
            
            if (!result.success) {
                explainerResultsContainer.style.display = 'none';
                resultsCount.style.display = 'none';
                storedResults = [];
                lastSearchKeyword = null;
                updateGenerateButtonState();
                return;
            }
            
            // Update stored results
            storedResults = result.store_data || [];
            lastSearchKeyword = keyword;
            
            // Clear previous checkboxes and render new ones
            renderCheckboxes(result.choices || []);
            
            // Show results container and count
            if (result.choices && result.choices.length > 0) {
                const count = result.choices.length;
                resultsCount.textContent = `Found ${count} result(s).`;
                resultsCount.style.display = 'block';
                explainerResultsContainer.style.display = 'block';
                updateGenerateButtonState();
            } else {
                explainerResultsContainer.style.display = 'none';
                resultsCount.style.display = 'none';
                updateGenerateButtonState();
            }
            
        } catch (error) {
            console.error('Error in search:', error);
            explainerResultsContainer.style.display = 'none';
            resultsCount.style.display = 'none';
            storedResults = [];
            updateGenerateButtonState();
        } finally {
            explainerSearchBtn.disabled = false;
        }
    }
    
    function renderCheckboxes(choices) {
        explainerResultsCheckboxes.innerHTML = '';
        
        if (!choices || choices.length === 0) {
            return;
        }
        
        choices.forEach((choice, index) => {
            const documentItem = document.createElement('div');
            documentItem.className = 'document-item';
            
            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.id = `checkbox-${index}`;
            checkbox.value = choice;
            checkbox.name = 'explainer-choice';
            checkbox.addEventListener('change', updateGenerateButtonState);
            checkbox.addEventListener('change', updateSelectAllNoneState);
            
            const label = document.createElement('label');
            label.htmlFor = `checkbox-${index}`;
            label.textContent = choice;
            
            documentItem.appendChild(checkbox);
            documentItem.appendChild(label);
            explainerResultsCheckboxes.appendChild(documentItem);
        });
        
        // Reset select all/none checkboxes
        selectAllCheckbox.checked = false;
        selectNoneCheckbox.checked = false;
    }
    
    function getSelectedChoices() {
        const checkboxes = explainerResultsCheckboxes.querySelectorAll('input[type="checkbox"][name="explainer-choice"]:checked');
        return Array.from(checkboxes).map(cb => cb.value);
    }
    
    async function generateExplanation() {
        const keyword = explainerKeyword.value.trim();
        
        if (!keyword) {
            explanationOutput.innerHTML = '<p class="placeholder-text">Please enter a keyword first.</p>';
            sourceChunksOutput.innerHTML = '<p class="placeholder-text">No source chunks yet.</p>';
            metadataOutput.innerHTML = '<p class="placeholder-text">No metadata yet.</p>';
            return;
        }
        
        if (!storedResults || storedResults.length === 0) {
            explanationOutput.innerHTML = '<p class="placeholder-text">Please search for a keyword first.</p>';
            sourceChunksOutput.innerHTML = '<p class="placeholder-text">No source chunks yet.</p>';
            metadataOutput.innerHTML = '<p class="placeholder-text">No metadata yet.</p>';
            return;
        }
        
        const selectedChoices = getSelectedChoices();
        
        if (!selectedChoices || selectedChoices.length === 0) {
            explanationOutput.innerHTML = '<p class="placeholder-text">Please select at least one document/section to explain.</p>';
            sourceChunksOutput.innerHTML = '<p class="placeholder-text">No source chunks yet.</p>';
            metadataOutput.innerHTML = '<p class="placeholder-text">No metadata yet.</p>';
            return;
        }
        
        try {
            explainBtn.disabled = true;
            explanationOutput.innerHTML = '<p>Generating explanation...</p>';
            sourceChunksOutput.innerHTML = '<p class="placeholder-text">No source chunks yet.</p>';
            metadataOutput.innerHTML = '<p class="placeholder-text">No metadata yet.</p>';
            
            const response = await fetch('/api/gdd/explainer/explain', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    keyword: keyword,
                    selected_choices: selectedChoices,
                    stored_results: storedResults
                })
            });
            
            const result = await response.json();
            
            if (!result.success) {
                explanationOutput.innerHTML = `<p>${result.explanation || 'Error occurred.'}</p>`;
                sourceChunksOutput.innerHTML = '<p class="placeholder-text">No source chunks yet.</p>';
                metadataOutput.innerHTML = '<p class="placeholder-text">No metadata yet.</p>';
                return;
            }
            
            // Render markdown outputs (strip duplicate headings)
            explanationOutput.innerHTML = renderMarkdown(result.explanation || '', 'Explanation');
            sourceChunksOutput.innerHTML = renderMarkdown(result.source_chunks || '', 'Source Chunks');
            metadataOutput.innerHTML = renderMarkdown(result.metadata || '', 'Metadata');
            
        } catch (error) {
            console.error('Error generating explanation:', error);
            explanationOutput.innerHTML = `<p>❌ Error: ${error.message}</p>`;
            sourceChunksOutput.innerHTML = '<p class="placeholder-text">No source chunks yet.</p>';
            metadataOutput.innerHTML = '<p class="placeholder-text">No metadata yet.</p>';
        } finally {
            explainBtn.disabled = false;
            updateGenerateButtonState();
        }
    }
    
    async function handleSelectAll() {
        if (selectAllCheckbox.checked) {
            selectNoneCheckbox.checked = false;
            if (!storedResults || storedResults.length === 0) {
                selectAllCheckbox.checked = false;
                return;
            }
            
            try {
                const response = await fetch('/api/gdd/explainer/select-all', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        stored_results: storedResults
                    })
                });
                
                const result = await response.json();
                
                // Check all checkboxes
                const checkboxes = explainerResultsCheckboxes.querySelectorAll('input[type="checkbox"][name="explainer-choice"]');
                const choices = result.choices || [];
                
                checkboxes.forEach(checkbox => {
                    if (choices.includes(checkbox.value)) {
                        checkbox.checked = true;
                    }
                });
                
                updateGenerateButtonState();
            } catch (error) {
                console.error('Error selecting all:', error);
                selectAllCheckbox.checked = false;
            }
        }
    }
    
    function handleSelectNone() {
        if (selectNoneCheckbox.checked) {
            selectAllCheckbox.checked = false;
            const checkboxes = explainerResultsCheckboxes.querySelectorAll('input[type="checkbox"][name="explainer-choice"]');
            checkboxes.forEach(checkbox => {
                checkbox.checked = false;
            });
            updateGenerateButtonState();
        }
    }
    
    function updateSelectAllNoneState() {
        const checkboxes = explainerResultsCheckboxes.querySelectorAll('input[type="checkbox"][name="explainer-choice"]');
        const checkedCount = explainerResultsCheckboxes.querySelectorAll('input[type="checkbox"][name="explainer-choice"]:checked').length;
        const totalCount = checkboxes.length;
        
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
    
    function renderMarkdown(text, stripHeading) {
        if (!text) return '';
        
        // Simple markdown rendering (for better results, consider using marked.js)
        let html = text;
        
        // Strip duplicate headings that match the bubble title
        if (stripHeading) {
            // Remove headings that exactly match the bubble title (case-insensitive)
            const headingPatterns = [
                new RegExp(`^#+\\s*${stripHeading}\\s*$`, 'gim'),
                new RegExp(`^#+\\s*${stripHeading.replace(/\s+/g, '\\s+')}\\s*$`, 'gim')
            ];
            
            headingPatterns.forEach(pattern => {
                html = html.replace(pattern, '');
            });
            
            // Also remove if it's the first line and matches
            const lines = html.split('\n');
            if (lines.length > 0) {
                const firstLine = lines[0].trim();
                const headingMatch = firstLine.match(/^#+\s*(.+)$/i);
                if (headingMatch && headingMatch[1].trim().toLowerCase() === stripHeading.toLowerCase()) {
                    lines.shift();
                    html = lines.join('\n');
                }
            }
        }
        
        // Headers
        html = html.replace(/^### (.*$)/gim, '<h3>$1</h3>');
        html = html.replace(/^## (.*$)/gim, '<h2>$1</h2>');
        html = html.replace(/^# (.*$)/gim, '<h1>$1</h1>');
        
        // Bold
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
        
        return html;
    }
});


