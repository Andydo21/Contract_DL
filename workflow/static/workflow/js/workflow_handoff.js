/* ══════════════════════════════════════════════════════════════
   workflow_handoff.js  —  Cross-page state bridge

   Reads and writes a single sessionStorage key ("wf_handoff")
   to pass template / recommendation context between pages without
   any backend round-trips.

   Schema of the handoff object
   ─────────────────────────────
   {
     source: 'recommendation' | 'template',   // where it came from
     action: 'customize' | 'view',            // what the user clicked
     templateId: 'tpl-nda' | null,            // template id if known
     workflowName: 'Standard NDA...',
     category: 'Legal',
     steps: [ { step, owner, estimated_days, priority }, ... ],
     departments: [ 'Legal Department', ... ],
     totalDays: 7,
   }

   Public API (attached to window.WorkflowHandoff)
   ─────────────────────────────────────────────────
     WorkflowHandoff.save(obj)      → void
     WorkflowHandoff.load()         → obj | null
     WorkflowHandoff.clear()        → void
     WorkflowHandoff.hasPending()   → bool
   ══════════════════════════════════════════════════════════════ */

var WorkflowHandoff = (function () {
    'use strict';

    var KEY = 'wf_handoff';

    function save(obj) {
        try {
            sessionStorage.setItem(KEY, JSON.stringify(obj));
        } catch (e) {
            console.warn('[WorkflowHandoff] Could not write to sessionStorage:', e);
        }
    }

    function load() {
        try {
            var raw = sessionStorage.getItem(KEY);
            return raw ? JSON.parse(raw) : null;
        } catch (e) {
            return null;
        }
    }

    function clear() {
        try { sessionStorage.removeItem(KEY); } catch (e) { /* noop */ }
    }

    function hasPending() {
        return load() !== null;
    }

    return { save: save, load: load, clear: clear, hasPending: hasPending };
})();
