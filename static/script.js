document.addEventListener('DOMContentLoaded', () => {
    const auditBtn = document.getElementById('audit-btn');
    const regulationInput = document.getElementById('regulation-input');
    const loadingState = document.getElementById('loading-state');
    const loadingMessage = loadingState.querySelector('h3');
    const resultsSection = document.getElementById('results-section');
    const resultsContainer = document.getElementById('results-container');
    const errorState = document.getElementById('error-state');
    const errorMessage = document.getElementById('error-message');

    // Upload Elements
    const fileUpload = document.getElementById('file-upload');
    const fileName = document.getElementById('file-name');
    const uploadBtn = document.getElementById('upload-btn');
    const uploadStatus = document.getElementById('upload-status');

    let currentCard = null;
    let currentContentDiv = null;

    if (fileUpload) {
        fileUpload.addEventListener('change', (e) => {
            if (e.target.files.length > 0) {
                fileName.textContent = e.target.files[0].name;
                uploadBtn.disabled = false;
            } else {
                fileName.textContent = 'Choose a file or drag & drop it here';
                uploadBtn.disabled = true;
            }
        });

        uploadBtn.addEventListener('click', async () => {
            const file = fileUpload.files[0];
            if (!file) return;

            uploadBtn.disabled = true;
            uploadBtn.textContent = 'Uploading...';
            uploadStatus.className = 'hidden';
            
            const formData = new FormData();
            formData.append('file', file);

            try {
                const response = await fetch('/api/upload', {
                    method: 'POST',
                    body: formData
                });
                
                const result = await response.json();
                
                uploadStatus.className = 'upload-status-msg ' + (result.type === 'success' ? 'upload-success' : 'upload-error');
                uploadStatus.innerHTML = result.type === 'success' 
                    ? `<i class="fa-solid fa-check-circle"></i> ${result.message}`
                    : `<i class="fa-solid fa-triangle-exclamation"></i> ${result.message}`;
                
                if (result.type === 'success') {
                    setTimeout(() => {
                        fileUpload.value = '';
                        fileName.textContent = 'Choose a file or drag & drop it here';
                        uploadBtn.disabled = true;
                    }, 3000);
                }
            } catch (error) {
                uploadStatus.className = 'upload-status-msg upload-error';
                uploadStatus.innerHTML = `<i class="fa-solid fa-circle-exclamation"></i> Network error: Could not upload document.`;
            } finally {
                uploadBtn.textContent = 'Upload to Pinecone';
                if (!fileUpload.value) uploadBtn.disabled = true;
                else uploadBtn.disabled = false;
            }
        });
    }

    auditBtn.addEventListener('click', async () => {
        const text = regulationInput.value.trim();
        
        if (!text) {
            regulationInput.focus();
            regulationInput.style.borderColor = 'var(--danger)';
            setTimeout(() => regulationInput.style.borderColor = '', 1000);
            return;
        }

        // Reset UI
        resultsSection.classList.add('hidden');
        errorState.classList.add('hidden');
        loadingState.classList.remove('hidden');
        loadingMessage.textContent = 'Agent is starting...';
        resultsContainer.innerHTML = '';
        auditBtn.disabled = true;
        auditBtn.querySelector('span').textContent = 'Auditing...';
        
        currentCard = null;
        currentContentDiv = null;

        try {
            const response = await fetch('/api/audit/stream', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ regulation_text: text })
            });

            if (!response.ok) {
                throw new Error('Server error occurred during audit.');
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder("utf-8");
            let buffer = "";
            
            // Show results section immediately to let cards populate
            resultsSection.classList.remove('hidden');
            
            setTimeout(() => {
                resultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }, 100);

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                
                buffer += decoder.decode(value, { stream: true });
                
                let lines = buffer.split('\n\n');
                buffer = lines.pop(); // keep the incomplete chunk
                
                for (let line of lines) {
                    if (line.startsWith('data: ')) {
                        try {
                            const data = JSON.parse(line.substring(6));
                            handleStreamEvent(data);
                        } catch (e) {
                            console.error("Error parsing event data", e);
                        }
                    }
                }
            }

            loadingState.classList.add('hidden');

        } catch (error) {
            console.error("Audit error:", error);
            loadingState.classList.add('hidden');
            errorState.classList.remove('hidden');
            errorMessage.textContent = error.message || "A network or timeout error occurred while waiting for the LLM.";
        } finally {
            auditBtn.disabled = false;
            auditBtn.querySelector('span').textContent = 'Run Full Audit';
        }
    });

    function handleStreamEvent(data) {
        if (data.type === 'error') {
            throw new Error(data.message);
        } else if (data.type === 'status') {
            loadingMessage.textContent = data.message;
        } else if (data.type === 'questions_extracted') {
            // Setup ready for evaluation
        } else if (data.type === 'token') {
            if (data.stage === 'evaluation') {
                if (!currentCard || currentCard.dataset.question !== data.question) {
                    createNewCard(data.question);
                }
                if (currentContentDiv) {
                    // Store the raw markdown string on the div
                    if (!currentContentDiv.rawMarkdown) {
                        currentContentDiv.rawMarkdown = '';
                    }
                    currentContentDiv.rawMarkdown += data.chunk;
                    // Format the entire accumulated text to correctly handle markdown spanning multiple chunks
                    let formattedText = escapeHtml(currentContentDiv.rawMarkdown).replace(/\n/g, '<br>');
                    currentContentDiv.innerHTML = formatMarkdown(formattedText);
                    updateCardStatus(currentCard, currentContentDiv.innerHTML);
                }
            }
        } else if (data.type === 'done') {
            loadingState.classList.add('hidden');
        }
    }

    function createNewCard(question) {
        currentCard = document.createElement('div');
        currentCard.className = 'result-card';
        currentCard.dataset.question = question;
        
        currentCard.innerHTML = `
            <div class="status-badge" style="background: rgba(0,0,0,0.1); color: var(--text-secondary);">ANALYZING...</div>
            <div class="question-title"><i class="fa-solid fa-circle-question" style="color: var(--text-secondary); margin-right: 8px;"></i> ${escapeHtml(question)}</div>
            <div class="assessment-content"></div>
        `;
        
        resultsContainer.appendChild(currentCard);
        currentContentDiv = currentCard.querySelector('.assessment-content');
    }

    function updateCardStatus(card, htmlContent) {
        const text = htmlContent.toUpperCase();
        let statusClass = '';
        let statusText = 'ANALYZING...';
        
        if (text.includes('STATUS: COMPLIANT') || (text.includes('COMPLIANT') && !text.includes('NON-COMPLIANT'))) {
            statusClass = 'status-compliant';
            statusText = 'COMPLIANT';
        } else if (text.includes('STATUS: NON-COMPLIANT') || text.includes('NON-COMPLIANT')) {
            statusClass = 'status-non-compliant';
            statusText = 'NON-COMPLIANT';
        } else if (text.includes('LACK OF EVIDENCE')) {
            statusClass = 'status-lack-of-evidence';
            statusText = 'LACK OF EVIDENCE';
        }

        if (statusClass) {
            card.className = `result-card ${statusClass}`;
            const badge = card.querySelector('.status-badge');
            badge.textContent = statusText;
            badge.style = ''; // remove inline styles
        }
    }

    function escapeHtml(unsafe) {
        return unsafe
             .replace(/&/g, "&amp;")
             .replace(/</g, "&lt;")
             .replace(/>/g, "&gt;")
             .replace(/"/g, "&quot;")
             .replace(/'/g, "&#039;");
    }

    function formatMarkdown(text) {
        return text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    }
});
