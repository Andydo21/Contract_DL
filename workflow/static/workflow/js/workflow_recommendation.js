/* ─────────────────────────────────────────────
   Workflow Recommendation – JavaScript (Enterprise)
   ───────────────────────────────────────────── */

(function () {
    'use strict';

    const U = WorkflowUtils;

    /* ── DOM References ── */
    const form = document.getElementById('recommend-form');
    const btnRecommend = document.getElementById('btn-recommend');

    // Inputs
    const titleInput = document.getElementById('rec-title');
    const typeInput = document.getElementById('rec-type');
    const deptInput = document.getElementById('rec-department');
    const valueInput = document.getElementById('rec-value');
    const riskInput = document.getElementById('rec-risk');
    const contentInput = document.getElementById('rec-content');

    // UI Feedback Elements
    const valueFormatted = document.getElementById('rec-value-formatted');
    const riskBadge = document.getElementById('rec-risk-badge');
    const charCount = document.getElementById('rec-char-count');

    // State Panels
    const resultEmpty = document.getElementById('result-empty');
    const resultLoading = document.getElementById('result-loading');
    const resultContent = document.getElementById('result-content');

    // Result Fields
    const resWorkflowName = document.getElementById('res-workflow-name');
    const resCategory = document.getElementById('res-category');
    const resConfidenceVal = document.getElementById('res-confidence-val');
    const resConfidenceFill = document.getElementById('res-confidence-fill');
    const resDuration = document.getElementById('res-duration');
    const resApprovalLevel = document.getElementById('res-approval-level');
    const resRiskLevel = document.getElementById('res-risk-level');
    const resDepartments = document.getElementById('res-departments');
    const reasoningGrid = document.getElementById('reasoning-grid');
    const recTimeline = document.getElementById('rec-timeline');
    const resultSummary = document.getElementById('result-summary');

    /* ── 1. Live Validation & Form Feedback ── */
    function updateValidation() {
        const isValid = titleInput.value.trim() !== '' && typeInput.value !== '';
        btnRecommend.disabled = !isValid;
    }

    titleInput.addEventListener('input', updateValidation);
    typeInput.addEventListener('change', updateValidation);
    U.attachLiveValidation(['rec-title', 'rec-type']);

    /* ── 2. Character Counter ── */
    contentInput.addEventListener('input', function () {
        charCount.textContent = U.formatNumber(this.value.length);
    });

    /* ── 3. Contract Value Formatting ── */
    valueInput.addEventListener('input', function () {
        const val = this.value.replace(/,/g, '');
        if (val && !isNaN(val)) {
            valueFormatted.textContent = U.formatCurrency(val);
        } else {
            valueFormatted.textContent = '';
        }
    });

    /* ── 4. Risk Badge Update ── */
    riskInput.addEventListener('change', function () {
        const val = this.value;
        riskBadge.textContent = val;
        riskBadge.className = `risk-badge risk-${val}`;
    });

    /* ── Collect Data ── */
    function collectFormData() {
        return {
            title: titleInput.value.trim(),
            contract_type: typeInput.value,
            department: deptInput.value,
            contract_value: parseFloat(valueInput.value.replace(/,/g, '')) || 0,
            risk_level: riskInput.value,
            content: contentInput.value.trim(),
        };
    }

    /* ── Render Result ── */
    function renderResult(data, payload) {
        // Hero Card
        resWorkflowName.textContent = data.workflow_name || 'Recommended Workflow';
        const typeOption = typeInput.options[typeInput.selectedIndex];
        resCategory.textContent = typeOption && typeOption.value ? typeOption.text : 'General';

        // Confidence Animation
        const conf = data.confidence || 0;
        resConfidenceVal.textContent = conf + '%';
        setTimeout(() => {
            resConfidenceFill.style.width = conf + '%';
        }, 50);

        // Process Steps & Meta
        const steps = data.steps || [];
        let totalDays = 0;
        const departments = new Set();

        const enrichedSteps = steps.map(stepName => {
            const meta = U.getStepMeta(stepName);
            totalDays += meta.days;
            if (meta.owner && meta.owner.toLowerCase() !== 'system') {
                departments.add(meta.owner);
            }
            return meta;
        });

        // Meta Grid
        resDuration.textContent = `${totalDays} day${totalDays !== 1 ? 's' : ''}`;
        resApprovalLevel.textContent = steps.length > 5 ? 'High' : (steps.length > 3 ? 'Medium' : 'Standard');
        resRiskLevel.textContent = payload.risk_level;
        resDepartments.textContent = departments.size > 0 ? Array.from(departments).join(', ') : 'None';

        // 9. Enriched Reasoning Cards
        reasoningGrid.innerHTML = '';
        const reasons = data.reasoning || [];
        reasons.forEach((reason, i) => {
            const card = document.createElement('div');
            card.className = 'reason-card';
            card.style.animationDelay = (i * 0.1) + 's';
            card.innerHTML = `
                <div class="reason-icon"><i class="fa-solid fa-check"></i></div>
                <div class="reason-text">${reason}</div>
            `;
            reasoningGrid.appendChild(card);
        });

        // 10. Enriched Timeline
        recTimeline.innerHTML = '';
        enrichedSteps.forEach((step, index) => {
            const el = document.createElement('div');
            el.className = 'tl-step';
            el.style.animationDelay = (index * 0.08) + 's';

            const statusConfig = U.getStatusConfig('pending');
            const priorityColor = U.getPriorityColor(step.priority);

            el.innerHTML = `
                <div class="tl-dot status-pending"><i class="fa-solid ${statusConfig.icon}"></i></div>
                <div class="tl-card">
                    <div class="tl-step-icon"><i class="fa-solid ${step.icon}"></i></div>
                    <div class="tl-body">
                        <div class="tl-step-name">${step.name}</div>
                        <div class="tl-step-desc">${step.desc}</div>
                        <div class="tl-meta">
                            <span><i class="fa-solid fa-user"></i> ${step.owner}</span>
                            <span><i class="fa-solid fa-clock"></i> ${step.days} day${step.days !== 1 ? 's' : ''}</span>
                            <span class="tl-status-badge" style="background-color: ${priorityColor}20; color: ${priorityColor}">${step.priority} Priority</span>
                        </div>
                    </div>
                </div>
            `;
            recTimeline.appendChild(el);
        });

        // 11. Summary Panel
        resultSummary.innerHTML = `
            <div class="summary-item">
                <div class="summary-value">${steps.length}</div>
                <div class="summary-label">Steps</div>
            </div>
            <div class="summary-item">
                <div class="summary-value">${departments.size}</div>
                <div class="summary-label">Teams</div>
            </div>
            <div class="summary-item">
                <div class="summary-value">${totalDays}</div>
                <div class="summary-label">Days Est.</div>
            </div>
            <div class="summary-item">
                <div class="summary-value" style="color: var(--green)">${conf}%</div>
                <div class="summary-label">Match Score</div>
            </div>
        `;

        U.hideElement(resultEmpty);
        U.hideElement(resultLoading);
        U.showElement(resultContent);
    }

    /* ── Form Submit Handler ── */
    form.addEventListener('submit', async function (e) {
        e.preventDefault();

        const v = U.validateRequired(['rec-title', 'rec-type']);
        if (!v.valid) {
            U.showToast('Please fill in required fields.', 'warning');
            return;
        }

        const payload = collectFormData();

        // Loading State
        U.hideElement(resultEmpty);
        U.hideElement(resultContent);
        U.showElement(resultLoading);
        resConfidenceFill.style.width = '0%';
        btnRecommend.disabled = true;
        btnRecommend.querySelector('.btn-text').textContent = 'Generating...';

        try {
            const data = await U.fetchJSON('/workflow/api/recommend/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            renderResult(data, payload);
            U.showToast('Recommendation generated successfully!', 'success');
        } catch (err) {
            // Handle Errors
            U.hideElement(resultLoading);
            U.showElement(resultEmpty);
            U.showToast(err.message || 'Failed to generate recommendation', 'error');
        } finally {
            btnRecommend.disabled = false;
            btnRecommend.querySelector('.btn-text').textContent = 'Generate Recommendation';
        }
    });

})();
