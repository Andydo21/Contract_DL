/**
 * Workflow Board Logic - Contract Guard AI
 * Handles real-time loading, filtering, and step-by-step approvals of contract workflows.
 */

// Global State
let allWorkflows = [];
let currentFilter = 'ALL';
let activeStepId = null;
let currentUserId = window.currentUserId || 1; // Default fallback user ID
let currentUserRole = window.currentUserRole || '';
let currentUserIsSuperuser = window.currentUserIsSuperuser || false;

const roleIdToNameMap = {
    1: 'ADMIN',
    2: 'EXPERT',
    3: 'VIEWER',
    4: 'LEGAL_EXPERT',
    5: 'MANAGER',
    6: 'FINANCE',
    7: 'TECHNICAL',
    8: 'SECURITY',
    9: 'COMPLIANCE',
    10: 'PROCUREMENT',
    11: 'EXECUTIVE'
};

document.addEventListener('DOMContentLoaded', () => {
    // Initialize UI Event Listeners
    initEventListeners();
    
    // Initial fetch of workflows
    fetchWorkflows();
});

/**
 * Register DOM event listeners
 */
function initEventListeners() {
    // Refresh button
    const btnRefresh = document.getElementById('btn-refresh');
    if (btnRefresh) {
        btnRefresh.addEventListener('click', () => {
            fetchWorkflows();
        });
    }

    // Filter Buttons
    const filterButtons = document.querySelectorAll('.filter-bar .filter-btn');
    filterButtons.forEach(btn => {
        btn.addEventListener('click', (e) => {
            // Remove active class from all
            filterButtons.forEach(b => b.classList.remove('active'));
            // Add active class to clicked
            e.currentTarget.classList.add('active');
            // Update filter state and render
            currentFilter = e.currentTarget.getAttribute('data-filter');
            renderWorkflows();
        });
    });

    // Modal Close
    const modalClose = document.getElementById('modal-close');
    const modalOverlay = document.getElementById('approve-modal');
    if (modalClose) {
        modalClose.addEventListener('click', closeModal);
    }
    if (modalOverlay) {
        modalOverlay.addEventListener('click', (e) => {
            if (e.target === modalOverlay) closeModal();
        });
    }

    // Approve Action
    const btnApprove = document.getElementById('btn-approve');
    if (btnApprove) {
        btnApprove.addEventListener('click', () => submitReview('APPROVED'));
    }

    // Reject Action
    const btnReject = document.getElementById('btn-reject');
    if (btnReject) {
        btnReject.addEventListener('click', () => submitReview('REJECTED'));
    }
}

/**
 * Fetch all workflows via Django proxy endpoint
 */
async function fetchWorkflows() {
    showLoading(true);
    try {
        const response = await fetch('/api/workflows/');
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data = await response.json();
        allWorkflows = data.workflows || [];
        updateStats();
        renderWorkflows();
    } catch (error) {
        console.error('Failed to fetch workflows:', error);
        showToast('Error loading workflows. Please try again.', 'error');
        renderErrorState();
    } finally {
        showLoading(false);
    }
}

/**
 * Show / Hide loading spinner
 */
function showLoading(isLoading) {
    const loadingState = document.getElementById('loading-state');
    const grid = document.getElementById('workflow-grid');
    
    if (isLoading) {
        if (!loadingState && grid) {
            grid.innerHTML = `
                <div class="loading-state" id="loading-state">
                    <div class="spinner"></div>
                    <p>Loading workflows...</p>
                </div>
            `;
        }
    } else {
        if (loadingState) {
            loadingState.remove();
        }
    }
}

/**
 * Update the Topbar statistic counts
 */
function updateStats() {
    const total = allWorkflows.length;
    const pending = allWorkflows.filter(w => w.status === 'PENDING').length;
    const inProgress = allWorkflows.filter(w => w.status === 'IN_PROGRESS').length;
    const completed = allWorkflows.filter(w => w.status === 'COMPLETED').length;

    updateStatElement('count-total', total);
    updateStatElement('count-pending', pending);
    updateStatElement('count-progress', inProgress);
    updateStatElement('count-done', completed);
}

function updateStatElement(id, value) {
    const el = document.getElementById(id);
    if (el) {
        el.innerText = value;
    }
}

/**
 * Render workflows on grid according to filter
 */
