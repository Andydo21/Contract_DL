document.addEventListener('DOMContentLoaded', () => {
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
        if (score >= 80) {
            gauge.style.stroke = '#ef4444';
            gaugeStatus.innerHTML = 'High Risk';
            gaugeStatus.className = 'gauge-status score-high';
        } else if (score >= 50) {
            gauge.style.stroke = '#f97316';
            gaugeStatus.innerHTML = 'Medium Risk';
            gaugeStatus.className = 'gauge-status score-medium';
        } else {
            gauge.style.stroke = '#10b981';
            gaugeStatus.innerHTML = 'Low Risk';
            gaugeStatus.className = 'gauge-status score-low';
        }
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
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ final_risk_level, comment })
                });
                
                const data = await res.json();
                if (data.success) {
                    // Reload the detail page to show approved status
                    window.location.reload();
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
    const scannerLoader = document.getElementById('scanner-loader');
    
    triggerButtons.forEach(btn => {
        btn.addEventListener('click', async () => {
            const contractId = btn.dataset.contractId;
            if (scannerLoader) scannerLoader.classList.add('active');
            
            try {
                const res = await fetch(`/api/contracts/${contractId}/analyze/`, {
                    method: 'POST'
                });
                const data = await res.json();
                
                setTimeout(() => {
                    if (scannerLoader) scannerLoader.classList.remove('active');
                    if (data.success) {
                        window.location.reload();
                    } else {
                        const errorMsg = data.error || "Unknown error";
                        const isModelError = errorMsg.includes("503") || errorMsg.includes("communication failed") || errorMsg.includes("not loaded");
                        if (isModelError) {
                            showToast("Hệ thống chưa kết nối được với mô hình AI. Vui lòng tải mô hình hoặc kích hoạt GPU để tiến hành phân tích hợp đồng.", "warning");
                        } else {
                            showToast(errorMsg, "error");
                        }
                    }
                }, 2500); // 2.5s simulation loader duration
            } catch (err) {
                if (scannerLoader) scannerLoader.classList.remove('active');
                console.error(err);
                showToast("Lỗi kết nối: Không thể gửi yêu cầu phân tích tới hệ thống.", "error");
            }
        });
    });

    // 4. Version switcher dropdown event
    const versionSelect = document.getElementById('version-select');
    if (versionSelect) {
        versionSelect.addEventListener('change', (e) => {
            const versionId = e.target.value;
            const url = new URL(window.location.href);
            url.searchParams.set('version_id', versionId);
            window.location.href = url.toString();
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
            btn.style.color = '#ffffff';
            
            const targetTab = btn.dataset.tab;
            const panes = document.querySelectorAll('.tab-pane');
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
    
    if (fileZone && fileInput) {
        fileInput.addEventListener('change', () => {
            if (fileInput.files.length > 0) {
                selectedFileName.style.display = 'block';
                selectedFileName.innerHTML = `<i class="fa-solid fa-file-circle-check"></i> Selected: ${fileInput.files[0].name}`;
            } else {
                selectedFileName.style.display = 'none';
                selectedFileName.innerHTML = '';
            }
        });
        
        // Drag and drop events
        ['dragenter', 'dragover'].forEach(eventName => {
            fileZone.addEventListener(eventName, (e) => {
                e.preventDefault();
                fileZone.style.borderColor = 'var(--accent-primary)';
                fileZone.style.background = 'rgba(99, 102, 241, 0.08)';
            }, false);
        });
        
        ['dragleave', 'drop'].forEach(eventName => {
            fileZone.addEventListener(eventName, (e) => {
                e.preventDefault();
                fileZone.style.borderColor = 'rgba(99, 102, 241, 0.3)';
                fileZone.style.background = 'rgba(99, 102, 241, 0.02)';
            }, false);
        });
        
        fileZone.addEventListener('drop', (e) => {
            const dt = e.dataTransfer;
            const files = dt.files;
            if (files.length > 0) {
                fileInput.files = files;
                selectedFileName.style.display = 'block';
                selectedFileName.innerHTML = `<i class="fa-solid fa-file-circle-check"></i> Selected: ${files[0].name}`;
            }
        });
    }

    // Submit new version form via AJAX
    const uploadForm = document.getElementById('upload-version-form');
    if (uploadForm) {
        uploadForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            
            const analyzeBtn = document.getElementById('btn-detail-reanalyze') || document.getElementById('btn-detail-trigger-analysis');
            if (!analyzeBtn) {
                alert("Contract ID not found on page.");
                return;
            }
            const contractId = analyzeBtn.dataset.contractId;
            
            if (uploadModal) uploadModal.classList.remove('active');
            
            if (scannerLoader) {
                scannerLoader.classList.add('active');
                const scannerText = scannerLoader.querySelector('.scanner-text');
                if (scannerText) scannerText.innerHTML = "UPLOADING & SCANNING NEW VERSION...";
            }
            
            const formData = new FormData(uploadForm);
            const activeTabPane = document.querySelector('.tab-pane.active');
            if (activeTabPane.id === 'file-tab') {
                formData.delete('raw_content');
            } else {
                formData.delete('file');
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
                        if (data.scan_error) {
                            showToast("Phiên bản mới đã được tải lên, nhưng hệ thống chưa kết nối được với mô hình AI để phân tích ngay. Bạn có thể bấm Phân tích lại sau.", "warning");
                            setTimeout(() => {
                                window.location.href = `/contracts/${contractId}/?version_id=${data.version_id}`;
                            }, 3000);
                        } else {
                            window.location.href = `/contracts/${contractId}/?version_id=${data.version_id}`;
                        }
                    } else {
                        const errorMsg = data.error || "Unknown error";
                        const isModelError = errorMsg.includes("503") || errorMsg.includes("communication failed") || errorMsg.includes("not loaded");
                        if (isModelError) {
                            showToast("Phiên bản mới đã được tải lên, nhưng hệ thống chưa kết nối được với mô hình AI để phân tích ngay. Bạn có thể bấm Phân tích lại sau.", "warning");
                            setTimeout(() => {
                                window.location.href = `/contracts/${contractId}/?version_id=${data.version_id || ''}`;
                            }, 3000);
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
});

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
                background: rgba(13, 17, 23, 0.95);
                border: 1px solid rgba(239, 68, 68, 0.2);
                border-left: 4px solid #ef4444;
                color: #ffffff;
                padding: 16px 20px;
                border-radius: 12px;
                box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.5), 0 8px 10px -6px rgba(0, 0, 0, 0.5);
                backdrop-filter: blur(12px);
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
            .toast-icon {
                font-size: 20px;
                color: #ef4444;
                flex-shrink: 0;
            }
            .toast-card.warning .toast-icon {
                color: #f59e0b;
            }
            .toast-content {
                display: flex;
                flex-direction: column;
                gap: 4px;
            }
            .toast-title {
                font-family: 'Outfit', sans-serif;
                font-weight: 600;
                font-size: 14.5px;
            }
            .toast-desc {
                font-size: 12.5px;
                color: rgba(255, 255, 255, 0.7);
                line-height: 1.4;
            }
            .toast-close {
                margin-left: auto;
                background: none;
                border: none;
                color: rgba(255, 255, 255, 0.4);
                cursor: pointer;
                padding: 4px;
                transition: color 0.2s;
            }
            .toast-close:hover {
                color: #ffffff;
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
    
    const iconClass = type === 'warning' ? 'fa-solid fa-triangle-exclamation' : 'fa-solid fa-circle-exclamation';
    const titleText = type === 'warning' ? 'Cảnh Báo Hệ Thống' : 'Lỗi Hệ Thống';

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

// Toggle folding/unfolding of risk findings (Global helper)
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
