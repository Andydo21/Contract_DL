/* ─────────────────────────────────────────────
   Dynamic Workflow Builder – JavaScript (Enterprise)
   ───────────────────────────────────────────── */

(function () {
    'use strict';

    const U = WorkflowUtils;

    /* ── DOM References ── */
    const btnGenerate = document.getElementById('btn-generate');
    const btnReset = document.getElementById('btn-reset');

    // Inputs
    const titleInput = document.getElementById('build-title');
    const typeInput = document.getElementById('build-type');
    const deptInput = document.getElementById('build-department');
    const valueInput = document.getElementById('build-value');
    const riskInput = document.getElementById('build-risk');
    const contentInput = document.getElementById('build-content');

    // Toggles
    const ruleLegal = document.getElementById('rule-legal');
    const ruleFinance = document.getElementById('rule-finance');
    const ruleCeo = document.getElementById('rule-ceo');
    const ruleArchive = document.getElementById('rule-archive');
    const ruleIntl = document.getElementById('rule-international');
    const rulePersonalData = document.getElementById('rule-personal-data');
    const ruleNda = document.getElementById('rule-nda');

    // Output Panels
    const outputEmpty = document.getElementById('output-empty');
    const outputLoading = document.getElementById('output-loading');
    const outputResult = document.getElementById('output-result');
    const outputSummary = document.getElementById('output-summary');
    const outputSteps = document.getElementById('output-steps');

    // Output Actions
    const btnExport = document.getElementById('btn-export');
    const btnCopy = document.getElementById('btn-copy');

    let currentWorkflowData = null;

    /* ── Collect Data ── */
    function collectContractData() {
        return {
            title: titleInput.value.trim(),
            contract_type: typeInput.value,
            department: deptInput.value,
            contract_value: parseFloat(valueInput.value.replace(/,/g, '')) || 0,
            risk_level: riskInput.value,
            content: contentInput.value.trim(),
        };
    }

    function collectBusinessRules() {
        return {
            require_legal_review: ruleLegal ? ruleLegal.checked : false,
            require_finance_review: ruleFinance ? ruleFinance.checked : false,
            require_ceo_approval: ruleCeo ? ruleCeo.checked : false,
            auto_archive: ruleArchive ? ruleArchive.checked : false,
            international: ruleIntl ? ruleIntl.checked : false,
            personal_data: rulePersonalData ? rulePersonalData.checked : false,
            nda_required: ruleNda ? ruleNda.checked : false,
        };
    }

    /* ── Render Workflow Steps ── */
    function renderWorkflow() {
        if (!currentWorkflowData || !currentWorkflowData.workflow) return;
        const steps = currentWorkflowData.workflow;

        let totalDays = 0;
        const teams = new Set();

        // Enrich and calculate
        const enrichedSteps = steps.map(s => {
            const meta = U.getStepMeta(s.step);
            const owner = s.owner || meta.owner;
            const days = s.estimated_days !== undefined ? s.estimated_days : meta.days;

            totalDays += days;
            if (owner && owner.toLowerCase() !== 'system') {
                teams.add(owner);
            }

            return {
                ...meta,
                name: s.step,
                owner: owner,
                days: days
            };
        });

        // Summary
        outputSummary.innerHTML = `
            <div class="os-item">
                <div class="os-value">${enrichedSteps.length}</div>
                <div class="os-label">Total Steps</div>
            </div>
            <div class="os-item">
                <div class="os-value">${teams.size}</div>
                <div class="os-label">Teams Involved</div>
            </div>
            <div class="os-item">
                <div class="os-value">${totalDays}</div>
                <div class="os-label">Estimated Days</div>
            </div>
        `;

        // Steps
        outputSteps.innerHTML = '';
        enrichedSteps.forEach((step, index) => {
            const card = document.createElement('div');
            card.className = 'step-card';
            card.style.animationDelay = (index * 0.05) + 's';

            const priorityColor = U.getPriorityColor(step.priority);

            card.innerHTML = `
                <div class="sc-order">${index + 1}</div>
                <div class="sc-icon"><i class="fa-solid ${step.icon}"></i></div>
                <div class="sc-body">
                    <div class="sc-name">${step.name}</div>
                    <div class="sc-desc">${step.desc}</div>
                    <div class="sc-meta">
                        <span><i class="fa-solid fa-user"></i> ${step.owner}</span>
                        <span><i class="fa-solid fa-clock"></i> ${step.days === 0 ? 'Instant' : step.days + (step.days === 1 ? ' day' : ' days')}</span>
                        <span class="sc-priority" style="background-color: ${priorityColor}20; color: ${priorityColor}">${step.priority}</span>
                    </div>
                </div>
                <div class="sc-actions">
                    <button class="sc-action-btn" data-action="up" data-index="${index}" title="Move Up"><i class="fa-solid fa-arrow-up"></i></button>
                    <button class="sc-action-btn" data-action="down" data-index="${index}" title="Move Down"><i class="fa-solid fa-arrow-down"></i></button>
                    <button class="sc-action-btn danger" data-action="remove" data-index="${index}" title="Remove"><i class="fa-solid fa-trash"></i></button>
                </div>
            `;
            outputSteps.appendChild(card);
        });

        U.hideElement(outputEmpty);
        U.hideElement(outputLoading);
        U.showElement(outputResult);
    }

    /* ── Action Handlers: Move/Remove ── */
    outputSteps.addEventListener('click', function (e) {
        const btn = e.target.closest('.sc-action-btn');
        if (!btn || !currentWorkflowData || !currentWorkflowData.workflow) return;

        const action = btn.dataset.action;
        const index = parseInt(btn.dataset.index, 10);
        const steps = currentWorkflowData.workflow;

        if (action === 'remove') {
            steps.splice(index, 1);
            U.showToast('Step removed', 'info');
        } else if (action === 'up' && index > 0) {
            const temp = steps[index];
            steps[index] = steps[index - 1];
            steps[index - 1] = temp;
        } else if (action === 'down' && index < steps.length - 1) {
            const temp = steps[index];
            steps[index] = steps[index + 1];
            steps[index + 1] = temp;
        }

        // Re-render to update order/indexes
        if (action === 'remove' || (action === 'up' && index > 0) || (action === 'down' && index < steps.length - 1)) {
            renderWorkflow();
        }
    });

    /* ── Generate Handler ── */
    btnGenerate.addEventListener('click', async function () {
        const contractData = collectContractData();
        const businessRules = collectBusinessRules();

        const payload = {
            ...contractData,
            business_rules: businessRules,
        };

        // Loading State
        U.hideElement(outputEmpty);
        U.hideElement(outputResult);
        U.showElement(outputLoading);
        btnGenerate.disabled = true;
        btnGenerate.querySelector('.btn-text').textContent = 'Building...';

        try {
            const data = await U.fetchJSON('/workflow/api/build/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            currentWorkflowData = data;
            renderWorkflow();
            U.showToast('Workflow generated successfully!', 'success');
        } catch (err) {
            U.hideElement(outputLoading);
            U.showElement(outputEmpty);
            U.showToast(err.message || 'Failed to build workflow', 'error');
        } finally {
            btnGenerate.disabled = false;
            btnGenerate.querySelector('.btn-text').textContent = 'Generate Workflow';
        }
    });

    /* ── Reset Handler ── */
    btnReset.addEventListener('click', function () {
        document.getElementById('builder-form').reset();

        if (ruleLegal) ruleLegal.checked = true;
        if (ruleFinance) ruleFinance.checked = true;
        if (ruleCeo) ruleCeo.checked = false;
        if (ruleArchive) ruleArchive.checked = true;
        if (ruleIntl) ruleIntl.checked = false;
        if (rulePersonalData) rulePersonalData.checked = false;
        if (ruleNda) ruleNda.checked = false;

        currentWorkflowData = null;

        U.hideElement(outputResult);
        U.hideElement(outputLoading);
        U.showElement(outputEmpty);

        U.showToast('Builder reset', 'info');
    });

    /* ── Export / Copy Handlers ── */
    btnExport.addEventListener('click', function () {
        if (currentWorkflowData && currentWorkflowData.workflow) {
            U.downloadJSON(currentWorkflowData.workflow, 'dynamic_workflow.json');
        }
    });

    btnCopy.addEventListener('click', function () {
        if (currentWorkflowData && currentWorkflowData.workflow) {
            U.copyToClipboard(JSON.stringify(currentWorkflowData.workflow, null, 2));
        }
    });

})();