function renderWorkflows() {
    const grid = document.getElementById('workflow-grid');
    if (!grid) return;

    // Apply Filter
    let filtered = allWorkflows;
    if (currentFilter !== 'ALL') {
        filtered = allWorkflows.filter(w => w.status === currentFilter);
    }

    if (filtered.length === 0) {
        grid.innerHTML = `
            <div class="empty-state">
                <i class="fa-solid fa-folder-open empty-icon"></i>
                <h3>No Workflows Found</h3>
                <p>There are no workflows matching the selected status filter.</p>
            </div>
        `;
        return;
    }

    grid.innerHTML = filtered.map(w => {
        // Find current active step
        let activeStep = null;
        if (w.status === 'PENDING' || w.status === 'IN_PROGRESS') {
            // Sort steps by order
            const sortedSteps = [...w.steps].sort((a, b) => a.step_order - b.step_order);
            activeStep = sortedSteps.find(s => s.status === 'PENDING');
        }

        const dateStr = w.started_at ? new Date(w.started_at).toLocaleString('vi-VN') : 'N/A';
        const completedStr = w.completed_at ? new Date(w.completed_at).toLocaleString('vi-VN') : '';

        // Compute completion progress percentage
        const totalSteps = w.steps.length;
        const approvedSteps = w.steps.filter(s => s.status === 'APPROVED').length;
        const progressPercent = totalSteps > 0 ? Math.round((approvedSteps / totalSteps) * 100) : 0;

        return `
            <div class="wf-card status-${w.status}">
                <div class="wf-card-header">
                    <div class="wf-name" title="${w.workflow_name}">
                        <a href="/workflows/${w.workflow_id}/" style="color: inherit; text-decoration: none; transition: var(--transition);" onmouseover="this.style.color='var(--accent)'" onmouseout="this.style.color='inherit'">
                            ${w.workflow_name}
                        </a>
                    </div>
                    <span class="wf-status-badge badge-${w.status}">${w.status}</span>
                </div>

                <div class="wf-type-row">
                    <span class="wf-type-badge type-${(w.workflow_type || 'WF_GENERAL').toLowerCase()}">
                        <i class="fa-solid fa-robot"></i> ${w.workflow_type || 'WF_GENERAL'}
                    </span>
                </div>

                ${w.reasons ? `
                    <div class="wf-reasons-box">
                        <div class="wf-reasons-header">
                            <i class="fa-solid fa-brain"></i> AI Reasoning
                        </div>
                        <div class="wf-reasons-body">
                            ${w.reasons.split('\n').map(r => `<div class="reason-item">${r}</div>`).join('')}
                        </div>
                    </div>
                ` : ''}

                <div class="wf-progress-track">
                    <div class="progress-bar-wrap">
                        <div class="progress-bar-fill" style="width: ${progressPercent}%"></div>
                    </div>
                    <div class="wf-meta">
                        <span>Progress: ${progressPercent}% (${approvedSteps}/${totalSteps})</span>
                        <span><i class="fa-regular fa-clock"></i> ${dateStr}</span>
                    </div>
                </div>
                
                <div class="wf-steps-list">
                    ${w.steps.map(s => {
                        let statusClass = s.status.toLowerCase();
                        let icon = '<i class="fa-regular fa-circle"></i>';
                        if (s.status === 'APPROVED') {
                            icon = '<i class="fa-solid fa-circle-check"></i>';
                        } else if (s.status === 'REJECTED') {
                            icon = '<i class="fa-solid fa-circle-xmark"></i>';
                        } else if (activeStep && activeStep.id === s.id) {
                            icon = '<i class="fa-solid fa-circle-notch fa-spin"></i>';
                            statusClass += ' active-step';
                        }

                        return `
                            <div class="wf-step-row status-${statusClass}">
                                <div class="step-dot dot-${s.status}">${icon}</div>
                                <div class="step-info">
                                    <div class="step-name">${s.step_name}</div>
                                    <div class="step-status-text">Step ${s.step_order} • ${s.status}</div>
                                </div>
                                ${(activeStep && activeStep.id === s.id) ? (() => {
                                    const requiredRoleName = roleIdToNameMap[s.role_id] || '';
                                    const hasPermission = currentUserIsSuperuser || (currentUserRole === 'ADMIN') || (requiredRoleName === currentUserRole);
                                    if (hasPermission) {
                                        return `
                                            <button class="btn-step-action" onclick="openReviewModal(${s.id}, '${s.step_name}', '${w.workflow_name}')">
                                                Review
                                            </button>
                                        `;
                                    } else {
                                        return `
                                            <button class="btn-step-action" disabled title="Yêu cầu role ${requiredRoleName}">
                                                Locked
                                            </button>
                                        `;
                                    }
                                })() : ''}
                            </div>
                        `;
                    }).join('')}
                </div>

                ${!activeStep ? `
                    <div class="wf-card-footer">
                        <div class="completion-info">
                            ${w.status === 'COMPLETED' ? `
                                <span class="text-success" style="font-size: 12px; font-weight: 600;"><i class="fa-solid fa-circle-check"></i> Fully Approved on ${completedStr}</span>
                            ` : w.status === 'REJECTED' ? `
                                <span class="text-danger" style="font-size: 12px; font-weight: 600;"><i class="fa-solid fa-circle-xmark"></i> Rejected on ${completedStr}</span>
                            ` : `
                                <span class="text-muted" style="font-size: 12px;">Workflow waiting for activation</span>
                            `}
                        </div>
                    </div>
                ` : ''}
            </div>
        `;
    }).join('');
}

