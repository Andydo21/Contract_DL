function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
}

const ENTITY_LABELS = {PARTY_A: 'Bên A', PARTY_B: 'Bên B', PARTY: 'Bên ký kết', ENTITY: 'Thực thể'};

// OCR can misread a digit silently, so numbers stay visibly tied to the original page.
function ocrNumbersHTML(text) {
    return String(text ?? '').split(/(\p{Nd}[\p{Nd}.,]*)/u).map((part, index) => index % 2
        ? `<mark title="Số do OCR đọc, hãy đối chiếu với ảnh gốc" style="background: rgba(245, 158, 11, 0.22); color: inherit; border-radius: 3px; padding: 0 2px;">${escapeHtml(part)}</mark>`
        : escapeHtml(part)).join('');
}

function sourcePagesHTML(contractId, versionId, pages) {
    if (!pages || !pages.length) return '';
    return `<div class="clause-source-pages" style="font-size: 12px; color: var(--text-muted); margin-bottom: 12px;">Số tô vàng do OCR đọc, hãy đối chiếu ảnh gốc: ${pages.map(page =>
        `<a href="/ai-extract/contracts/${encodeURIComponent(contractId)}/pages/${encodeURIComponent(page)}/?version_id=${encodeURIComponent(versionId)}" target="_blank" rel="noopener" style="color: #05359d;">Trang ${escapeHtml(page)}</a>`).join(', ')}</div>`;
}

// The scan replaces the analysis tab, so its result is shown on a fresh page.
// The badge states the analysis's own level (a single HIGH finding is a high-risk contract); the score only sets it
// when no level was stored.
function gaugeLevel(score, level) {
    const key = ['HIGH', 'MEDIUM', 'LOW'].includes(level) ? level : score >= 80 ? 'HIGH' : score >= 50 ? 'MEDIUM' : 'LOW';
    return {HIGH: ['#ef4444', 'High Risk', 'score-high'], MEDIUM: ['#f97316', 'Medium Risk', 'score-medium'],
            LOW: ['#10b981', 'Low Risk', 'score-low']}[key];
}

function reloadWithToast(message, type) {
    try {
        sessionStorage.setItem('contract-detail-toast', JSON.stringify({message, type}));
    } catch (err) {
        console.error(err);
    }
    window.location.reload();
}

