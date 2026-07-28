/**
 * workflow_templates.js
 *
 * Manages the Workflow Templates page:
 *  - Fetch & render template cards
 *  - Search + category filter
 *  - Preview drawer (timeline, summary, departments)
 *  - Create template modal (step builder)
 *  - Import template modal (file drop / raw JSON paste)
 *  - Actions: Preview, Duplicate, Export JSON, Copy JSON, Delete
 *
 * Uses WorkflowUtils for toast, loading, and fetch helpers.
 */

/* ─── API endpoints ───────────────────────────────────── */
const TPL_API = {
    list:      '/workflow/api/templates/',
    create:    '/workflow/api/templates/',
    import:    '/workflow/api/templates/import/',
    detail:    (id) => `/workflow/api/templates/${id}/`,
    duplicate: (id) => `/workflow/api/templates/${id}/duplicate/`,
    delete:    (id) => `/workflow/api/templates/${id}/delete/`,
};

/* ─── Category → icon map ─────────────────────────────── */
const CAT_ICONS = {
    Service:     'fa-handshake',
    HR:          'fa-user-tie',
    Legal:       'fa-scale-balanced',
    Procurement: 'fa-boxes-stacked',
    Technology:  'fa-microchip',
    Custom:      'fa-paintbrush',
    Imported:    'fa-file-import',
    default:     'fa-layer-group',
};

/* ─── Priority colours ────────────────────────────────── */
const PRIORITY_STYLE = {
    critical: 'background:rgba(248,113,113,.12);color:#f87171;border:1px solid rgba(248,113,113,.25)',
    high:     'background:rgba(251,191,36,.10);color:#fbbf24;border:1px solid rgba(251,191,36,.22)',
    medium:   'background:rgba(99,102,241,.12);color:#818cf8;border:1px solid rgba(99,102,241,.22)',
    low:      'background:rgba(100,116,139,.10);color:#64748b;border:1px solid rgba(100,116,139,.22)',
};

/* ─── State ───────────────────────────────────────────── */
let _allTemplates = [];       // full list from API
let _filtered     = [];       // currently displayed
let _activeFilter = 'all';    // active category pill
let _previewId    = null;     // id of the template open in drawer

/* ════════════════════════════════════════════════════════
   Boot
   ════════════════════════════════════════════════════════ */
document.addEventListener('DOMContentLoaded', () => {
    bindToolbar();
    bindCreateModal();
    bindImportModal();
    bindDrawer();
    loadTemplates();
});

/* ════════════════════════════════════════════════════════
   Data loading
   ════════════════════════════════════════════════════════ */
async function loadTemplates() {
    try {
        const data = await WorkflowUtils.fetchJSON(TPL_API.list, { method: 'GET' });
        _allTemplates = data.templates || [];
        applyFilter();
    } catch (err) {
        WorkflowUtils.showToast('Failed to load templates: ' + err.message, 'error');
    }
}

/* ════════════════════════════════════════════════════════
   Filtering & rendering
   ════════════════════════════════════════════════════════ */
function applyFilter() {
    const query = (document.getElementById('tpl-search').value || '').toLowerCase().trim();
    _filtered = _allTemplates.filter(t => {
        const catMatch = _activeFilter === 'all' || t.category === _activeFilter;
        const qMatch   = !query ||
            t.name.toLowerCase().includes(query) ||
            (t.description || '').toLowerCase().includes(query) ||
            (t.category || '').toLowerCase().includes(query);
        return catMatch && qMatch;
    });
    renderGrid();
}

function renderGrid() {
    const grid  = document.getElementById('templates-grid');
    const empty = document.getElementById('templates-empty');
    const count = document.getElementById('tpl-count');

    count.textContent = _filtered.length;

    if (_filtered.length === 0) {
        grid.innerHTML = '';
        empty.classList.add('visible');
        return;
    }
    empty.classList.remove('visible');
    grid.innerHTML = _filtered.map((t, i) => buildCard(t, i)).join('');

    // Bind per-card actions after render
    grid.querySelectorAll('[data-action]').forEach(btn => {
        btn.addEventListener('click', e => {
            e.stopPropagation();
            handleCardAction(btn.dataset.action, btn.dataset.id);
        });
    });
    // Clicking the card body (not a button) opens the preview
    grid.querySelectorAll('.tpl-card').forEach(card => {
        card.addEventListener('click', () => openPreview(card.dataset.id));
    });
}