/**
 * Render Error/Fallback State
 */
function renderErrorState() {
    const grid = document.getElementById('workflow-grid');
    if (!grid) return;
    grid.innerHTML = `
        <div class="empty-state error">
            <i class="fa-solid fa-triangle-exclamation empty-icon text-danger"></i>
            <h3>Connection Failed</h3>
            <p>Could not communicate with the Workflow microservice. Please verify the service is running locally on port 8003.</p>
            <button class="btn" style="margin-top: 16px; background: var(--accent-primary);" onclick="fetchWorkflows()">
                <i class="fa-solid fa-arrows-rotate"></i> Retry Connection
            </button>
        </div>
    `;
}

/**
 * Open the Approve / Reject Modal
 */
window.openReviewModal = function(stepId, stepName, workflowName) {
    activeStepId = stepId;
    
    const modalStep = document.getElementById('modal-step-name');
    const modalWf = document.getElementById('modal-workflow-name');
    const commentArea = document.getElementById('modal-comment');
    const modalOverlay = document.getElementById('approve-modal');

    if (modalStep) modalStep.innerText = stepName;
    if (modalWf) modalWf.innerText = workflowName;
    if (commentArea) commentArea.value = '';
    
    if (modalOverlay) {
        modalOverlay.style.display = 'flex';
        setTimeout(() => modalOverlay.classList.add('show'), 10);
    }
};

/**
 * Close Modal
 */
function closeModal() {
    const modalOverlay = document.getElementById('approve-modal');
    if (modalOverlay) {
        modalOverlay.classList.remove('show');
        setTimeout(() => {
            modalOverlay.style.display = 'none';
            activeStepId = null;
        }, 300);
    }
}

/**
 * Submit Review status (APPROVED or REJECTED)
 */
async function submitReview(action) {
    if (!activeStepId) return;

    const comment = document.getElementById('modal-comment')?.value || '';
    const btnApprove = document.getElementById('btn-approve');
    const btnReject = document.getElementById('btn-reject');

    // Disable buttons during submission
    if (btnApprove) btnApprove.disabled = true;
    if (btnReject) btnReject.disabled = true;

    try {
        const response = await fetch(`/api/workflows/steps/${activeStepId}/approve/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            },
            body: JSON.stringify({
                action: action,
                comment: comment,
                user_id: currentUserId
            })
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();
        
        if (data.success) {
            showToast(`Step successfully ${action === 'APPROVED' ? 'Approved' : 'Rejected'}!`, 'success');
            closeModal();
            fetchWorkflows(); // Refresh list & stats
        } else {
            showToast(data.error || 'Failed to submit review.', 'error');
        }
    } catch (error) {
        console.error('Error submitting step review:', error);
        showToast('Error communicating with server.', 'error');
    } finally {
        if (btnApprove) btnApprove.disabled = false;
        if (btnReject) btnReject.disabled = false;
    }
}

/**
 * Show animated toast notifications
 */
function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    
    let icon = '<i class="fa-solid fa-info-circle"></i>';
    if (type === 'success') icon = '<i class="fa-solid fa-circle-check"></i>';
    if (type === 'error') icon = '<i class="fa-solid fa-triangle-exclamation"></i>';

    toast.innerHTML = `
        ${icon}
        <span class="toast-message">${message}</span>
    `;

    container.appendChild(toast);

    // Trigger animation
    setTimeout(() => toast.classList.add('show'), 10);

    // Auto remove
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

/**
 * Helper to fetch CSRF token from cookies
 */
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