document.addEventListener('DOMContentLoaded', () => {
    try {
        const pending = JSON.parse(sessionStorage.getItem('contract-detail-toast') || 'null');
        sessionStorage.removeItem('contract-detail-toast');
        if (pending) showToast(pending.message, pending.type);
    } catch (err) {
        console.error(err);
    }

    // 0. Auto Initial AJAX Fetch on page load
    const pathParts = window.location.pathname.split('/').filter(Boolean);
    const contractId = pathParts[1];
    const urlParams = new URLSearchParams(window.location.search);
    const versionId = urlParams.get('version_id');
    if (contractId && window.refreshContractDetailViaAjax) {
        window.refreshContractDetailViaAjax(contractId, versionId);
    }
    // 1. Gauge Animation
    const gauge = document.getElementById('gauge-val');
    const gaugeStatus = document.getElementById('gauge-status');
    
    if (gauge) {
        const score = parseFloat(gauge.dataset.score);
        const r = 36;
        const circumference = 2 * Math.PI * r;
        const offset = circumference - (score / 100) * circumference;
        
        // Trigger stroke offset transition
        setTimeout(() => {
            gauge.style.strokeDashoffset = offset;
        }, 100);
        
        // Color the circle and update status text
        const [color, label, cls] = gaugeLevel(score, gauge.dataset.level);
        gauge.style.stroke = color;
        gaugeStatus.innerHTML = label;
        gaugeStatus.className = 'gauge-status ' + cls;
    }

    // 2. Expert Review Form Handling
    const reviewForm = document.getElementById('detail-review-form');
    if (reviewForm) {
        reviewForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const analysisId = reviewForm.dataset.analysisId;
            const final_risk_level = reviewForm.final_risk_level.value;
            const comment = reviewForm.comment.value;
            
            try {
                const res = await fetch(`/api/analyses/${analysisId}/review/`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCookie('csrftoken')
                    },
                    body: JSON.stringify({ final_risk_level, comment })
                });
                
                const data = await res.json();
                if (data.success) {
                    // The review section is drawn by the page, not by the data refresh: reload to show it.
                    reloadWithToast("Đã gửi nhận xét.", "success");
                } else {
                    alert("Error submitting review: " + (data.error || "Unknown error"));
                }
            } catch (err) {
                console.error(err);
                alert("Failed to submit review request.");
            }
        });
    }

    // 3. Run/Re-run AI Analysis Trigger (Detailed Page)
    const triggerButtons = document.querySelectorAll('#btn-detail-trigger-analysis, #btn-detail-reanalyze');
    
    triggerButtons.forEach(btn => {
        btn.addEventListener('click', async () => {
            const contractId = btn.dataset.contractId;
            const analysisTab = document.getElementById('analysis-tab');

            // 1. Ensure Risk Analysis tab is active
            const panelTabBtns = document.querySelectorAll('.panel-tab-btn');
            panelTabBtns.forEach(b => {
                b.classList.remove('active');
                b.style.color = 'var(--text-muted)';
                if (b.dataset.target === 'analysis-tab') {
                    b.classList.add('active');
                    b.style.color = '#171a21';
                }
            });
            const panes = document.querySelectorAll('.tab-content-wrapper > .tab-pane');
            panes.forEach(pane => {
                if (pane.id === 'analysis-tab') {
                    pane.style.display = 'block';
                    pane.classList.add('active');
                } else {
                    pane.style.display = 'none';
                    pane.classList.remove('active');
                }
            });

            // 2. Disable trigger buttons
            triggerButtons.forEach(b => {
                b.disabled = true;
                b.style.opacity = '0.7';
                b.innerHTML = `<i class="fa-solid fa-circle-notch fa-spin"></i> Đang phân tích…`;
            });

            // 3. A progress card inside the Risk Assessment section, updated from the background job
            const showRiskProgress = text => {
                if (!analysisTab) return;
                analysisTab.innerHTML = `
                    <div class="risk-loading-card" style="text-align: center; color: var(--text-muted); padding: 50px 24px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 16px; background: rgba(37, 99, 235, 0.04); border: 1px dashed rgba(37, 99, 235, 0.3); border-radius: 12px; margin: 12px 0;">
                        <div style="position: relative; width: 64px; height: 64px; display: flex; align-items: center; justify-content: center;">
                            <i class="fa-solid fa-wand-magic-sparkles" style="font-size: 28px; color: #05359d;"></i>
                            <div style="position: absolute; top:0; left:0; width:64px; height:64px; border:3px solid rgba(37, 99, 235, 0.15); border-top-color:#2563eb; border-radius:50%; animation:spin 1s linear infinite;"></div>
                        </div>
                        <div>
                            <h3 style="color: #171a21; font-family: 'Inter', sans-serif; font-size: 17px; margin: 0 0 6px 0; font-weight: 700;">Đang phân tích rủi ro hợp đồng</h3>
                            <p id="risk-progress-text" style="max-width: 420px; font-size: 13px; color: var(--text-secondary); margin: 0; line-height: 1.5;"></p>
                        </div>
                    </div>`;
                const line = document.getElementById('risk-progress-text');
                if (line) line.textContent = text;
            };
            const stageText = item => {
                const p = item && item.progress;
                if (!item || item.status === 'waiting') return 'Đang chờ trong hàng đợi (mỗi lúc xử lý một tài liệu)…';
                if (!p) return 'Đang chuẩn bị các điều khoản…';
                if (p.stage === 'retrieving_law') return `Đang tìm văn bản pháp luật cho ${p.total} điều khoản…`;
                if (p.stage === 'clauses') return `Đã phân tích ${p.done}/${p.total} điều khoản, đối chiếu với luật và các điều khoản liên quan…`;
                if (p.stage === 'whole_contract') return 'Đang đánh giá rủi ro chung của toàn hợp đồng…';
                return 'Đang phân tích…';
            };
            showRiskProgress('Đang gửi yêu cầu…');

            try {
                const res = await fetch(`/api/contracts/${contractId}/analyze/`, {
                    method: 'POST',
                    headers: {
                        'X-CSRFToken': getCookie('csrftoken')
                    }
                });
                const data = await res.json();
                if (!data.success) {
                    reloadWithToast(data.error || "Chưa phân tích được hợp đồng.", "error");
                    return;
                }
                // Clause-by-clause analysis runs as a background job; follow it until it ends.
                const follow = async () => {
                    try {
                        const job = (await (await fetch(`/api/ai/bulk/${data.job_id}/`)).json()).job;
                        const item = job && job.items && job.items[0];
                        if (job && job.status === 'complete') { reloadWithToast("Phân tích rủi ro hoàn tất.", "success"); return; }
                        if (job && (job.status === 'failed' || job.status === 'partial')) {
                            reloadWithToast((item && item.error) || job.error || "Chưa phân tích được hợp đồng.", "error");
                            return;
                        }
                        showRiskProgress(stageText(item));
                    } catch (err) {
                        console.error(err);
                    }
                    setTimeout(follow, 4000);
                };
                follow();
            } catch (err) {
                console.error(err);
                reloadWithToast("Lỗi kết nối: Không thể gửi yêu cầu phân tích tới hệ thống.", "error");
            }
        });
    });

    // 3b. Extraction progress: an uploaded document extracts in the background; the risk analysis opens when it is done.
    const extraction = document.getElementById('extraction-progress');
    if (extraction) {
        const label = document.getElementById('extraction-progress-label');
        const percent = document.getElementById('extraction-progress-percent');
        const fill = document.getElementById('extraction-progress-fill');
        const bar = document.getElementById('extraction-progress-bar');
        const stages = {queued: 'Đang chờ trong hàng đợi', structure: 'Đang đọc trang', whole_document_entities: 'Đang trích thực thể',
            pregraph_identity: 'Đang ghép thực thể', contract_clauses: 'Đang tách điều khoản', heading_hierarchy: 'Đang dựng cây mục',
            document_references: 'Đang tìm dẫn chiếu trong hợp đồng', related_passages: 'Đang nối đoạn liên quan',
            dense_index: 'Đang đánh chỉ mục vector', neo4j_final: 'Đang lưu đồ thị', neo4j_entities: 'Đang lưu đồ thị',
            retrieval_index: 'Đang hoàn tất chỉ mục tìm kiếm'};
        const setButtons = ready => triggerButtons.forEach(b => {
            if (b.innerHTML.includes('fa-spin')) return;
            b.disabled = !ready;
            b.style.opacity = ready ? '1' : '.55';
            b.title = ready ? '' : 'Chờ trích xuất xong';
        });
        const poll = async () => {
            let again = true;
            try {
                const state = await (await fetch(`/api/ai/contracts/${extraction.dataset.contractId}/extraction-status/`)).json();
                const p = state.progress || {};
                const value = Math.max(0, Math.min(100, p.percent || 0));
                fill.style.width = `${value}%`;
                bar.setAttribute('aria-valuenow', String(value));
                percent.textContent = `${value}%`;
                if (state.status === 'COMPLETED') {
                    label.textContent = 'Đã trích xuất xong. Có thể phân tích rủi ro hợp đồng.';
                    setButtons(true);
                    again = false;
                } else if ((state.status === 'FAILED' || state.status === 'PARTIAL') && !state.queued) {
                    label.textContent = `Trích xuất chưa hoàn tất: ${state.error || state.status}. Quản trị viên có thể trích xuất lại ở trang quản trị.`;
                    setButtons(false);
                    again = false;
                } else if (state.status === 'NOT_STARTED') {
                    label.textContent = 'Chưa trích xuất. Tải phiên bản mới lên, hoặc quản trị viên trích xuất lại ở trang quản trị.';
                    percent.textContent = '';
                    setButtons(false);
                    again = false;
                } else {
                    const name = stages[p.stage] || 'Đang trích xuất';
                    label.textContent = p.stage === 'structure' && p.total_pages ? `${name} ${p.page || 0}/${p.total_pages}` : `${name}…`;
                    setButtons(false);
                }
            } catch (err) {
                console.error(err);
            }
            if (again) setTimeout(poll, 4000);
        };
        poll();
    }

    // 4. Push to Workflow button
    const btnPushWorkflow = document.getElementById('btn-push-workflow');
    if (btnPushWorkflow) {
        btnPushWorkflow.addEventListener('click', async () => {
            const contractId = btnPushWorkflow.dataset.contractId;
            btnPushWorkflow.disabled = true;
            btnPushWorkflow.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Pushing...';

            try {
                const res = await fetch(`/api/contracts/${contractId}/workflow/`, {
                    method: 'POST',
                    headers: {
                        'X-CSRFToken': getCookie('csrftoken')
                    }
                });
                const data = await res.json();

                if (data.success) {
                    showToast('Contract đã được đẩy lên workflow thành công! Đang tải lại...', 'success');
                    setTimeout(() => window.location.reload(), 1800);
                } else {
                    btnPushWorkflow.disabled = false;
                    btnPushWorkflow.innerHTML = '<i class="fa-solid fa-paper-plane"></i> Push to Workflow';
                    const msg = data.error || 'Không thể đẩy lên workflow.';
                    showToast(msg.includes('already active') ? 'Workflow đã tồn tại cho contract này.' : msg, 'warning');
                }
            } catch (err) {
                btnPushWorkflow.disabled = false;
                btnPushWorkflow.innerHTML = '<i class="fa-solid fa-paper-plane"></i> Push to Workflow';
                console.error(err);
                showToast('Lỗi kết nối: Không thể kết nối tới workflow service.', 'error');
            }
        });
    }

    // 4b. Re-push to Workflow button (Force recreate)
    const btnRepushWorkflow = document.getElementById('btn-repush-workflow');
    if (btnRepushWorkflow) {
        btnRepushWorkflow.addEventListener('click', async () => {
            if (!confirm('Bạn có chắc chắn muốn reset và tạo lại quy trình phê duyệt (Workflow) cho hợp đồng này không? Toàn bộ các bước ký kết và chữ ký cũ sẽ bị xóa.')) {
                return;
            }
            
            const contractId = btnRepushWorkflow.dataset.contractId;
            btnRepushWorkflow.disabled = true;
            btnRepushWorkflow.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Resetting...';

            try {
                const res = await fetch(`/api/contracts/${contractId}/workflow/`, {
                    method: 'POST',
                    headers: {
                        'X-CSRFToken': getCookie('csrftoken')
                    }
                });
                const data = await res.json();

                if (data.success) {
                    showToast('Đã xóa và tái tạo workflow mới thành công! Đang tải lại...', 'success');
                    setTimeout(() => window.location.reload(), 1800);
                } else {
                    btnRepushWorkflow.disabled = false;
                    btnRepushWorkflow.innerHTML = '<i class="fa-solid fa-arrows-rotate"></i> Re-push to Workflow';
                    showToast(data.error || 'Không thể tạo lại workflow.', 'warning');
                }
            } catch (err) {
                btnRepushWorkflow.disabled = false;
                btnRepushWorkflow.innerHTML = '<i class="fa-solid fa-arrows-rotate"></i> Re-push to Workflow';
                console.error(err);
                showToast('Lỗi kết nối: Không thể kết nối tới workflow service.', 'error');
            }
        });
    }

    // 5. Auto-load workflow status
    const workflowContainer = document.getElementById('workflow-steps-container');
    if (workflowContainer) {
        const contractId = workflowContainer.dataset.contractId;
        (async () => {
            try {
                const res = await fetch(`/api/contracts/${contractId}/workflow/status/`);
                const data = await res.json();
                const wf = data.workflow;
                if (!wf) {
                    const pushContainer = document.getElementById('workflow-push-container');
                    const statusContainer = document.getElementById('workflow-status-container');
                    if (pushContainer && statusContainer) {
                        pushContainer.style.display = 'block';
                        statusContainer.style.display = 'none';
                    } else {
                        workflowContainer.innerHTML = '<p style="color:var(--text-muted);font-size:13px;">Chưa có workflow nào được tạo.</p>';
                    }
                    return;
                }
                const statusColor = { PENDING: '#2563eb', IN_PROGRESS: '#f59e0b', COMPLETED: '#10b981', REJECTED: '#ef4444' };
                const stepStatusIcon = { PENDING: 'fa-clock', APPROVED: 'fa-circle-check', REJECTED: 'fa-circle-xmark' };
                const stepStatusColor = { PENDING: '#6b7280', APPROVED: '#10b981', REJECTED: '#ef4444' };

                workflowContainer.innerHTML = `
                    <div style="margin-bottom:12px;display:flex;align-items:center;justify-content:space-between;gap:8px;">
                        <div style="display:flex;align-items:center;gap:8px;">
                            <span style="font-size:12px;font-weight:600;background:${statusColor[wf.status]||'#2563eb'}22;color:${statusColor[wf.status]||'#2563eb'};padding:4px 10px;border-radius: 12px;">${wf.status}</span>
                            <span style="font-size:12px;color:var(--text-muted);">${escapeHtml(wf.workflow_name)}</span>
                        </div>
                        <a href="/board/${wf.workflow_id}/" target="_blank" style="font-size:11.5px;color:#05359d;text-decoration:none;font-weight:600;background:rgba(37, 99, 235, 0.12);padding:4px 10px;border-radius:6px;border:1px solid rgba(37, 99, 235, 0.25);display:inline-flex;align-items:center;gap:4px;" title="Open standalone Workflow Detail page">
                            <i class="fa-solid fa-route"></i> Workflow Detail <i class="fa-solid fa-up-right-from-square" style="font-size:10px;"></i>
                        </a>
                    </div>
                    <div style="display:flex;flex-direction:column;gap:8px;">
                        ${wf.steps.map(st => `
                        <div style="display:flex;align-items:center;gap:10px;padding:10px 14px;background:rgba(15, 23, 42, 0.027);border-radius:8px;border:1px solid rgba(15, 23, 42, 0.098);">
                            <i class="fa-solid ${stepStatusIcon[st.status]||'fa-clock'}" style="color:${stepStatusColor[st.status]||'#6b7280'};font-size:15px;"></i>
                            <div>
                                <div style="font-size:13px;font-weight:600;color:#171a21;">${escapeHtml(st.step_order)}. ${escapeHtml(st.step_name)}</div>
                                <div style="font-size:11.5px;color:var(--text-muted);">${st.status}${st.completed_at ? ' · ' + new Date(st.completed_at).toLocaleDateString('vi-VN') : ''}</div>
                            </div>
                        </div>`).join('')}
                    </div>
                `;
            } catch (e) {
                workflowContainer.innerHTML = '<p style="color:#8d0c0c;font-size:13px;">Không tải được trạng thái workflow.</p>';
            }
        })();
    }

    // 6. Version switcher dropdown event
    const versionSelect = document.getElementById('version-select');
    if (versionSelect) {
        versionSelect.addEventListener('change', (e) => {
            const versionId = e.target.value;
            const contractId = window.location.pathname.split('/')[2];
            if (window.refreshContractDetailViaAjax) {
                window.refreshContractDetailViaAjax(contractId, versionId);
            } else {
                const url = new URL(window.location.href);
                url.searchParams.set('version_id', versionId);
                window.location.href = url.toString();
            }
        });
    }

    // 5. Upload new version modal logic
    const btnUploadNew = document.getElementById('btn-upload-new-version');
    const uploadModal = document.getElementById('upload-version-modal');
    const btnCloseModal = document.getElementById('modal-close-btn');
    const btnCancelUpload = document.getElementById('btn-cancel-upload');
    
    if (btnUploadNew && uploadModal) {
        // Open Modal
        btnUploadNew.addEventListener('click', () => {
            uploadModal.classList.add('active');
        });
        
        // Close Modal helpers
        const closeModal = () => {
            uploadModal.classList.remove('active');
            document.getElementById('upload-version-form').reset();
            if (typeof versionPages !== "undefined" && versionPages) versionPages.clear();
            const selectedFile = document.getElementById('selected-file-name');
            if (selectedFile) {
                selectedFile.style.display = 'none';
                selectedFile.innerHTML = '';
            }
        };
        
        if (btnCloseModal) btnCloseModal.addEventListener('click', closeModal);
        if (btnCancelUpload) btnCancelUpload.addEventListener('click', closeModal);
        
        // Close on clicking overlay background
        uploadModal.addEventListener('click', (e) => {
            if (e.target === uploadModal) {
                closeModal();
            }
        });
    }

    // Tab switcher in upload modal
    const tabBtns = document.querySelectorAll('.modal-tab-btn');
    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            tabBtns.forEach(b => {
                b.classList.remove('active');
                b.style.color = 'var(--text-muted)';
            });
            btn.classList.add('active');
            btn.style.color = '#171a21';
            
            const targetTab = btn.dataset.tab;
            const uploadModal = document.getElementById('upload-version-modal');
            const panes = uploadModal ? uploadModal.querySelectorAll('.tab-pane') : document.querySelectorAll('#upload-version-modal .tab-pane');
            panes.forEach(pane => {
                if (pane.id === targetTab) {
                    pane.style.display = 'block';
                    pane.classList.add('active');
                } else {
                    pane.style.display = 'none';
                    pane.classList.remove('active');
                }
            });
        });
    });

    // File selection handling
    const fileZone = document.getElementById('file-upload-zone');
    const fileInput = document.getElementById('version_file_input');
    const selectedFileName = document.getElementById('selected-file-name');
    
    // Several photos are one document: numbered thumbnails let the user set the page order.
    const showSelection = (files) => {
        if (!selectedFileName) return;
        selectedFileName.style.display = files.length ? 'block' : 'none';
        selectedFileName.innerHTML = !files.length ? '' : files.length > 1
            ? `<i class="fa-solid fa-images"></i> ${files.length} ảnh sẽ được ghép thành một văn bản theo thứ tự bên dưới`
            : `<i class="fa-solid fa-file-circle-check"></i> Selected: ${files[0].name}`;
    };
    const versionPages = fileInput && window.PageImages
        ? window.PageImages.attach(fileInput, document.getElementById('version-page-image-list'), showSelection) : null;

    if (fileZone && fileInput) {
        
        // Drag and drop events
        ['dragenter', 'dragover'].forEach(eventName => {
            fileZone.addEventListener(eventName, (e) => {
                e.preventDefault();
                fileZone.style.borderColor = 'var(--accent-primary)';
                fileZone.style.background = 'rgba(37, 99, 235, 0.08)';
            }, false);
        });
        
        ['dragleave', 'drop'].forEach(eventName => {
            fileZone.addEventListener(eventName, (e) => {
                e.preventDefault();
                fileZone.style.borderColor = 'rgba(37, 99, 235, 0.3)';
                fileZone.style.background = 'rgba(37, 99, 235, 0.02)';
            }, false);
        });
        
        fileZone.addEventListener('drop', (e) => {
            const dt = e.dataTransfer;
            const files = dt.files;
            if (files.length > 0) {
                fileInput.files = files;
                if (versionPages) versionPages.set(files);
            }
        });
    }

    // Submit new version form via AJAX
    const uploadForm = document.getElementById('upload-version-form');
    if (uploadForm) {
        uploadForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            
            const contractId = uploadForm.dataset.contractId || (document.getElementById('btn-detail-reanalyze') || document.getElementById('btn-detail-trigger-analysis') || {}).dataset?.contractId;
            if (!contractId) {
                showToast("Không tìm thấy ID hợp đồng trên trang.", "error");
                return;
            }

            const activeTabPane = uploadForm.querySelector('.tab-pane.active');
            const isFileTab = activeTabPane && activeTabPane.id === 'file-tab';
            
            const formData = new FormData(uploadForm);
            if (isFileTab) {
                formData.delete('raw_content');
                if (versionPages) {
                    const pageError = versionPages.error();
                    if (pageError) {
                        showToast(pageError, "warning");
                        return;
                    }
                    versionPages.appendTo(formData);
                }
                if (!formData.getAll('file').some(f => f && f.size !== undefined && f.name)) {
                    showToast("Vui lòng chọn một tập tin hợp đồng (.pdf, .docx, .txt).", "warning");
                    return;
                }
            } else {
                formData.delete('file');
                const rawContentVal = (uploadForm.raw_content ? uploadForm.raw_content.value : '').trim();
                if (!rawContentVal) {
                    showToast("Vui lòng nhập nội dung văn bản hợp đồng.", "warning");
                    return;
                }
            }
            
            if (uploadModal) uploadModal.classList.remove('active');
            
            if (scannerLoader) {
                scannerLoader.classList.add('active');
                const scannerText = scannerLoader.querySelector('.scanner-text');
                if (scannerText) scannerText.innerHTML = "UPLOADING & SCANNING NEW VERSION...";
            }
            
            try {
                const res = await fetch(`/api/contracts/${contractId}/versions/`, {
                    method: 'POST',
                    body: formData
                });
                const data = await res.json();
                
                setTimeout(() => {
                    if (scannerLoader) scannerLoader.classList.remove('active');
                    if (data.success) {
                        showToast("Phiên bản mới đã được tải lên thành công!", "success");
                        if (window.refreshContractDetailViaAjax) {
                            window.refreshContractDetailViaAjax(contractId, data.version_id);
                        }
                    } else {
                        const errorMsg = data.error || "Unknown error";
                        const isModelError = errorMsg.includes("503") || errorMsg.includes("communication failed") || errorMsg.includes("not loaded");
                        if (isModelError) {
                            showToast("Phiên bản mới đã được tải lên, nhưng hệ thống chưa kết nối được với mô hình AI để phân tích ngay.", "warning");
                            if (window.refreshContractDetailViaAjax) {
                                window.refreshContractDetailViaAjax(contractId, data.version_id);
                            }
                        } else {
                            showToast(errorMsg, "error");
                        }
                    }
                }, 3000);
            } catch (err) {
                if (scannerLoader) scannerLoader.classList.remove('active');
                console.error(err);
                showToast("Lỗi kết nối: Không thể tải lên phiên bản mới.", "error");
            }
        });
    }

    // Panel Tabs Switcher
    const panelTabBtns = document.querySelectorAll('.panel-tab-btn');
    panelTabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            panelTabBtns.forEach(b => {
                b.classList.remove('active');
                b.style.color = 'var(--text-muted)';
            });
            btn.classList.add('active');
            btn.style.color = '#171a21';
            
            const targetTab = btn.dataset.target;
            const panes = document.querySelectorAll('.tab-content-wrapper > .tab-pane');
            panes.forEach(pane => {
                if (pane.id === targetTab) {
                    pane.style.display = 'block';
                    pane.classList.add('active');
                } else {
                    pane.style.display = 'none';
                    pane.classList.remove('active');
                }
            });
        });
    });

    const scannerLoader = document.getElementById('scanner-loader');

    // 9. Generate AI Summary click handler
    const btnGenerateSummary = document.getElementById('btn-generate-summary');
    if (btnGenerateSummary) {
        btnGenerateSummary.addEventListener('click', async () => {
            const contractId = btnGenerateSummary.dataset.contractId;
            const versionSelect = document.getElementById('version-select');
            const versionId = versionSelect ? versionSelect.value : null;
            
            if (scannerLoader) {
                scannerLoader.classList.add('active');
                const scannerText = scannerLoader.querySelector('.scanner-text');
                if (scannerText) scannerText.innerHTML = "GENERATING AI EXECUTIVE SUMMARY...";
            }
            
            try {
                const res = await fetch(`/api/ai/contracts/${contractId}/summarize/`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCookie('csrftoken')
                    },
                    body: JSON.stringify({ version_id: versionId })
                });
                const data = await res.json();
                
                const done = (message, kind) => {
                    if (scannerLoader) scannerLoader.classList.remove('active');
                    showToast(message, kind);
                    if (kind === 'success' && window.refreshContractDetailViaAjax) window.refreshContractDetailViaAjax(contractId, versionId);
                };
                if (!data.success) { done(data.error || "Lỗi khi tạo tóm tắt AI.", "error"); return; }
                // The summary runs as a background job (like the risk analysis); follow it until it ends.
                const follow = async () => {
                    try {
                        const job = (await (await fetch(`/api/ai/bulk/${data.job_id}/`)).json()).job;
                        const item = job && job.items && job.items[0];
                        if (job && job.status === 'complete') { done("Tóm tắt AI hoàn tất!", "success"); return; }
                        if (job && (job.status === 'failed' || job.status === 'partial')) {
                            done((item && item.error) || job.error || "Lỗi khi tạo tóm tắt AI.", "error");
                            return;
                        }
                    } catch (err) {
                        console.error(err);
                    }
                    setTimeout(follow, 3000);
                };
                follow();
            } catch (err) {
                if (scannerLoader) scannerLoader.classList.remove('active');
                console.error(err);
                showToast("Lỗi kết nối khi tạo tóm tắt AI.", "error");
            }
        });
    }
});