function buildCard(t, idx) {
    const catClass = `cat-${(t.category || 'default').replace(/\s+/g, '-')}`;
    const icon     = CAT_ICONS[t.category] || CAT_ICONS.default;
    const depts    = (t.departments_involved || []);
    const shown    = depts.slice(0, 2);
    const more     = depts.length > 2 ? `<span class="dept-more">+${depts.length - 2} more</span>` : '';
    const customBadge = t.is_custom ? '<span class="tpl-custom-badge">Custom</span>' : '';
    const delay    = (idx % 8) * 40;

    return `
    <article class="tpl-card" data-id="${t.id}" style="animation-delay:${delay}ms" tabindex="0"
             aria-label="Template: ${escHtml(t.name)}" role="button">
        <div class="tpl-card-glow"></div>
        <div class="tpl-header">
            <div class="tpl-icon-wrap ${catClass}"><i class="fa-solid ${icon}"></i></div>
            <div class="tpl-header-text">
                <div class="tpl-name" title="${escHtml(t.name)}">${escHtml(t.name)}</div>
                <div class="tpl-badges">
                    <span class="tpl-category-badge">${escHtml(t.category || 'Custom')}</span>
                    ${customBadge}
                </div>
            </div>
        </div>
        <p class="tpl-desc" title="${escHtml(t.description || '')}">${escHtml(t.description || 'No description provided.')}</p>
        <div class="tpl-meta">
            <span class="tpl-meta-item"><i class="fa-solid fa-list-check"></i>${(t.steps || []).length} steps</span>
            <span class="tpl-meta-item"><i class="fa-solid fa-clock"></i>${t.total_estimated_days} days</span>
        </div>
        <div class="tpl-depts">
            ${shown.map(d => `<span class="dept-tag">${escHtml(d)}</span>`).join('')}
            ${more}
        </div>
        <div class="tpl-footer">
            <span class="tpl-date"><i class="fa-regular fa-calendar"></i>${t.last_updated || '—'}</span>
            <div class="tpl-actions">
                <button class="tpl-action-btn btn-preview-card" data-action="preview" data-id="${t.id}"
                        title="Preview" aria-label="Preview template"><i class="fa-solid fa-eye"></i></button>
                <button class="tpl-action-btn" data-action="customize" data-id="${t.id}"
                        title="Customize in Builder" aria-label="Customize template" style="color:var(--violet)"><i class="fa-solid fa-cubes"></i></button>
                <button class="tpl-action-btn" data-action="duplicate" data-id="${t.id}"
                        title="Duplicate" aria-label="Duplicate template"><i class="fa-solid fa-clone"></i></button>
                <button class="tpl-action-btn" data-action="export" data-id="${t.id}"
                        title="Export JSON" aria-label="Export JSON"><i class="fa-solid fa-file-export"></i></button>
                <button class="tpl-action-btn" data-action="copy" data-id="${t.id}"
                        title="Copy JSON" aria-label="Copy JSON"><i class="fa-solid fa-copy"></i></button>
                ${t.is_custom ? `<button class="tpl-action-btn danger" data-action="delete" data-id="${t.id}"
                        title="Delete" aria-label="Delete template"><i class="fa-solid fa-trash"></i></button>` : ''}
            </div>
        </div>
    </article>`;
}

/* ════════════════════════════════════════════════════════
   Card actions dispatcher
   ════════════════════════════════════════════════════════ */
function handleCardAction(action, id) {
    const tpl = findTemplate(id);
    if (!tpl) return;
    switch (action) {
        case 'preview':   openPreview(id);              break;
        case 'customize': customizeTemplate(tpl);       break;
        case 'duplicate': duplicateTemplate(id);        break;
        case 'export':    exportTemplate(tpl);          break;
        case 'copy':      copyTemplateJson(tpl);        break;
        case 'delete':    deleteTemplate(id, tpl.name); break;
    }
}

/* ════════════════════════════════════════════════════════
   Preview Drawer
   ════════════════════════════════════════════════════════ */
