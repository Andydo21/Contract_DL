/* ─────────────────────────────────────────────────────────
   WorkflowUtils — Shared Utility Library
   Reusable helpers for all Workflow AI pages.
   ───────────────────────────────────────────────────────── */

var WorkflowUtils = (function () {
    'use strict';

    /* ══════════════════════════════════════════
       TOAST NOTIFICATION SYSTEM
       ══════════════════════════════════════════ */

    var _toastContainer = null;

    function _getToastContainer() {
        if (!_toastContainer) {
            _toastContainer = document.getElementById('toast-container');
            if (!_toastContainer) {
                _toastContainer = document.createElement('div');
                _toastContainer.id = 'toast-container';
                _toastContainer.className = 'wf-toast-container';
                document.body.appendChild(_toastContainer);
            }
        }
        return _toastContainer;
    }

    var TOAST_ICONS = {
        success: 'fa-circle-check',
        error: 'fa-circle-xmark',
        warning: 'fa-triangle-exclamation',
        info: 'fa-circle-info',
    };

    function showToast(message, type, duration) {
        type = type || 'info';
        duration = duration || 4000;
        var container = _getToastContainer();
        var toast = document.createElement('div');
        toast.className = 'wf-toast wf-toast-' + type;
        toast.setAttribute('role', 'alert');
        toast.innerHTML =
            '<i class="fa-solid ' + (TOAST_ICONS[type] || TOAST_ICONS.info) + ' wf-toast-icon"></i>' +
            '<span class="wf-toast-msg">' + _escapeHtml(message) + '</span>' +
            '<button class="wf-toast-close" aria-label="Dismiss">&times;</button>';
        toast.querySelector('.wf-toast-close').addEventListener('click', function () {
            _dismissToast(toast);
        });
        container.appendChild(toast);
        requestAnimationFrame(function () { toast.classList.add('wf-toast-visible'); });
        setTimeout(function () { _dismissToast(toast); }, duration);
    }

    function _dismissToast(toast) {
        if (!toast || toast._dismissed) return;
        toast._dismissed = true;
        toast.classList.remove('wf-toast-visible');
        toast.classList.add('wf-toast-exit');
        setTimeout(function () { if (toast.parentNode) toast.parentNode.removeChild(toast); }, 350);
    }


    /* ══════════════════════════════════════════
       LOADING STATE MANAGEMENT
       ══════════════════════════════════════════ */

    function showLoading(containerId, text) {
        var el = document.getElementById(containerId);
        if (!el) return;
        el.classList.remove('wf-hidden');
        var textEl = el.querySelector('.wf-loading-text');
        if (textEl && text) textEl.textContent = text;
    }

    function hideLoading(containerId) {
        var el = document.getElementById(containerId);
        if (el) el.classList.add('wf-hidden');
    }

    function showElement(el) {
        if (typeof el === 'string') el = document.getElementById(el);
        if (el) el.classList.remove('wf-hidden');
    }

    function hideElement(el) {
        if (typeof el === 'string') el = document.getElementById(el);
        if (el) el.classList.add('wf-hidden');
    }


    /* ══════════════════════════════════════════
       FORM VALIDATION
       ══════════════════════════════════════════ */

    /**
     * Validate that all listed field IDs have non-empty values.
     * Returns { valid: bool, missing: [ids] }
     */
    function validateRequired(fieldIds) {
        var missing = [];
        fieldIds.forEach(function (id) {
            var el = document.getElementById(id);
            if (!el) { missing.push(id); return; }
            var val = (el.value || '').trim();
            if (!val) {
                missing.push(id);
                el.classList.add('wf-field-error');
            } else {
                el.classList.remove('wf-field-error');
            }
        });
        return { valid: missing.length === 0, missing: missing };
    }

    /**
     * Attach live validation: remove error class on input.
     */
    function attachLiveValidation(fieldIds) {
        fieldIds.forEach(function (id) {
            var el = document.getElementById(id);
            if (!el) return;
            el.addEventListener('input', function () {
                if ((el.value || '').trim()) el.classList.remove('wf-field-error');
            });
        });
    }


    /* ══════════════════════════════════════════
       FORMATTING
       ══════════════════════════════════════════ */

    function formatCurrency(value) {
        var num = parseFloat(value);
        if (isNaN(num)) return '$0';
        return '$' + num.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 });
    }

    function formatNumber(value) {
        var num = parseFloat(value);
        if (isNaN(num)) return '0';
        return num.toLocaleString('en-US');
    }


    /* ══════════════════════════════════════════
       CLIPBOARD & DOWNLOAD
       ══════════════════════════════════════════ */

    async function copyToClipboard(text) {
        try {
            await navigator.clipboard.writeText(text);
            showToast('Copied to clipboard', 'success', 2500);
            return true;
        } catch (e) {
            showToast('Failed to copy', 'error');
            return false;
        }
    }

    function downloadJSON(data, filename) {
        filename = filename || 'workflow.json';
        var json = JSON.stringify(data, null, 2);
        var blob = new Blob([json], { type: 'application/json' });
        var url = URL.createObjectURL(blob);
        var a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        showToast('JSON exported: ' + filename, 'success', 2500);
    }


    /* ══════════════════════════════════════════
       STEP METADATA ENRICHMENT
       ══════════════════════════════════════════ */

    var STEP_META = {
        'legal review': { icon: 'fa-scale-balanced', owner: 'Legal Department', days: 2, desc: 'Review contract terms, clauses, and legal compliance', priority: 'high' },
        'compliance check': { icon: 'fa-clipboard-check', owner: 'Compliance Team', days: 2, desc: 'Verify regulatory compliance and policy adherence', priority: 'high' },
        'finance review': { icon: 'fa-coins', owner: 'Finance Department', days: 1, desc: 'Validate budget allocation and payment terms', priority: 'medium' },
        'manager approval': { icon: 'fa-user-check', owner: 'Department Manager', days: 1, desc: 'Managerial sign-off on department-level obligations', priority: 'medium' },
        'director approval': { icon: 'fa-user-tie', owner: 'Director / VP', days: 2, desc: 'Executive review for high-impact contracts', priority: 'high' },
        'ceo approval': { icon: 'fa-crown', owner: 'CEO', days: 1, desc: 'Final executive authorization for enterprise agreements', priority: 'critical' },
        'contract signing': { icon: 'fa-signature', owner: 'Authorized Signers', days: 1, desc: 'Digital or physical contract execution and attestation', priority: 'high' },
        'sign & archive': { icon: 'fa-signature', owner: 'Authorized Signers', days: 1, desc: 'Sign the contract and archive the final version', priority: 'high' },
        'archive': { icon: 'fa-box-archive', owner: 'System', days: 0, desc: 'Secure storage and indexing in the contract repository', priority: 'low' },
    };

    function getStepMeta(stepName) {
        var key = (stepName || '').toLowerCase().trim();
        var meta = STEP_META[key];
        if (meta) return Object.assign({ name: stepName }, meta);
        // Fallback: derive from name
        return {
            name: stepName,
            icon: _guessStepIcon(key),
            owner: 'Assigned Team',
            days: 1,
            desc: 'Workflow step: ' + stepName,
            priority: 'medium',
        };
    }

    function _guessStepIcon(nameLower) {
        if (nameLower.indexOf('legal') !== -1) return 'fa-scale-balanced';
        if (nameLower.indexOf('finance') !== -1) return 'fa-coins';
        if (nameLower.indexOf('manager') !== -1) return 'fa-user-check';
        if (nameLower.indexOf('director') !== -1) return 'fa-user-tie';
        if (nameLower.indexOf('ceo') !== -1) return 'fa-crown';
        if (nameLower.indexOf('sign') !== -1) return 'fa-signature';
        if (nameLower.indexOf('archive') !== -1) return 'fa-box-archive';
        if (nameLower.indexOf('compliance') !== -1) return 'fa-clipboard-check';
        if (nameLower.indexOf('review') !== -1) return 'fa-magnifying-glass';
        return 'fa-circle-dot';
    }

    function getPriorityColor(priority) {
        var map = {
            critical: '#f87171',
            high: '#fb923c',
            medium: '#fbbf24',
            low: '#34d399',
        };
        return map[(priority || '').toLowerCase()] || map.medium;
    }

    function getStatusConfig(status) {
        var map = {
            completed: { color: '#34d399', bg: 'rgba(52,211,153,0.10)', icon: 'fa-circle-check', label: 'Completed' },
            current: { color: '#818cf8', bg: 'rgba(129,140,248,0.10)', icon: 'fa-spinner fa-spin', label: 'In Progress' },
            pending: { color: '#64748b', bg: 'rgba(100,116,139,0.08)', icon: 'fa-clock', label: 'Pending' },
        };
        return map[(status || '').toLowerCase()] || map.pending;
    }


    /* ══════════════════════════════════════════
       UTILITIES
       ══════════════════════════════════════════ */

    function debounce(fn, delay) {
        var timer;
        return function () {
            var args = arguments;
            var ctx = this;
            clearTimeout(timer);
            timer = setTimeout(function () { fn.apply(ctx, args); }, delay);
        };
    }

    function _escapeHtml(str) {
        var div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    /**
     * Fetch JSON with error handling.
     */
    async function fetchJSON(url, options) {
        var response = await fetch(url, options);
        var data = await response.json();
        if (!response.ok || data.error) {
            throw new Error(data.error || 'Request failed (' + response.status + ')');
        }
        return data;
    }


    /* ══════════════════════════════════════════
       PUBLIC API
       ══════════════════════════════════════════ */

    return {
        showToast: showToast,
        showLoading: showLoading,
        hideLoading: hideLoading,
        showElement: showElement,
        hideElement: hideElement,
        validateRequired: validateRequired,
        attachLiveValidation: attachLiveValidation,
        formatCurrency: formatCurrency,
        formatNumber: formatNumber,
        copyToClipboard: copyToClipboard,
        downloadJSON: downloadJSON,
        getStepMeta: getStepMeta,
        getPriorityColor: getPriorityColor,
        getStatusConfig: getStatusConfig,
        debounce: debounce,
        fetchJSON: fetchJSON,
    };
})();