// Toggle folding/unfolding of clauses
window.toggleClause = function(header) {
    const item = header.parentElement;
    item.classList.toggle('active');
    const body = item.querySelector('.clause-item-body');
    const icon = header.querySelector('i');
    if (item.classList.contains('active')) {
        body.style.display = 'block';
        icon.style.transform = 'rotate(180deg)';
    } else {
        body.style.display = 'none';
        icon.style.transform = 'rotate(0deg)';
    }
};

// Toast notification helper
window.showToast = function(message, type = 'error') {
    if (!document.getElementById('toast-styles')) {
        const style = document.createElement('style');
        style.id = 'toast-styles';
        style.innerHTML = `
            .toast-container {
                position: fixed;
                top: 24px;
                right: 24px;
                z-index: 9999;
                display: flex;
                flex-direction: column;
                gap: 12px;
                pointer-events: none;
            }
            .toast-card {
                background: #f4f6fa;
                border: 1px solid rgba(239, 68, 68, 0.2);
                border-left: 4px solid #ef4444;
                color: #171a21;
                padding: 16px 20px;
                border-radius: 12px;
                box-shadow: 0 10px 25px -5px rgba(15, 23, 42, 0.1), 0 8px 10px -6px rgba(15, 23, 42, 0.1);
                backdrop-filter: none;
                display: flex;
                align-items: center;
                gap: 16px;
                min-width: 320px;
                max-width: 450px;
                transform: translateX(120%);
                transition: transform 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275), opacity 0.3s ease;
                pointer-events: auto;
                opacity: 0;
            }
            .toast-card.show {
                transform: translateX(0);
                opacity: 1;
            }
            .toast-card.warning {
                border-left-color: #f59e0b;
                border-color: rgba(245, 158, 11, 0.2);
            }
            .toast-card.success {
                border-left-color: #10b981;
                border-color: rgba(16, 185, 129, 0.2);
            }
            .toast-icon {
                font-size: 20px;
                color: #8d0c0c;
                flex-shrink: 0;
            }
            .toast-card.warning .toast-icon {
                color: #d48809;
            }
            .toast-content {
                display: flex;
                flex-direction: column;
                gap: 4px;
            }
            .toast-title {
                font-family: 'Inter', sans-serif;
                font-weight: 600;
                font-size: 14.5px;
            }
            .toast-desc {
                font-size: 12.5px;
                color: rgba(23, 26, 33, 0.7);
                line-height: 1.4;
            }
            .toast-close {
                margin-left: auto;
                background: none;
                border: none;
                color: rgba(23, 26, 33, 0.4);
                cursor: pointer;
                padding: 4px;
                transition: color 0.2s;
            }
            .toast-close:hover {
                color: #171a21;
            }
        `;
        document.head.appendChild(style);
    }

    let container = document.querySelector('.toast-container');
    if (!container) {
        container = document.createElement('div');
        container.className = 'toast-container';
        document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.className = `toast-card ${type}`;
    
    const iconClass = type === 'warning' ? 'fa-solid fa-triangle-exclamation' : type === 'success' ? 'fa-solid fa-circle-check' : 'fa-solid fa-circle-exclamation';
    const titleText = type === 'warning' ? 'Cảnh Báo Hệ Thống' : type === 'success' ? 'Thành Công' : 'Lỗi Hệ Thống';

    toast.innerHTML = `
        <i class="${iconClass} toast-icon"></i>
        <div class="toast-content">
            <div class="toast-title">${titleText}</div>
            <div class="toast-desc">${message}</div>
        </div>
        <button class="toast-close"><i class="fa-solid fa-xmark"></i></button>
    `;

    container.appendChild(toast);

    setTimeout(() => {
        toast.classList.add('show');
    }, 10);

    const closeBtn = toast.querySelector('.toast-close');
    const dismiss = () => {
        toast.classList.remove('show');
        setTimeout(() => {
            toast.remove();
        }, 300);
    };

    closeBtn.addEventListener('click', dismiss);
    setTimeout(dismiss, 8000);
};

// Toggle clause body (Global helper)
window.toggleClause = function(header) {
    const item = header.parentElement;
    const body = item.querySelector('.clause-item-body');
    const icon = header.querySelector('i.fa-chevron-down');
    if (body) {
        if (body.style.display === 'none' || !body.style.display) {
            body.style.display = 'block';
            if (icon) icon.style.transform = 'rotate(180deg)';
        } else {
            body.style.display = 'none';
            if (icon) icon.style.transform = 'rotate(0deg)';
        }
    }
};

// Pure AJAX refresh of Contract Detail page without full browser reload
window.refreshContractDetailViaAjax = async function(contractId, versionId = null) {
    const apiUrl = versionId ? `/api/contracts/${contractId}/?version_id=${versionId}` : `/api/contracts/${contractId}/`;
    try {
        const res = await fetch(apiUrl);
        if (!res.ok) return;
        const contract = await res.json();
        
        if (versionId) {
            const currentUrl = new URL(window.location.href);
            currentUrl.searchParams.set('version_id', versionId);
            window.history.pushState({}, '', currentUrl.toString());
        }

        // 1. Update Version Select dropdown options
        const versionSelect = document.getElementById('version-select');
        if (versionSelect && contract.versions) {
            versionSelect.innerHTML = contract.versions.map(v => `
                <option value="${v.id}" ${v.id == contract.active_version_id ? 'selected' : ''}>
                    v${v.version_number} - ${(v.change_summary || '').substring(0, 20)} (${v.overall_score ? Math.round(v.overall_score) + '%' : 'Pending'})
                </option>
            `).join('');
        }

        // 2. Update Status badge
        const statusBadges = document.querySelectorAll('.status-badge');
        statusBadges.forEach(badge => {
            badge.className = `status-badge status-${(contract.status || '').toLowerCase()}`;
            badge.textContent = contract.status;
        });

        // 3. Update Document raw content
        const docPre = document.querySelector('.doc-content-pre');
        if (docPre) docPre.textContent = contract.raw_content || '';

        // 4. Update Active Version Info Card
        const activeVersionInfo = document.querySelector('.active-version-info-card');
        if (activeVersionInfo) {
            activeVersionInfo.innerHTML = `
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <span style="font-family: 'Inter', sans-serif; font-weight: 700; color: #171a21; font-size: 14px; display: flex; align-items: center; gap: 6px;">
                        <i class="fa-solid fa-code-branch" style="color: var(--accent-primary);"></i> Viewing Version ${contract.active_version_number || 1}
                    </span>
                    <span style="font-size: 11.5px; color: var(--text-muted);">
                        Status: ${contract.status}
                    </span>
                </div>
                ${contract.active_version_change_summary ? `
                <div style="font-size: 12.5px; color: var(--text-secondary); line-height: 1.4; border-top: 1px solid rgba(15, 23, 42, 0.09); margin-top: 8px; padding-top: 8px;">
                    <strong style="color: var(--accent-primary);">Change Log:</strong> ${escapeHtml(contract.active_version_change_summary)}
                </div>` : ''}
            `;
        }

        // 5. Update Metadata cards (Code, Type, Value)
        const metaVals = document.querySelectorAll('.meta-val');
        if (metaVals.length >= 3) {
            metaVals[0].textContent = contract.contract_code || 'N/A';
            metaVals[1].textContent = contract.contract_type || 'N/A';
            metaVals[2].textContent = '$' + (contract.contract_value ? Number(contract.contract_value).toLocaleString('en-US', {minimumFractionDigits: 2}) : '0.00');
        }

        // 6. Update Gauge & Risk Score
        const gauge = document.getElementById('gauge-val');
        const gaugeText = document.querySelector('.gauge-text');
        const gaugeStatus = document.getElementById('gauge-status');
        if (gauge && contract.analysis && contract.analysis.overall_score !== undefined) {
            const score = parseFloat(contract.analysis.overall_score);
            gauge.dataset.score = score;
            if (gaugeText) gaugeText.textContent = Math.round(score) + '%';
            const r = 36;
            const circumference = 2 * Math.PI * r;
            const offset = circumference - (score / 100) * circumference;
            gauge.style.strokeDashoffset = offset;
            gauge.dataset.level = contract.analysis.risk_level || '';
            const [color, label, cls] = gaugeLevel(score, contract.analysis.risk_level);
            gauge.style.stroke = color;
            if (gaugeStatus) { gaugeStatus.innerHTML = label; gaugeStatus.className = 'gauge-status ' + cls; }
        }

        // 7. Update AI Summary Box
        const summaryBox = document.querySelector('.summary-box');
        if (summaryBox && contract.analysis && contract.analysis.summary) {
            summaryBox.textContent = contract.analysis.summary;
        }

        // 8. Update Findings List
        const findingsList = document.querySelector('.findings-list');
        if (findingsList) {
            if (contract.findings && contract.findings.length > 0) {
                findingsList.innerHTML = contract.findings.map((f, i, all) => `
                    ${f.is_suggestion && !(i > 0 && all[i - 1].is_suggestion) ? '<h5 class="section-title" style="margin-top: 18px; font-size: 14px;"><i class="fa-solid fa-pen-to-square"></i> Gợi ý soạn thảo <span style="font-weight: 400; color: var(--text-muted);">(không có điều luật làm căn cứ, không tính vào điểm rủi ro)</span></h5>' : ''}
                    <div class="finding-item">
                        <div class="finding-header" onclick="toggleFinding(this)">
                            <div class="finding-left">
                                ${f.is_suggestion ? '<span class="risk-badge badge-low">GỢI Ý</span>' : `<span class="risk-badge badge-${escapeHtml((f.risk_level || '').toLowerCase())}">${escapeHtml(f.risk_level)}</span>`}
                                <span>${escapeHtml(f.risk_name)}</span>
                            </div>
                            <i class="fa-solid fa-chevron-down" style="color: var(--text-muted); font-size: 12px; transition: transform 0.2s;"></i>
                        </div>
                        <div class="finding-body" style="display: none;">
                            <div class="finding-block">
                                <div class="block-label">Điều khoản liên quan</div>
                                <div class="block-text" style="font-weight: 500; color: #171a21;">${escapeHtml(f.clause_title || 'Toàn bộ hợp đồng')}</div>
                            </div>
                            <div class="finding-block">
                                <div class="block-label">Risk Explanation</div>
                                <div class="block-text">${escapeHtml(f.explanation)}</div>
                            </div>
                            ${f.disadvantaged_party ? `
                            <div class="finding-block" style="margin-top: 8px;">
                                <div class="block-label" style="color: #8d0c0c;"><i class="fa-solid fa-triangle-exclamation"></i> Bên gặp bất lợi / Disadvantaged Party</div>
                                <div class="block-text" style="font-weight: 600; color: #9f0808;">${escapeHtml(f.disadvantaged_party)}</div>
                            </div>` : ''}
                            ${f.recommendation ? `
                            <div class="rec-box">
                                <div class="block-label" style="color: var(--risk-low);"><i class="fa-solid fa-lightbulb"></i> AI Recommendation</div>
                                <div class="block-text">${escapeHtml(f.recommendation)}</div>
                            </div>` : ''}
                        </div>
                    </div>
                `).join('');
            } else {
                findingsList.innerHTML = '<p style="color: var(--text-muted); font-style: italic;">No specific risks identified.</p>';
            }
        }

        // 9. Update Clauses List
        const clausesList = document.querySelector('.clauses-list');
        // The parties box is the editable form the user fills; it is not redrawn from the refreshed data.
        if (clausesList) {
            if (contract.clauses && contract.clauses.length > 0) {
                clausesList.innerHTML = contract.clauses.map(cl => `
                    <div class="clause-item-container" style="background: rgba(15, 23, 42, 0.025); border: 1px solid rgba(15, 23, 42, 0.09); border-radius: 10px; overflow: hidden; transition: all 0.2s;">
                        <div class="clause-item-header" style="padding: 12px 16px; cursor: pointer; display: flex; justify-content: space-between; align-items: center;" onclick="toggleClause(this)">
                            <span style="font-family: 'Inter', sans-serif; font-weight: 600; font-size: 14px; color: #171a21;">${escapeHtml(cl.title)}</span>
                            <div style="display: flex; align-items: center; gap: 8px;">
                                <span style="font-size: 11px; background: rgba(37, 99, 235, 0.15); color: #083492; padding: 2px 8px; border-radius: 12px;">${cl.entities ? cl.entities.length : 0} entities</span>
                                <i class="fa-solid fa-chevron-down" style="color: var(--text-muted); font-size: 12px; transition: transform 0.2s;"></i>
                            </div>
                        </div>
                        <div class="clause-item-body" style="display: none; padding: 16px; border-top: 1px solid rgba(15, 23, 42, 0.09); background: rgba(15, 23, 42, 0.045);">
                            <p style="font-size: 13px; line-height: 1.6; color: var(--text-secondary); white-space: pre-wrap; margin-top: 0; margin-bottom: 16px;">${ocrNumbersHTML(cl.content)}</p>
                            ${sourcePagesHTML(contract.id, contract.active_version_id, cl.source_pages)}
                            ${cl.entities && cl.entities.length > 0 ? `
                            <div style="border-top: 1px dashed rgba(15, 23, 42, 0.112); padding-top: 12px;">
                                <h5 style="margin: 0 0 10px 0; font-family: 'Inter', sans-serif; font-size: 11px; text-transform: uppercase; color: var(--accent-primary); letter-spacing: 0.5px;">Extracted Entities</h5>
                                <div style="display: flex; flex-direction: column; gap: 8px;">
                                    ${cl.entities.map(ee => `
                                    <div style="display: flex; justify-content: space-between; align-items: center; background: rgba(15, 23, 42, 0.025); padding: 8px 12px; border-radius: 6px; border: 1px solid rgba(15, 23, 42, 0.09);">
                                        <div style="display: flex; align-items: center; gap: 8px;">
                                            <span class="entity-type-badge entity-type-${escapeHtml((ee.entity_type || '').toLowerCase())}">${escapeHtml(ENTITY_LABELS[ee.entity_type] || ee.entity_type)}</span>
                                            <span style="font-size: 12.5px; color: #171a21; font-weight: 500;">${escapeHtml(ee.entity_value)}</span>
                                        </div>
                                        <span style="font-size: 11px; color: var(--text-muted);">Conf: ${ee.confidence_score ? Number(ee.confidence_score).toFixed(2) : '1.00'}</span>
                                    </div>
                                    `).join('')}
                                </div>
                            </div>` : '<p style="font-size: 12px; color: var(--text-muted); font-style: italic; margin: 0;">Thực thể khác được lưu trong Neo4j.</p>'}
                        </div>
                    </div>
                `).join('');
            } else {
                clausesList.innerHTML = '<p style="color: var(--text-muted); font-style: italic; text-align: center; padding: 20px 0;">No clauses extracted yet.</p>';
            }
        }

        // 10. Update Executive Summary Tab Text
        const aiSummaryText = document.getElementById('ai-summary-text');
        if (aiSummaryText && contract.ai_summary) {
            aiSummaryText.textContent = contract.ai_summary.summary || '';
        }
    } catch (err) {
        console.error("AJAX contract refresh error:", err);
    }
};

function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

// Parties the user enters (the AI does not guess them) and tags from the administrator's list.
document.addEventListener('DOMContentLoaded', () => {
    const box = document.getElementById('contract-parties');
    if (!box) return;
    const rows = document.getElementById('party-rows');
    const status = document.getElementById('party-status');
    const contractId = box.dataset.contractId;
    const newRow = () => {
        const row = document.createElement('div');
        row.className = 'party-row';
        row.style.cssText = 'display: grid; grid-template-columns: 110px 1.6fr 1fr 1fr 1fr 32px; gap: 6px;';
        row.innerHTML = '<select class="form-control" name="party_type" aria-label="Vai trò"><option>Bên A</option><option>Bên B</option><option>Bên khác</option></select>' +
            '<input class="form-control" name="party_name" placeholder="Tên tổ chức / cá nhân" aria-label="Tên">' +
            '<input class="form-control" name="tax_code" placeholder="Mã số thuế" aria-label="Mã số thuế">' +
            '<input class="form-control" name="email" placeholder="Email" aria-label="Email">' +
            '<input class="form-control" name="phone" placeholder="Điện thoại" aria-label="Điện thoại">' +
            '<button type="button" class="btn btn-secondary party-remove" aria-label="Xóa bên" style="padding: 0;">×</button>';
        const taken = [...rows.querySelectorAll('select[name=party_type]')].map(s => s.value);
        row.querySelector('select').value = !taken.includes('Bên A') ? 'Bên A' : !taken.includes('Bên B') ? 'Bên B' : 'Bên khác';
        rows.appendChild(row);
    };
    if (!rows.children.length) { newRow(); newRow(); }
    document.getElementById('party-add').addEventListener('click', newRow);
    rows.addEventListener('click', event => {
        if (event.target.classList.contains('party-remove')) event.target.closest('.party-row').remove();
    });
    document.getElementById('party-save').addEventListener('click', async () => {
        const parties = [...rows.querySelectorAll('.party-row')].map(row => Object.fromEntries(
            [...row.querySelectorAll('select, input')].map(field => [field.name, field.value.trim()]))).filter(p => p.party_name);
        const tagIds = [...document.querySelectorAll('.tag-pick:checked')].map(box => Number(box.value));
        status.textContent = 'Đang lưu…';
        try {
            const send = (path, body) => fetch(`/api/contracts/${contractId}/${path}/`, {method: 'POST',
                headers: {'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken')}, body: JSON.stringify(body)}).then(r => r.json());
            const [saved, tagged] = await Promise.all([send('parties', {parties}), send('tags', {tag_ids: tagIds})]);
            if (!saved.success) throw new Error(saved.error || 'Không lưu được các bên.');
            if (!tagged.success) throw new Error(tagged.error || 'Không lưu được tag.');
            status.textContent = `Đã lưu ${saved.parties.length} bên và ${tagIds.length} tag.`;
        } catch (error) {
            status.textContent = error.message;
        }
    });
});