function bindDrawer() {
    document.getElementById('drawer-close').addEventListener('click', closeDrawer);
    document.getElementById('drawer-overlay').addEventListener('click', closeDrawer);
    document.getElementById('drawer-btn-export').addEventListener('click', () => {
        const tpl = findTemplate(_previewId);
        if (tpl) exportTemplate(tpl);
    });
    document.getElementById('drawer-btn-copy').addEventListener('click', () => {
        const tpl = findTemplate(_previewId);
        if (tpl) copyTemplateJson(tpl);
    });
    document.getElementById('drawer-btn-duplicate').addEventListener('click', () => {
        if (_previewId) duplicateTemplate(_previewId);
    });
    document.getElementById('drawer-btn-customize').addEventListener('click', () => {
        const tpl = findTemplate(_previewId);
        if (tpl) customizeTemplate(tpl);
    });
    // ESC closes drawer
    document.addEventListener('keydown', e => {
        if (e.key === 'Escape') closeDrawer();
    });
}

function openPreview(id) {
    const tpl = findTemplate(id);
    if (!tpl) return;
    _previewId = id;

    document.getElementById('drawer-title').textContent = tpl.name;
    document.getElementById('drawer-subtitle').textContent =
        `${tpl.category} · ${(tpl.steps || []).length} steps · ${tpl.total_estimated_days} days`;
    document.getElementById('ds-steps').textContent  = (tpl.steps || []).length;
    document.getElementById('ds-days').textContent   = tpl.total_estimated_days;
    document.getElementById('ds-depts').textContent  = (tpl.departments_involved || []).length;
    document.getElementById('ds-description').textContent = tpl.description || 'No description provided.';

    // Timeline
    const tl = document.getElementById('drawer-timeline');
    tl.innerHTML = (tpl.steps || []).map((s, i) => {
        const pStyle = PRIORITY_STYLE[s.priority] || PRIORITY_STYLE.low;
        return `
        <div class="dtl-step">
            <div class="dtl-dot"><i class="fa-solid fa-check"></i></div>
            <div class="dtl-card">
                <div class="dtl-name">${i + 1}. ${escHtml(s.step)}</div>
                <div class="dtl-meta">
                    <span><i class="fa-solid fa-user"></i>${escHtml(s.owner)}</span>
                    <span><i class="fa-solid fa-clock"></i>${s.estimated_days} day${s.estimated_days !== 1 ? 's' : ''}</span>
                    ${s.priority ? `<span class="dtl-priority" style="${pStyle}">${s.priority}</span>` : ''}
                </div>
            </div>
        </div>`;
    }).join('');

    // Departments
    const dc = document.getElementById('drawer-depts');
    dc.innerHTML = (tpl.departments_involved || [])
        .map(d => `<span class="dept-tag">${escHtml(d)}</span>`).join('');

    document.getElementById('preview-drawer').classList.add('open');
    document.getElementById('drawer-overlay').classList.add('open');
    document.getElementById('drawer-overlay').setAttribute('aria-hidden', 'false');
}

function closeDrawer() {
    document.getElementById('preview-drawer').classList.remove('open');
    document.getElementById('drawer-overlay').classList.remove('open');
    document.getElementById('drawer-overlay').setAttribute('aria-hidden', 'true');
    _previewId = null;
}

/* ════════════════════════════════════════════════════════
   Template Actions
   ════════════════════════════════════════════════════════ */
function customizeTemplate(tpl) {
    if (typeof WorkflowHandoff === 'undefined') {
        WorkflowUtils.showToast('Handoff bridge not loaded.', 'error');
        return;
    }
    WorkflowHandoff.save({
        source: 'template',
        action: 'customize',
        templateId: tpl.id,
        workflowName: tpl.name,
        category: tpl.category || '',
        steps: (tpl.steps || []).map(function (s) {
            return {
                step: s.step,
                owner: s.owner,
                estimated_days: s.estimated_days,
                priority: s.priority || 'medium',
            };
        }),
        departments: tpl.departments_involved || [],
        totalDays: tpl.total_estimated_days || 0,
    });
    window.location.href = '/workflow/builder/';
}

async function duplicateTemplate(id) {
    try {
        WorkflowUtils.showToast('Duplicating template…', 'info');
        const data = await WorkflowUtils.apiFetch(TPL_API.duplicate(id), { method: 'POST' });
        _allTemplates.unshift(data.template);
        applyFilter();
        WorkflowUtils.showToast(`"${data.template.name}" created.`, 'success');
        closeDrawer();
    } catch (err) {
        WorkflowUtils.showToast('Duplicate failed: ' + err.message, 'error');
    }
}

