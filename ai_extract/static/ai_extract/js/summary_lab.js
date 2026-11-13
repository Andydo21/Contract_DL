(() => {
    const $ = id => document.getElementById(id);
    const csrf = document.querySelector('[name=csrfmiddlewaretoken]').value;
    const KINDS = {pdf: 'PDF', docx: 'DOCX', txt: 'TXT'};
    const AUTO = {queued: 'đang chờ tự tóm tắt', running: 'đang tự tóm tắt', done: 'đã tự tóm tắt', failed: 'tự tóm tắt lỗi'};
    const FACT_LABELS = {contract_numbers: 'Số hợp đồng', parties: 'Các bên', tax_codes: 'Mã số thuế', money: 'Số tiền',
                         dates: 'Ngày', durations: 'Thời hạn', percents: 'Tỷ lệ'};
    const LEVELS = {high: 'cao', medium: 'trung bình', low: 'thấp'};
    const STATUS = {found: '✓ có', partial: '◐ thiếu một phần', missing: '✗ không thấy'};
    const FIELD_NAMES = {contract_type: 'Loại hợp đồng', purpose: 'Mục đích', value: 'Giá trị', term: 'Thời hạn',
                         effective_date: 'Hiệu lực', job: 'Công việc', salary: 'Lương', working_time: 'Thời giờ làm việc',
                         insurance: 'Bảo hiểm', payment: 'Thanh toán', benefits: 'Quyền lợi', obligations: 'Nghĩa vụ',
                         penalties: 'Phạt', termination: 'Chấm dứt', risks: 'Lưu ý', parties: 'Các bên'};
    let current = null;
    let busy = false;
    let rerun = null;  // last summary action, replayed from cache when display options change

    const opts = () => ({perspective: $('opt-perspective').value, length: $('opt-length').value,
                         explain_terms: $('opt-explain').checked});

    function el(tag, attrs = {}, ...children) {
        const node = document.createElement(tag);
        Object.entries(attrs).forEach(([k, v]) => k === 'class' ? node.className = v : node.setAttribute(k, v));
        children.flat().forEach(child => node.append(child instanceof Node ? child : document.createTextNode(String(child))));
        return node;
    }

    async function api(url, body) {
        const form = body instanceof FormData;
        const response = await fetch(url, body === undefined ? {} : {
            method: 'POST', headers: form ? {'X-CSRFToken': csrf} : {'Content-Type': 'application/json', 'X-CSRFToken': csrf},
            body: form ? body : JSON.stringify(body)});
        const data = await response.json().catch(() => ({error: `HTTP ${response.status}`}));
        if (!response.ok || data.success === false) throw new Error(data.error || data.detail || `HTTP ${response.status}`);
        return data;
    }

    // Errors stay on the page next to the controls instead of interrupting with a browser alert.
    function showError(message) {
        $('lab-error-text').textContent = message;
        $('lab-error').hidden = !message;
        if (message) $('lab-error').scrollIntoView({behavior: 'smooth', block: 'nearest'});
    }

    // A control's state decided while a task runs takes effect when the task ends and the controls unlock.
    function setDisabled(node, value) {
        if (busy) node.dataset.wasDisabled = value;
        else node.disabled = value;
    }

    async function withBusy(label, task) {
        if (busy) return;
        busy = true;
        showError('');
        // Options and inputs lock with the buttons: a value changed mid-run would not be the one the result used.
        const controls = [...document.querySelectorAll('button, select, input, textarea')];
        const focused = document.activeElement;
        controls.forEach(c => c.dataset.wasDisabled = c.disabled);
        controls.forEach(c => c.disabled = true);
        const started = performance.now();
        const tick = () => $('busy-text').textContent = `${label} · ${((performance.now() - started) / 1000).toFixed(0)}s`;
        tick();
        $('busy').hidden = false;
        const timer = setInterval(tick, 1000);
        try {
            return await task();
        } catch (error) {
            showError(`${label} thất bại: ${error.message}`);
        } finally {
            clearInterval(timer);
            $('busy').hidden = true;
            controls.forEach(c => c.disabled = c.dataset.wasDisabled === 'true');
            busy = false;
            if (focused && controls.includes(focused) && !focused.disabled) focused.focus({preventScroll: true});
        }
    }

    function pill(node, text, tone) {
        node.textContent = text;
        node.className = `pill ${tone || ''}`;
    }

    async function checkHealth() {
        const box = $('health');
        try {
            const data = await api(box.dataset.endpoint);
            box.classList.toggle('ok', !!data.llm_connected);
            box.classList.toggle('bad', !data.llm_connected);
            box.querySelector('small').textContent = data.llm_connected
                ? `${data.model} · đã kết nối` : (data.error || `Model chưa kết nối (${data.llm_url || 'chưa cấu hình URL'})`);
        } catch (error) {
            box.classList.add('bad');
            box.querySelector('small').textContent = error.message;
        }
    }

    function renderPrepare(target, prepared, error) {
        target.replaceChildren();
        if (error) {
            target.append(el('p', {class: 'error-text'}, `Không lấy được kế hoạch chunk: ${error}`));
            return;
        }
        if (!prepared) return;
        const rows = prepared.sections.map(s => el('tr', {class: s.included ? '' : 'skipped'},
            el('td', {}, s.id), el('td', {}, s.label), el('td', {}, s.chars.toLocaleString('vi-VN')),
            el('td', {}, s.included ? `chunk ${prepared.chunks.findIndex(c => c.includes(s.id)) + 1}` : 'bị lược'),
            el('td', {class: 'preview'}, s.preview)));
        const facts = Object.entries(prepared.facts).map(([key, values]) => el('div', {},
            el('h4', {}, FACT_LABELS[key] || key),
            values.length ? values.map(v => el('span', {class: 'chip'}, v)) : el('span', {class: 'hint'}, 'Không thấy')));
        target.append(
            el('details', {class: 'panel', open: ''}, el('summary', {}, `Điều khoản tách được (${prepared.sections.length}) → ${prepared.chunks.length} lượt gọi model song song`),
                el('div', {class: 'panel-body'}, el('table', {class: 'sections'},
                    el('thead', {}, el('tr', {}, ['Mã', 'Điều khoản', 'Ký tự', 'Gửi trong', 'Mở đầu'].map(h => el('th', {}, h)))),
                    el('tbody', {}, rows)))),
            el('details', {class: 'panel'}, el('summary', {}, 'Giá trị rút bằng regex (gửi kèm làm mốc đối chiếu)'),
                el('div', {class: 'panel-body facts'}, facts)));
    }

    function describeSource(source) {
        if (!source) return '';
        const parts = [KINDS[source.kind] || source.kind, `${source.chars.toLocaleString('vi-VN')} ký tự`];
        if (source.pages) parts.push(`${source.pages} trang`);
        if (source.ocr_pages && source.ocr_pages.length) parts.push(`OCR ${source.ocr_pages.length} trang scan`);
        return parts.join(' · ') + (source.warnings && source.warnings.length ? ` — ${source.warnings.join(' ')}` : '');
    }

    function renderResult(data) {
        $('result').hidden = false;
        $('result-metrics').replaceChildren(
            el('span', {class: 'pill'}, `${(data.elapsed_ms / 1000).toFixed(1)}s`),
            el('span', {class: `pill ${data.cached ? 'ok' : ''}`}, data.cached ? 'từ cache' : 'gọi model'),
            el('span', {class: 'pill'}, `${data.chunks} chunk`),
            el('span', {class: 'pill'}, data.model_id),
            el('span', {class: `pill ${data.unverified.length ? 'warn' : 'ok'}`}, `${data.unverified.length} giá trị bị loại`));
        $('result-summary').textContent = data.summary;
        $('result-json').textContent = JSON.stringify(data.structured, null, 2);
        renderChecklist(data.checklist);
        renderConfidence(data.structured);
        $('result-unverified').replaceChildren(...(data.unverified.length ? [el('div', {class: 'unverified'},
            el('h3', {}, 'Model đưa ra nhưng không qua kiểm chứng — đã loại khỏi bản tóm tắt'),
            el('ul', {}, data.unverified.map(u => el('li', {}, `${u.field}: “${u.text}” — ${u.reason || 'số không thấy trong nguồn: ' + u.numbers.join(', ')}`))))] : []));
        $('result').scrollIntoView({behavior: 'smooth', block: 'start'});
    }

    function renderChecklist(checklist) {
        $('result-checklist').replaceChildren(...(checklist ? [el('div', {class: 'checklist'},
            el('h3', {}, `Nội dung bắt buộc — ${checklist.basis}`),
            el('ul', {}, checklist.items.map(item => el('li', {class: `st-${item.status}`},
                `${item.point}) ${item.label}: ${STATUS[item.status]}`
                + (item.sections.length ? ` (${item.sections.join(', ')})` : '')
                + (item.missing.length && item.status === 'partial' ? ` — thiếu ${item.missing.join(', ')}` : '')))))] : []));
    }

    function renderConfidence(structured) {
        const rows = [];
        Object.entries(structured.confidence || {}).forEach(([field, c]) => rows.push([FIELD_NAMES[field] || field, structured[field], c]));
        (structured.parties || []).forEach(p => p.confidence && rows.push(['Các bên', p.name, p.confidence]));
        Object.keys(FIELD_NAMES).forEach(field => Array.isArray(structured[field]) && field !== 'parties' &&
            structured[field].forEach(item => item.confidence && rows.push([FIELD_NAMES[field], item.text, item.confidence])));
        const order = {low: 0, medium: 1, high: 2};
        rows.sort((a, b) => order[a[2].level] - order[b[2].level]);
        $('result-confidence').replaceChildren(el('table', {class: 'conf'},
            el('thead', {}, el('tr', {}, ['Mức', 'Trường', 'Giá trị', 'Xác suất token', 'Khớp nguồn', 'Lý do'].map(h => el('th', {}, h)))),
            el('tbody', {}, rows.map(([name, value, c]) => el('tr', {},
                el('td', {class: `lv-${c.level}`}, LEVELS[c.level]), el('td', {}, name), el('td', {}, String(value).slice(0, 120)),
                el('td', {}, c.prob == null ? '—' : c.prob.toFixed(2)), el('td', {}, c.support == null ? '—' : `${Math.round(c.support * 100)}%`),
                el('td', {}, c.reasons.join('; ')))))));
    }

    function renderCompare(data) {
        $('result').hidden = true;
        $('compare-result').hidden = false;
        $('compare-metrics').replaceChildren(
            el('span', {class: 'pill'}, `${(data.elapsed_ms / 1000).toFixed(1)}s`),
            el('span', {class: 'pill'}, `${data.changes.length} thay đổi`),
            el('span', {class: `pill ${data.old.cached && data.new.cached ? 'ok' : ''}`},
               data.old.cached && data.new.cached ? 'cả hai từ cache' : 'có gọi model'));
        $('compare-changes').textContent = data.summary;
        $('compare-old-summary').textContent = data.old.summary;
        $('compare-new-summary').textContent = data.new.summary;
        $('compare-result').scrollIntoView({behavior: 'smooth', block: 'start'});
    }

    async function loadContract(id) {
        const data = await api(`/api/ai/summary-lab/contracts/${id}/`);
        current = data;
        $('steps').hidden = false;
        const source = data.source;
        pill($('file-kind'), data.has_text ? 'TEXT TRONG DB' : source ? KINDS[source.kind] || source.kind : data.file ? 'LỖI ĐỌC' : 'CHƯA CÓ NGUỒN',
             source ? 'ok' : 'bad');
        $('file-pages').textContent = source && source.pages ? source.pages : '—';
        $('file-ocr').textContent = source ? (source.ocr_pages.length || 'không cần') : '—';
        $('file-uploaded').textContent = data.file ? new Date(data.file.uploaded_at).toLocaleString('vi-VN') : '—';
        $('file-name').textContent = data.has_text ? 'Dùng text hợp đồng đã lưu trong database.' : data.file ? data.file.name : 'Phiên bản này chưa có text hay file.';
        const problems = [data.read_error, ...(source ? source.warnings : [])].filter(Boolean);
        $('file-error').hidden = !problems.length;
        $('file-error').textContent = problems.join(' ');

        pill($('source-state'), source ? `${source.chars.toLocaleString('vi-VN')} ký tự` : 'KHÔNG CÓ', source ? 'ok' : 'bad');
        $('source-chars').textContent = source ? source.chars.toLocaleString('vi-VN') : 0;
        $('source-sections').textContent = data.prepare ? data.prepare.sections.length : '—';
        $('source-chunks').textContent = data.prepare ? data.prepare.chunks.length : '—';
        const skipped = data.prepare ? data.prepare.sections.filter(s => !s.included).length : 0;
        $('source-hint').textContent = !source ? 'Không có text để tóm tắt.'
            : skipped ? `${skipped} điều khoản ít quan trọng bị lược vì vượt giới hạn ${data.prepare.max_chunks} chunk.`
            : `Toàn bộ văn bản được gửi${data.prepare.cached ? ' · đã có kết quả trong cache' : ''}.`;
        renderPrepare($('contract-prepare'), data.prepare);
        $('source-panel').hidden = !source;
        $('source-preview').textContent = source ? source.preview : '';

        setDisabled($('run-summary'), !source);
        const auto = data.auto ? AUTO[data.auto.state] || data.auto.state : '';
        pill($('summary-state'), data.saved_summary ? 'ĐÃ LƯU' : auto ? auto.toUpperCase() : 'CHƯA CÓ',
             data.saved_summary ? 'ok' : data.auto && data.auto.state === 'failed' ? 'bad' : '');
        $('saved-hint').textContent = (data.saved_summary
            ? `Bản đang lưu: ${data.saved_summary.model_id || 'không rõ model'} · ${new Date(data.saved_summary.updated_at).toLocaleString('vi-VN')}` : '')
            + (data.auto && data.auto.error ? ` Lỗi tự tóm tắt: ${data.auto.error}` : '');
        return data;
    }

    async function runSummary() {
        const data = await api(`/api/ai/contracts/${current.contract.id}/summarize/`, {force: $('contract-force').checked, ...opts()});
        $('contract-force').checked = false;
        rerun = runSummary;
        $('compare-result').hidden = true;
        renderResult(data);
        if (data.saved) {
            pill($('summary-state'), 'ĐÃ LƯU', 'ok');
            $('saved-hint').textContent = `Vừa lưu: ${data.model_id}`;
        } else {
            $('saved-hint').textContent = 'Đang xem góc nhìn khác; bản lưu vẫn là bản chung, chi tiết.';
        }
    }

    const tabs = [...document.querySelectorAll('.tab')];
    function selectTab(tab) {
        tabs.forEach(t => {
            t.classList.toggle('active', t === tab);
            t.setAttribute('aria-selected', String(t === tab));
            t.tabIndex = t === tab ? 0 : -1;  // one stop in the tab order; arrow keys move between tabs
            $(`tab-${t.dataset.tab}`).hidden = t !== tab;
        });
    }
    tabs.forEach((tab, index) => {
        tab.addEventListener('click', () => selectTab(tab));
        tab.addEventListener('keydown', event => {
            const target = {ArrowRight: tabs[(index + 1) % tabs.length], ArrowLeft: tabs[(index - 1 + tabs.length) % tabs.length],
                            Home: tabs[0], End: tabs[tabs.length - 1]}[event.key];
            if (!target) return;
            event.preventDefault();
            selectTab(target);
            target.focus();
        });
    });
    $('lab-error-close').addEventListener('click', () => showError(''));

    ['opt-perspective', 'opt-length', 'opt-explain'].forEach(id => $(id).addEventListener('change', () => {
        if (rerun) withBusy('Đang dựng lại bản tóm tắt', rerun);
    }));

    $('contract-select').addEventListener('change', event => {
        $('result').hidden = true;
        $('compare-result').hidden = true;
        rerun = null;  // the shown result belonged to the previous contract
        if (event.target.value) withBusy('Đang tải hợp đồng', () => loadContract(event.target.value));
        else $('steps').hidden = true;
    });
    $('run-summary').addEventListener('click', () => withBusy('Đang tóm tắt', runSummary));

    async function runFileSummary() {
        const file = $('lab-file').files[0];
        if (!file) throw new Error('Chọn một file PDF, DOCX hoặc TXT.');
        const form = new FormData();
        form.append('file', file);
        Object.entries({...opts(), force: $('file-force').checked}).forEach(([k, v]) => form.append(k, String(v)));
        const data = await api('/api/ai/summary-lab/file/', form);
        $('file-force').checked = false;
        rerun = runFileSummary;
        $('compare-result').hidden = true;
        $('file-source').textContent = `Đã đọc: ${describeSource(data.source)}`;
        renderResult(data);
    }
    $('file-summary').addEventListener('click', () => withBusy('Đang đọc file và tóm tắt', runFileSummary));

    $('text-prepare').addEventListener('click', () => withBusy('Đang phân tích text', async () =>
        renderPrepare($('text-prepare-out'), await api('/api/ai/summary-lab/text/', {text: $('lab-text').value, prepare_only: true}))));
    async function runTextSummary() {
        const data = await api('/api/ai/summary-lab/text/', {text: $('lab-text').value, force: $('text-force').checked, ...opts()});
        $('text-force').checked = false;
        rerun = runTextSummary;
        $('compare-result').hidden = true;
        renderResult(data);
    }
    $('text-summary').addEventListener('click', () => withBusy('Đang tóm tắt', runTextSummary));

    document.querySelectorAll('[name=compare-mode]').forEach(radio => radio.addEventListener('change', () => {
        const texts = document.querySelector('[name=compare-mode]:checked').value === 'texts';
        $('compare-texts').hidden = !texts;
        $('compare-versions').hidden = texts;
    }));
    $('compare-contract').addEventListener('change', event => withBusy('Đang tải danh sách phiên bản', async () => {
        const versions = event.target.value ? (await api(`/api/ai/summary-lab/contracts/${event.target.value}/`)).versions : [];
        ['compare-old', 'compare-new'].forEach((id, index) => {
            $(id).replaceChildren(...versions.map(v => el('option', {value: v.id}, `v${v.number}`)));
            setDisabled($(id), versions.length < 2);
            if (versions.length) $(id).selectedIndex = index ? versions.length - 1 : Math.max(0, versions.length - 2);
        });
        if (event.target.value && versions.length < 2) showError('Hợp đồng này chỉ có một phiên bản. Hãy dùng chế độ dán hai văn bản.');
    }));
    async function runCompare() {
        const texts = document.querySelector('[name=compare-mode]:checked').value === 'texts';
        const body = texts ? {old_text: $('compare-old-text').value, new_text: $('compare-new-text').value}
            : {contract_id: $('compare-contract').value, old_version_id: $('compare-old').value, new_version_id: $('compare-new').value};
        if (!texts && !body.contract_id) throw new Error('Chọn hợp đồng và hai phiên bản.');
        if (!texts && body.old_version_id === body.new_version_id) throw new Error('Hãy chọn hai phiên bản khác nhau.');
        const data = await api('/api/ai/summary-lab/compare/', {...body, force: $('compare-force').checked, ...opts()});
        $('compare-force').checked = false;
        rerun = runCompare;
        renderCompare(data);
    }
    $('run-compare').addEventListener('click', () => withBusy('Đang so sánh (tóm tắt hai bản)', runCompare));

    // Opened from a contract's summary panel: start on that contract.
    const preset = new URLSearchParams(window.location.search).get('contract');
    if (preset && [...$('contract-select').options].some(option => option.value === preset)) {
        $('contract-select').value = preset;
        withBusy('Đang tải hợp đồng', () => loadContract(preset));
    }

    checkHealth();
})();