// Delete contract (managers): postponed only while an extraction/analysis job or ledger work is still running.
document.addEventListener('DOMContentLoaded', () => {
    const button = document.getElementById('btn-delete-contract');
    if (!button) return;
    button.addEventListener('click', async () => {
        const id = button.dataset.contractId;
        const code = button.dataset.contractCode || id;
        const typed = window.prompt(`Xoá vĩnh viễn hợp đồng ${code}: mọi phiên bản, tệp, kết quả trích xuất, phân tích rủi ro, `
            + `đồ thị, chỉ mục tìm kiếm và quy trình duyệt sẽ bị xoá và không khôi phục được. Giao dịch đã ghi trên `
            + `blockchain vẫn còn trên sổ cái (chỉ xoá bản sao trong hệ thống).\n\nNhập mã hợp đồng để xác nhận:`);
        if (typed === null) return;
        if (typed.trim() !== code) {
            window.alert('Mã hợp đồng không khớp; hợp đồng chưa bị xoá.');
            return;
        }
        button.disabled = true;
        try {
            const response = await fetch(`/api/contracts/${id}/`, {
                method: 'DELETE',
                headers: { 'X-CSRFToken': getCookie('csrftoken') },
                credentials: 'same-origin'
            });
            const body = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(body.error || `Lỗi ${response.status}`);
            window.location.href = '/';
        } catch (error) {
            window.alert('Không xoá được hợp đồng: ' + error.message);
            button.disabled = false;
        }
    });
});