function exportTemplate(tpl) {
    const json = JSON.stringify(tpl, null, 2);
    const blob = new Blob([json], { type: 'application/json' });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href     = url;
    a.download = `${tpl.id}.json`;
    a.click();
    URL.revokeObjectURL(url);
    WorkflowUtils.showToast(`Exported "${tpl.name}".`, 'success');
}

async function copyTemplateJson(tpl) {
    const json = JSON.stringify(tpl, null, 2);
    try {
        await navigator.clipboard.writeText(json);
        WorkflowUtils.showToast('JSON copied to clipboard.', 'success');
    } catch {
        WorkflowUtils.showToast('Copy failed — clipboard unavailable.', 'warning');
    }
}

async function deleteTemplate(id, name) {
    if (!confirm(`Delete "${name}"? This cannot be undone.`)) return;
    try {
        await WorkflowUtils.fetchJSON(TPL_API.delete(id), { method: 'DELETE' });
        _allTemplates = _allTemplates.filter(t => t.id !== id);
        applyFilter();
        WorkflowUtils.showToast(`"${name}" deleted.`, 'success');
        if (_previewId === id) closeDrawer();
    } catch (err) {
        WorkflowUtils.showToast('Delete failed: ' + err.message, 'error');
    }
}

/* ════════════════════════════════════════════════════════
   Toolbar Bindings
   ════════════════════════════════════════════════════════ */
function bindToolbar() {
    document.getElementById('tpl-search').addEventListener('input', applyFilter);

    document.getElementById('filter-pills').addEventListener('click', e => {
        const pill = e.target.closest('.filter-pill');
        if (!pill) return;
        document.querySelectorAll('.filter-pill').forEach(p => p.classList.remove('active'));
        pill.classList.add('active');
        _activeFilter = pill.dataset.cat;
        applyFilter();
    });
}

/* ════════════════════════════════════════════════════════
   Create Modal
   ════════════════════════════════════════════════════════ */
function bindCreateModal() {
    document.getElementById('btn-create').addEventListener('click', () => openModal('create-modal'));
    document.getElementById('btn-create-submit').addEventListener('click', submitCreate);
    document.getElementById('btn-add-step').addEventListener('click', addStepRow);
    document.querySelectorAll('[data-modal="create-modal"]').forEach(el =>
        el.addEventListener('click', () => closeModal('create-modal')));

    // Seed with one blank step row
    addStepRow();
}

let _stepCounter = 0;

function addStepRow(stepData = {}) {
    const id = ++_stepCounter;
    const row = document.createElement('div');
    row.className = 'step-row';
    row.dataset.stepId = id;
    row.innerHTML = `
        <input type="text" class="form-control step-name" placeholder="Step name" value="${escHtml(stepData.step || '')}" autocomplete="off">
        <input type="text" class="form-control step-owner" placeholder="Owner / dept." value="${escHtml(stepData.owner || '')}" autocomplete="off">
        <input type="number" class="form-control step-days" placeholder="Days" min="0" value="${stepData.estimated_days ?? 1}">
        <button type="button" class="btn-remove-step" aria-label="Remove step"><i class="fa-solid fa-minus"></i></button>`;
    row.querySelector('.btn-remove-step').addEventListener('click', () => {
        const builder = document.getElementById('step-builder');
        if (builder.children.length > 1) row.remove();
        else WorkflowUtils.showToast('At least one step is required.', 'warning');
    });
    document.getElementById('step-builder').appendChild(row);
}

function collectSteps() {
    return Array.from(document.querySelectorAll('#step-builder .step-row')).map(row => ({
        step:           row.querySelector('.step-name').value.trim(),
        owner:          row.querySelector('.step-owner').value.trim(),
        estimated_days: parseInt(row.querySelector('.step-days').value, 10) || 1,
        priority:       'medium',
    }));
}

