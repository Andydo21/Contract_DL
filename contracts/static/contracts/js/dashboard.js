document.addEventListener('DOMContentLoaded', () => {
    const listContainer = document.getElementById('contracts-list-container');
    const detailPanel = document.getElementById('analysis-detail-panel');
    
    // Modal Elements
    const uploadModal = document.getElementById('upload-modal');
    const openUploadBtn = document.getElementById('btn-open-upload');
    const closeUploadBtn = document.getElementById('btn-close-upload');
    const cancelUploadBtn = document.getElementById('btn-cancel-upload');
    const uploadForm = document.getElementById('upload-form');
    const scannerLoader = document.getElementById('scanner-loader');
    const fileInput = document.getElementById('file-input');
    const fileDropZone = document.getElementById('file-drop-zone');
    const fileDropText = document.getElementById('file-drop-text');

    let currentContractId = null;

    // Load Contracts list
    async function loadContracts(selectedId = null) {
        try {
            const res = await fetch('/api/contracts/');
            if (!res.ok) throw new Error("Failed to fetch contracts");
            const data = await res.json();
            
            renderStats(data);
            
            if (data.length === 0) {
                listContainer.innerHTML = `<div style="text-align: center; padding: 40px; color: var(--text-muted)">
                    <i class="fa-regular fa-folder-open" style="font-size: 32px; margin-bottom: 12px;"></i>
                    <p>No contracts uploaded yet.</p>
                </div>`;
                return;
            }

            listContainer.innerHTML = '';
            data.forEach(c => {
                const card = document.createElement('div');
                card.className = `contract-card ${selectedId == c.id ? 'active' : ''}`;
                card.dataset.id = c.id;

                // Risk display
                let riskClass = 'score-low';
                let indicatorClass = 'bg-low';
                let riskLabel = 'Low Risk';
                
                if (c.risk_score !== null) {
                    if (c.risk_score >= 80) {
                        riskClass = 'score-high';
                        indicatorClass = 'bg-high';
                        riskLabel = `Score: ${c.risk_score}% (High)`;
                    } else if (c.risk_score >= 50) {
                        riskClass = 'score-medium';
                        indicatorClass = 'bg-medium';
                        riskLabel = `Score: ${c.risk_score}% (Medium)`;
                    } else {
                        riskClass = 'score-low';
                        indicatorClass = 'bg-low';
                        riskLabel = `Score: ${c.risk_score}% (Low)`;
                    }
                } else {
                    riskLabel = 'Pending AI Run';
                    riskClass = 'score-low';
                    indicatorClass = 'bg-low';
                    if (c.status === 'ANALYZING') {
                        riskLabel = 'Analyzing...';
                    }
                }

                card.innerHTML = `
                    <div class="card-top">
                        <span class="card-code">${c.contract_code}</span>
                        <span class="status-badge status-${c.status.toLowerCase()}">${c.status}</span>
                    </div>
                    <div class="card-title">${c.title}</div>
                    <div class="card-footer">
                        <span>$${c.contract_value !== null && c.contract_value !== undefined ? c.contract_value.toLocaleString() : '0'}</span>
                        <div class="card-score ${riskClass}">
                            <div class="score-indicator ${indicatorClass}"></div>
                            <span>${riskLabel}</span>
                        </div>
                    </div>
                `;
                
                card.addEventListener('click', () => {
                    document.querySelectorAll('.contract-card').forEach(cc => cc.classList.remove('active'));
                    card.classList.add('active');
                    showContractDetail(c.id);
                });

                listContainer.appendChild(card);
            });

            // Auto-select active if set
            if (selectedId) {
                const activeCard = listContainer.querySelector(`[data-id="${selectedId}"]`);
                if (activeCard) activeCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            }

        } catch (err) {
            console.error(err);
            listContainer.innerHTML = `<div style="text-align: center; padding: 40px; color: var(--risk-high)">
                <i class="fa-solid fa-triangle-exclamation" style="font-size: 32px; margin-bottom: 12px;"></i>
                <p>Error loading registry database.</p>
            </div>`;
        }
    }

    // Stats calculator
    function renderStats(contracts) {
        const total = contracts.length;
        let highRiskCount = 0;
        let pendingCount = 0;

        contracts.forEach(c => {
            if (c.risk_score && c.risk_score >= 80) highRiskCount++;
            if (c.status === 'ANALYZED') pendingCount++;
        });

        document.getElementById('stat-total').innerText = total;
        document.getElementById('stat-high-risk').innerText = highRiskCount;
        document.getElementById('stat-pending').innerText = pendingCount;
    }

    // Load single contract details
    async function showContractDetail(id) {
        currentContractId = id;
        detailPanel.innerHTML = `
            <div style="display: flex; align-items: center; justify-content: center; height: 100%; color: var(--text-muted);">
                <i class="fa-solid fa-circle-notch fa-spin" style="font-size: 32px; margin-bottom: 12px;"></i>
            </div>
        `;

        try {
            const res = await fetch(`/api/contracts/${id}/`);
            if (!res.ok) throw new Error("Failed to fetch contract details");
            const data = await res.json();

            // Render risk assessment tab content
            let analysisHTML = '';
            if (data.analysis) {
                const score = data.analysis.overall_score;
                let strokeColor = '#10b981';
                let scoreStatus = 'Low Risk';
                let scoreStatusClass = 'score-low';
                
                if (score >= 80) {
                    strokeColor = '#ef4444';
                    scoreStatus = 'High Risk';
                    scoreStatusClass = 'score-high';
                } else if (score >= 50) {
                    strokeColor = '#f97316';
                    scoreStatus = 'Medium Risk';
                    scoreStatusClass = 'score-medium';
                }

                // SVG Circular gauge dashoffset
                const r = 36;
                const circumference = 2 * Math.PI * r; // ~226.2
                const dashoffset = circumference - (score / 100) * circumference;

                // Findings list HTML
                let findingsHTML = '';
                if (data.findings && data.findings.length > 0) {
                    data.findings.forEach(f => {
                        findingsHTML += `
                            <div class="finding-item">
                                <div class="finding-header" onclick="toggleFinding(this)">
                                    <div class="finding-left">
                                        <span class="risk-badge badge-${f.risk_level.toLowerCase()}">${f.risk_level}</span>
                                        <span>${f.risk_name}</span>
                                    </div>
                                    <i class="fa-solid fa-chevron-down" style="color: var(--text-muted); font-size: 12px; transition: transform 0.2s;"></i>
                                </div>
                                <div class="finding-body" style="display: none;">
                                    <div class="finding-block">
                                        <div class="block-label">Violated Clause</div>
                                        <div class="block-text" style="font-weight: 500; color: #ffffff;">${f.clause_title}</div>
                                    </div>
                                    <div class="finding-block">
                                        <div class="block-label">Risk Explanation</div>
                                        <div class="block-text">${f.explanation}</div>
                                    </div>
                                    ${f.recommendation ? `
                                    <div class="rec-box">
                                        <div class="block-label" style="color: var(--risk-low);"><i class="fa-solid fa-lightbulb"></i> AI Recommendation</div>
                                        <div class="block-text">${f.recommendation}</div>
                                    </div>` : ''}
                                </div>
                            </div>
                        `;
                    });
                } else {
                    findingsHTML = `<p style="color: var(--text-muted); font-style: italic;">No specific risks identified.</p>`;
                }

                // Reviews list HTML
                let reviewsHTML = '';
                if (data.reviews && data.reviews.length > 0) {
                    data.reviews.forEach(r => {
                        reviewsHTML += `
                            <div class="review-card">
                                <div class="review-header">
                                    <div class="reviewer-info">
                                        <i class="fa-solid fa-user-tie" style="color: var(--accent-primary);"></i>
                                        <span>${r.reviewer}</span>
                                    </div>
                                    <span class="risk-badge badge-${r.final_risk_level.toLowerCase()}">${r.final_risk_level} Decision</span>
                                </div>
                                <div class="review-comment">"${r.comment}"</div>
                            </div>
                        `;
                    });
                }

                // Show review form only if contract is not approved, or show a review submission form
                const showReviewForm = data.status === 'ANALYZED';

                analysisHTML = `
                    <h4 class="section-title"><i class="fa-solid fa-chart-line"></i> Risk Assessment Summary</h4>
                    <div class="gauge-area" style="margin-bottom: 20px;">
                        <div class="gauge-circle">
                            <svg>
                                <circle class="bg-circle" cx="40" cy="40" r="${r}"></circle>
                                <circle class="val-circle" cx="40" cy="40" r="${r}" style="stroke-dashoffset: ${dashoffset}; stroke: ${strokeColor};"></circle>
                            </svg>
                            <div class="gauge-text">${score}%</div>
                        </div>
                        <div class="gauge-desc">
                            <div class="gauge-label">Overall AI Threat Level</div>
                            <div class="gauge-status ${scoreStatusClass}">${scoreStatus}</div>
                        </div>
                    </div>

                    <div class="summary-box">
                        ${data.analysis.summary}
                    </div>

                    <h4 class="section-title"><i class="fa-solid fa-magnifying-glass-warning"></i> Detected Clause Violations</h4>
                    <div class="findings-list">
                        ${findingsHTML}
                    </div>

                    <div class="reviews-section">
                        <h4 class="section-title"><i class="fa-solid fa-user-shield"></i> Legal Expert Review</h4>
                        ${reviewsHTML}
                        
                        ${showReviewForm ? `
                        <form class="review-form" id="submit-review-form">
                            <div class="form-group">
                                <label class="form-label">Review Verdict *</label>
                                <select class="form-control" name="final_risk_level" required>
                                    <option value="LOW">LOW RISK - Approved</option>
                                    <option value="MEDIUM" selected>MEDIUM RISK - Mitigation Required</option>
                                    <option value="HIGH">HIGH RISK - Rejection/Renegotiate</option>
                                </select>
                            </div>
                            <div class="form-group">
                                <label class="form-label">Expert Commentary *</label>
                                <textarea class="form-control" name="comment" placeholder="Provide legal reasoning and next action steps..." required></textarea>
                            </div>
                            <button type="submit" class="btn" style="align-self: flex-end; margin-top: 8px;">
                                <i class="fa-solid fa-signature"></i> Sign & Submit Review
                            </button>
                        </form>
                        ` : `
                        <div style="display: flex; gap: 8px; align-items: center; color: var(--risk-low); font-size: 13.5px; background: rgba(16,185,129,0.05); padding: 12px; border-radius: 8px; border: 1px dashed rgba(16,185,129,0.2);">
                            <i class="fa-solid fa-circle-check"></i>
                            <span>Expert review has been successfully submitted and the contract status has been marked as <strong>Approved</strong>.</span>
                        </div>
                        `}
                    </div>
                `;
            } else {
                analysisHTML = `<div style="text-align: center; color: var(--text-muted); padding: 24px;">
                    <i class="fa-solid fa-microchip-ai" style="font-size: 32px; margin-bottom: 8px;"></i>
                    <p>AI Analysis is still in progress...</p>
                </div>`;
            }

            // Render original clauses list HTML
            let clausesHTML = '';
            if (data.clauses && data.clauses.length > 0) {
                data.clauses.forEach(cl => {
                    clausesHTML += `
                        <div class="clause-item">
                            <div class="clause-title-text">
                                <i class="fa-solid fa-paragraph" style="color: var(--accent-primary);"></i>
                                <span>${cl.title}</span>
                            </div>
                            <div class="clause-body-text">${cl.content.replace(/\n/g, '<br>')}</div>
                        </div>
                    `;
                });
            } else {
                clausesHTML = `<p style="color: var(--text-muted); font-style: italic; text-align: center; padding: 40px 0;">No clauses found in this contract.</p>`;
            }

            // Render the full detail panel structure
            detailPanel.innerHTML = `
                <div class="analysis-header">
                    <div class="analysis-title-area">
                        <h2 class="analysis-title">${data.title}</h2>
                        <div class="analysis-meta">
                            <div class="meta-tag"><i class="fa-solid fa-barcode"></i> ${data.contract_code}</div>
                            <div class="meta-tag"><i class="fa-solid fa-tag"></i> ${data.contract_type}</div>
                            <div class="meta-tag"><i class="fa-solid fa-dollar-sign"></i> ${data.contract_value !== null && data.contract_value !== undefined ? data.contract_value.toLocaleString() : '0'}</div>
                            ${data.start_date ? `<div class="meta-tag"><i class="fa-solid fa-calendar-days"></i> ${data.start_date} to ${data.end_date}</div>` : ''}
                        </div>
                    </div>
                    <div style="display: flex; gap: 8px;">
                        <a href="/contracts/${data.id}/" class="btn" style="background: var(--accent-primary); color: #ffffff; text-decoration: none;">
                            <i class="fa-solid fa-expand"></i> Full Reader Page
                        </a>
                        ${data.file_path ? `
                        <a href="${data.file_path}" target="_blank" class="btn" style="background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); color: var(--text-main); box-shadow: none; text-decoration: none;">
                            <i class="fa-solid fa-file-pdf"></i> Download PDF
                        </a>` : ''}
                    </div>
                </div>

                <div class="tabs-header">
                    <button class="tab-btn active" id="btn-tab-analysis"><i class="fa-solid fa-chart-line"></i> Risk Assessment</button>
                    <button class="tab-btn" id="btn-tab-clauses"><i class="fa-solid fa-file-invoice"></i> Original Clauses (${data.clauses ? data.clauses.length : 0})</button>
                    <button class="tab-btn" id="btn-tab-fulltext"><i class="fa-solid fa-file-lines"></i> Full Document</button>
                </div>

                <div id="tab-analysis" class="tab-content active">
                    ${analysisHTML}
                </div>

                <div id="tab-clauses" class="tab-content">
                    <div class="clauses-list">
                        ${clausesHTML}
                    </div>
                </div>

                <div id="tab-fulltext" class="tab-content">
                    <pre class="doc-preview-container">${data.raw_content || 'No content available.'}</pre>
                </div>
            `;

            // Bind Tab Navigation Events
            const tabAnalysisBtn = document.getElementById('btn-tab-analysis');
            const tabClausesBtn = document.getElementById('btn-tab-clauses');
            const tabFulltextBtn = document.getElementById('btn-tab-fulltext');
            
            const tabAnalysisContent = document.getElementById('tab-analysis');
            const tabClausesContent = document.getElementById('tab-clauses');
            const tabFulltextContent = document.getElementById('tab-fulltext');

            function deactivateAllTabs() {
                tabAnalysisBtn.classList.remove('active');
                tabClausesBtn.classList.remove('active');
                tabFulltextBtn.classList.remove('active');
                
                tabAnalysisContent.classList.remove('active');
                tabClausesContent.classList.remove('active');
                tabFulltextContent.classList.remove('active');
            }

            tabAnalysisBtn.addEventListener('click', () => {
                deactivateAllTabs();
                tabAnalysisBtn.classList.add('active');
                tabAnalysisContent.classList.add('active');
            });

            tabClausesBtn.addEventListener('click', () => {
                deactivateAllTabs();
                tabClausesBtn.classList.add('active');
                tabClausesContent.classList.add('active');
            });

            tabFulltextBtn.addEventListener('click', () => {
                deactivateAllTabs();
                tabFulltextBtn.classList.add('active');
                tabFulltextContent.classList.add('active');
            });


            // Bind Review Form Event if present
            const reviewForm = document.getElementById('submit-review-form');
            if (reviewForm) {
                reviewForm.addEventListener('submit', async (e) => {
                    e.preventDefault();
                    const final_risk_level = reviewForm.final_risk_level.value;
                    const comment = reviewForm.comment.value;
                    
                    try {
                        const rRes = await fetch(`/api/analyses/${data.analysis.id}/review/`, {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json'
                            },
                            body: JSON.stringify({ final_risk_level, comment })
                        });
                        
                        const rData = await rRes.json();
                        if (rData.success) {
                            // Reload details and list to update status
                            showContractDetail(currentContractId);
                            loadContracts(currentContractId);
                        } else {
                            alert("Error submitting review: " + (rData.error || "Unknown error"));
                        }
                    } catch (err) {
                        console.error(err);
                        alert("Failed to submit review request.");
                    }
                });
            }

        } catch (err) {
            console.error(err);
            detailPanel.innerHTML = `
                <div class="empty-state" style="color: var(--risk-high)">
                    <i class="fa-solid fa-triangle-exclamation" style="font-size: 64px;"></i>
                    <h2>Failed to Load Details</h2>
                    <p>An error occurred retrieving database records for this contract ID.</p>
                </div>
            `;
        }
    }

    // Modal Interactions
    openUploadBtn.addEventListener('click', () => {
        uploadForm.reset();
        fileDropText.innerHTML = 'Drag and drop file here, or click to choose file';
        uploadModal.classList.add('active');
    });

    function closeModal() {
        uploadModal.classList.remove('active');
    }

    closeUploadBtn.addEventListener('click', closeModal);
    cancelUploadBtn.addEventListener('click', closeModal);

    // Drag and drop events
    fileInput.addEventListener('change', () => {
        if (fileInput.files.length > 0) {
            fileDropText.innerHTML = `<strong>Selected file:</strong> ${fileInput.files[0].name}`;
        }
    });

    fileDropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        fileDropZone.classList.add('dragover');
    });

    fileDropZone.addEventListener('dragleave', () => {
        fileDropZone.classList.remove('dragover');
    });

    fileDropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        fileDropZone.classList.remove('dragover');
        if (e.dataTransfer.files.length > 0) {
            fileInput.files = e.dataTransfer.files;
            fileDropText.innerHTML = `<strong>Selected file:</strong> ${fileInput.files[0].name}`;
        }
    });

    // Form Submit
    uploadForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const fileSelected = fileInput.files.length > 0;
        const rawContentVal = uploadForm.raw_content.value.trim();
        
        if (!fileSelected && !rawContentVal) {
            alert("Please either upload a contract file or paste the contract text.");
            return;
        }

        const formData = new FormData(uploadForm);
        
        // Show AI Scanner loader
        scannerLoader.classList.add('active');
        
        try {
            const res = await fetch('/api/contracts/', {
                method: 'POST',
                body: formData
            });
            
            const data = await res.json();
            
            // Simulate analysis lag slightly to let the animation play beautifully
            setTimeout(() => {
                scannerLoader.classList.remove('active');
                closeModal();
                
                if (data.success) {
                    loadContracts(data.contract_id);
                    showContractDetail(data.contract_id);
                } else {
                    alert("Upload failed: " + (data.error || "Unknown error"));
                }
            }, 2500); // 2.5s scan duration for maximum user experience

        } catch (err) {
            scannerLoader.classList.remove('active');
            console.error(err);
            alert("Network error: Failed to upload contract.");
        }
    });

    // Init load
    loadContracts();
});

// Toggle Clause finding details open/close (Global handler)
window.toggleFinding = function(header) {
    const item = header.parentElement;
    item.classList.toggle('active');
    
    const body = item.querySelector('.finding-body');
    const icon = header.querySelector('i');
    
    if (item.classList.contains('active')) {
        body.style.display = 'flex';
        icon.style.transform = 'rotate(180deg)';
    } else {
        body.style.display = 'none';
        icon.style.transform = 'rotate(0deg)';
    }
};