// Q&A on this contract: the question is answered in the background job queue, the tab follows it.
(function () {
    const form = document.getElementById('contract-qa-form');
    if (!form) return;
    const status = document.getElementById('contract-qa-status');
    const answer = document.getElementById('contract-qa-answer');
    const sources = document.getElementById('contract-qa-sources');
    const stages = {queued: 'Đang chờ xử lý', retrieving: 'Đang tìm trong hợp đồng', reranking: 'Đang xếp hạng nguồn',
        reading_graph: 'Đang đọc cấu trúc hợp đồng', planning_questions: 'Đang phân tích câu hỏi',
        generating: 'Đang soạn câu trả lời', repairing_citations: 'Đang kiểm tra trích dẫn', verifying: 'Đang rà soát câu trả lời'};
    async function call(url, body) {
        const response = await fetch(url, body ? {method: 'POST', headers: {'Content-Type': 'application/json',
            'X-CSRFToken': getCookie('csrftoken')}, body: JSON.stringify(body)} : {});
        const data = await response.json().catch(() => ({}));
        if (!response.ok || data.success === false) throw new Error(data.error || 'Không thực hiện được yêu cầu.');
        return data;
    }
    form.addEventListener('submit', async event => {
        event.preventDefault();
        const query = document.getElementById('contract-qa-question').value.trim();
        if (!query) { status.textContent = 'Nhập câu hỏi trước.'; return; }
        const button = form.querySelector('button');
        button.disabled = true;
        answer.textContent = '';
        sources.replaceChildren();
        status.textContent = stages.queued;
        try {
            const job = await call('/api/newidea/jobs/', {query, version_id: Number(form.dataset.versionId), generate: true, mode: 'structural'});
            let result = null;
            for (let attempt = 0; attempt < 300 && !result; attempt++) {
                await new Promise(resolve => setTimeout(resolve, 2000));
                const receipt = await call(`/api/newidea/jobs/?id=${job.search_id}`);
                if (receipt.status === 'COMPLETED') result = receipt.result.response || {};
                else if (receipt.status === 'FAILED') throw new Error(receipt.result.error || 'Không trả lời được câu hỏi.');
                else status.textContent = stages[(receipt.result.progress || {}).stage] || stages.queued;
            }
            if (!result) throw new Error('Câu hỏi vẫn đang được xử lý, hãy thử lại sau.');
            status.textContent = '';
            answer.textContent = result.answer_text || result.answer || 'Chưa tìm được bằng chứng đủ để trả lời.';
            (result.citations || []).forEach(source => {
                const row = document.createElement('div');
                row.style.cssText = 'border-left: 3px solid rgba(37, 99, 235, 0.6); padding: 6px 10px; background: rgba(15, 23, 42, 0.025); border-radius: 4px; font-size: 13px;';
                const head = document.createElement(source.source_url ? 'a' : 'strong');
                head.textContent = `[${source.evidence_id}] ${source.source_location || source.original_name || ''}`;
                if (source.source_url) { head.href = source.source_url; head.target = '_blank'; head.rel = 'noopener'; head.style.color = '#05359d'; }
                const text = document.createElement('p');
                text.textContent = source.text || '';
                text.style.margin = '4px 0 0';
                row.append(head, text);
                sources.append(row);
            });
        } catch (error) {
            status.textContent = error.message;
        } finally {
            button.disabled = false;
        }
    });
})();

