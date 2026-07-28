/* ─────────────────────────────────────────────────────────
   Workflow AI Dashboard – JavaScript (Enterprise)
   ───────────────────────────────────────────────────────── */

(function () {
    'use strict';

    var U = WorkflowUtils;

    /* ══════════════════════════════════════════
       MOCK ACTIVITY DATA
       ══════════════════════════════════════════ */

    var MOCK_ACTIVITIES = [
        { type: 'recommend', text: '<strong>Enterprise Procurement Workflow</strong> recommended for HD-2026-099', time: '2 min ago' },
        { type: 'build', text: '<strong>NDA Approval Workflow</strong> generated via Dynamic Builder', time: '15 min ago' },
        { type: 'export', text: '<strong>High-Value Contract Workflow</strong> exported as JSON', time: '1 hour ago' },
        { type: 'recommend', text: '<strong>Service Agreement Workflow</strong> recommended for SVC-2026-044', time: '3 hours ago' },
        { type: 'build', text: '<strong>Consulting Contract Workflow</strong> built with 5 approval steps', time: '5 hours ago' },
        { type: 'recommend', text: '<strong>Software Licensing Workflow</strong> recommended – 94% confidence', time: 'Yesterday' },
        { type: 'export', text: '<strong>Partnership Agreement Workflow</strong> copied to clipboard', time: 'Yesterday' },
    ];


    /* ══════════════════════════════════════════
       RENDER ACTIVITY LIST
       ══════════════════════════════════════════ */

    function renderActivityList() {
        var container = document.getElementById('activity-list');
        if (!container) return;

        container.innerHTML = '';

        MOCK_ACTIVITIES.forEach(function (item, i) {
            var el = document.createElement('div');
            el.className = 'activity-item';
            el.style.animationDelay = (i * 0.05) + 's';
            el.style.animation = 'fadeInUp 0.3s ease both';

            el.innerHTML =
                '<div class="activity-dot ' + item.type + '"></div>' +
                '<div>' +
                '   <div class="activity-text">' + item.text + '</div>' +
                '   <div class="activity-time">' + item.time + '</div>' +
                '</div>';

            container.appendChild(el);
        });
    }


    /* ══════════════════════════════════════════
       STAT COUNTER ANIMATION
       ══════════════════════════════════════════ */

    function animateCounters() {
        var counters = [
            { id: 'sv-templates', target: 12, suffix: '' },
            { id: 'sv-recommended', target: 8, suffix: '' },
            { id: 'sv-dynamic', target: 24, suffix: '' },
            { id: 'sv-confidence', target: 91, suffix: '<span class="stat-unit">%</span>' },
        ];

        counters.forEach(function (counter) {
            var el = document.getElementById(counter.id);
            if (!el) return;

            var start = 0;
            var end = counter.target;
            var duration = 1200;
            var startTime = null;

            function step(timestamp) {
                if (!startTime) startTime = timestamp;
                var progress = Math.min((timestamp - startTime) / duration, 1);
                // Ease out cubic
                var eased = 1 - Math.pow(1 - progress, 3);
                var current = Math.round(start + (end - start) * eased);
                el.innerHTML = current + counter.suffix;

                if (progress < 1) {
                    requestAnimationFrame(step);
                }
            }

            requestAnimationFrame(step);
        });
    }


    /* ══════════════════════════════════════════
       BANNER DISMISS
       ══════════════════════════════════════════ */

    function setupBannerDismiss() {
        var btn = document.getElementById('banner-dismiss');
        var banner = document.getElementById('welcome-banner');
        if (!btn || !banner) return;

        // Check localStorage
        if (localStorage.getItem('wf_banner_dismissed') === '1') {
            banner.classList.add('dismissed');
            return;
        }

        btn.addEventListener('click', function () {
            banner.style.opacity = '0';
            banner.style.transform = 'translateY(-10px)';
            banner.style.transition = 'all 0.3s ease';
            setTimeout(function () {
                banner.classList.add('dismissed');
                localStorage.setItem('wf_banner_dismissed', '1');
            }, 300);
        });
    }


    /* ══════════════════════════════════════════
       HOVER EFFECTS
       ══════════════════════════════════════════ */

    function setupHoverEffects() {
        var cards = document.querySelectorAll('.stat-card');
        cards.forEach(function (card) {
            card.addEventListener('mouseenter', function () {
                var icon = card.querySelector('.stat-icon-wrap');
                if (icon) icon.style.transform = 'scale(1.1)';
            });
            card.addEventListener('mouseleave', function () {
                var icon = card.querySelector('.stat-icon-wrap');
                if (icon) icon.style.transform = 'scale(1)';
            });
        });
    }


    /* ══════════════════════════════════════════
       INIT
       ══════════════════════════════════════════ */

    renderActivityList();
    animateCounters();
    setupBannerDismiss();
    setupHoverEffects();

})();