async function submitCreate() {
    clearFieldErrors('create-form');
    const name     = document.getElementById('f-name').value.trim();
    const category = document.getElementById('f-category').value;
    const desc     = document.getElementById('f-desc').value.trim();
    const dept     = document.getElementById('f-dept').value.trim();
    const steps    = collectSteps();

    let valid = true;
    if (!name) { markFieldError('f-name'); valid = false; }
    if (!category) { markFieldError('f-category'); valid = false; }
    if (steps.length === 0 || steps.some(s => !s.step || !s.owner)) {
        WorkflowUtils.showToast('All steps must have a name and owner.', 'warning');
        valid = false;
    }
    if (!valid) return;

    const payload = {
        name,
        description: desc,
        category,
        departments_involved: dept ? [dept] : [],
        steps,
    };

    try {
        document.getElementById('btn-create-submit').disabled = true;
        const data = await WorkflowUtils.fetchJSON(TPL_API.create, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        _allTemplates.unshift(data.template);
        applyFilter();
        closeModal('create-modal');
        resetCreateForm();
        WorkflowUtils.showToast(`Template "${data.template.name}" created!`, 'success');
    } catch (err) {
        WorkflowUtils.showToast('Create failed: ' + err.message, 'error');
    } finally {
        document.getElementById('btn-create-submit').disabled = false;
    }
}

function resetCreateForm() {
    document.getElementById('create-form').reset();
    document.getElementById('step-builder').innerHTML = '';
    _stepCounter = 0;
    addStepRow();
}

/* ════════════════════════════════════════════════════════
   Import Modal
   ════════════════════════════════════════════════════════ */
function bindImportModal() {
    document.getElementById('btn-import').addEventListener('click', () => openModal('import-modal'));
    document.getElementById('btn-import-submit').addEventListener('click', submitImport);
    document.querySelectorAll('[data-modal="import-modal"]').forEach(el =>
        el.addEventListener('click', () => closeModal('import-modal')));

    // File drop zone
    const dropZone = document.getElementById('import-drop-zone');
    const fileInput = document.getElementById('import-file-input');

    dropZone.addEventListener('click', () => fileInput.click());
    dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('drag-over'); });
    dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
    dropZone.addEventListener('drop', e => {
        e.preventDefault();
        dropZone.classList.remove('drag-over');
        const file = e.dataTransfer.files[0];
        if (file) readFile(file);
    });
    fileInput.addEventListener('change', () => {
        if (fileInput.files[0]) readFile(fileInput.files[0]);
    });
}

function readFile(file) {
    if (!file.name.endsWith('.json')) {
        WorkflowUtils.showToast('Only .json files are supported.', 'warning');
        return;
    }
    const reader = new FileReader();
    reader.onload = e => {
        document.getElementById('import-json-raw').value = e.target.result;
    };
    reader.readAsText(file);
}

async function submitImport() {
    const raw = document.getElementById('import-json-raw').value.trim();
    if (!raw) {
        WorkflowUtils.showToast('Please paste JSON or upload a file.', 'warning');
        return;
    }
    let payload;
    try {
        payload = JSON.parse(raw);
    } catch {
        WorkflowUtils.showToast('Invalid JSON — could not parse.', 'error');
        return;
    }

    try {
        document.getElementById('btn-import-submit').disabled = true;
        const data = await WorkflowUtils.fetchJSON(TPL_API.import, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        _allTemplates.unshift(data.template);
        applyFilter();
        closeModal('import-modal');
        document.getElementById('import-json-raw').value = '';
        WorkflowUtils.showToast(`Template "${data.template.name}" imported!`, 'success');
    } catch (err) {
        WorkflowUtils.showToast('Import failed: ' + err.message, 'error');
    } finally {
        document.getElementById('btn-import-submit').disabled = false;
    }
}

/* ════════════════════════════════════════════════════════
   Modal helpers
   ════════════════════════════════════════════════════════ */
function openModal(id) {
    document.getElementById(id).classList.add('open');
}
function closeModal(id) {
    document.getElementById(id).classList.remove('open');
}

/* ════════════════════════════════════════════════════════
   Form validation helpers
   ════════════════════════════════════════════════════════ */
function markFieldError(id) {
    document.getElementById(id).classList.add('wf-field-error');
}
function clearFieldErrors(formId) {
    document.getElementById(formId).querySelectorAll('.wf-field-error')
        .forEach(el => el.classList.remove('wf-field-error'));
}

/* ════════════════════════════════════════════════════════
   Utility
   ════════════════════════════════════════════════════════ */
function findTemplate(id) {
    return _allTemplates.find(t => t.id === id) || null;
}
function escHtml(str) {
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}