// Legal text mark: the user says whether this document is law, and its number, status and effective date.
(function () {
    const box = document.getElementById('contract-legal');
    if (!box) return;
    const flag = document.getElementById('legal-flag');
    const fields = document.getElementById('legal-fields');
    const message = document.getElementById('legal-status-msg');
    const inputs = ['legal-number', 'legal-status', 'legal-effective', 'legal-title'].map(id => document.getElementById(id));
    const sync = () => {
        inputs.forEach(input => { input.disabled = !flag.checked; });
        fields.style.opacity = flag.checked ? '1' : '.5';
    };
    flag.addEventListener('change', sync);
    document.getElementById('legal-save').addEventListener('click', async () => {
        const [number, status, effective, title] = inputs;
        message.textContent = 'Đang lưu...';
        try {
            const response = await fetch(`/api/contracts/${box.dataset.contractId}/legal/`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken')},
                body: JSON.stringify({is_legal: flag.checked, number: number.value, status: status.value,
                                      effective_on: effective.value, title: title.value}),
            });
            const data = await response.json().catch(() => ({}));
            if (!response.ok || !data.success) throw new Error(data.error || 'Không lưu được đánh dấu.');
            message.textContent = data.extraction_job_id
                ? 'Đã lưu. Tài liệu đang được trích xuất lại để AI đọc đúng các điều.'
                : 'Đã lưu.';
        } catch (error) {
            message.textContent = error.message;
        }
    });
})();
