(() => {
    const $ = id => document.getElementById(id);
    const csrf = document.querySelector('[name=csrfmiddlewaretoken]').value;
    const ORIGINS = {ocr_blocks: 'Khối OCR', ocr_pages: 'Text trang OCR', raw_text: 'Raw text (không OCR)', none: 'Không có text'};
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
        const response = await fetch(url, body === undefined ? {} : {
            method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf}, body: JSON.stringify(body)});
        const data = await response.json().catch(() => ({error: `HTTP ${response.status}`}));
        if (!response.ok || data.success === false) throw new Error(data.error || data.detail || `HTTP ${response.status}`);
        return data;
    }

    async function withBusy(label, task) {
        if (busy) return;
        busy = true;
        document.querySelectorAll('button').forEach(b => b.dataset.wasDisabled = b.disabled);
        document.querySelectorAll('button').forEach(b => b.disabled = true);
        const started = performance.now();
        const tick = () => $('busy-text').textContent = `${label} · ${((performance.now() - started) / 1000).toFixed(0)}s`;
        tick();
        $('busy').hidden = false;
        const timer = setInterval(tick, 1000);
        try {
            return await task();
        } catch (error) {
            alert(`${label} thất bại:\n${error.message}`);
        } finally {
            clearInterval(timer);
            $('busy').hidden = true;
            document.querySelectorAll('button').forEach(b => b.disabled = b.dataset.wasDisabled === 'true');
            $('run-flow').disabled = !$('contract-select').value;
            busy = false;
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
        const run = data.run;
        pill($('ocr-status'), run ? run.status : 'CHƯA OCR', run ? {COMPLETED: 'ok', FAILED: 'bad'}[run.status] || 'warn' : 'warn');
        $('ocr-pages').textContent = run ? run.total_pages : 0;
        $('ocr-blocks').textContent = run ? run.total_blocks : 0;
        $('ocr-done').textContent = run && run.completed_at ? new Date(run.completed_at).toLocaleString('vi-VN') : '—';
        $('ocr-error').hidden = !(run && run.error);
        $('ocr-error').textContent = run && run.error ? run.error : '';
        $('open-pipeline').href = `/ai-extract/contracts/${data.contract.id}/`;

        const source = data.source;
        pill($('source-origin'), ORIGINS[source.origin] || source.origin,
             {ocr_blocks: 'ok', ocr_pages: 'ok', raw_text: 'warn', none: 'bad'}[source.origin]);
        $('source-chars').textContent = source.chars.toLocaleString('vi-VN');
        $('source-sections').textContent = data.prepare ? data.prepare.sections.length : '—';
        $('source-chunks').textContent = data.prepare ? data.prepare.chunks.length : '—';
        const skipped = data.prepare ? data.prepare.sections.filter(s => !s.included).length : 0;
        $('source-hint').textContent = source.origin === 'none' ? 'Chưa có text. Chạy trích xuất OCR ở bước 1.'
            : skipped ? `${skipped} điều khoản ít quan trọng bị lược vì vượt giới hạn ${data.prepare.max_chunks} chunk.`
            : data.prepare ? `Toàn bộ văn bản được gửi${data.prepare.cached ? ' · đã có kết quả trong cache' : ''}.` : '';
        renderPrepare($('contract-prepare'), data.prepare, data.prepare_error);
        $('source-panel').hidden = !source.chars;
        $('source-preview').textContent = source.preview;

        $('run-summary').disabled = !source.chars;
        pill($('summary-state'), data.saved_summary ? 'ĐÃ LƯU' : 'CHƯA CÓ', data.saved_summary ? 'ok' : '');
        $('saved-hint').textContent = data.saved_summary
            ? `Bản đang lưu: ${data.saved_summary.model_id || 'không rõ model'} · ${new Date(data.saved_summary.updated_at).toLocaleString('vi-VN')}` : '';
        return data;
    }

    async function runOcr() {
        const data = await api(`/api/ai/contracts/${current.contract.id}/layout-extract/`, {});
        if (data.partial) alert(`Trích xuất xong nhưng chưa trọn vẹn. Trang lỗi: ${data.failed_pages.join(', ') || 'không có'}`);
        return loadContract(current.contract.id);
    }

    async function runSummary() {
        const data = await api(`/api/ai/contracts/${current.contract.id}/summarize/`, {force: $('contract-force').checked, ...opts()});
        $('contract-force').checked = false;
        rerun = runSummary;
        $('compare-result').hidden = true;
        renderResult(data);
        pill($('summary-state'), 'ĐÃ LƯU', 'ok');
        $('saved-hint').textContent = `Vừa lưu: ${data.model_id}`;
    }

    document.querySelectorAll('.tab').forEach(tab => tab.addEventListener('click', () => {
        document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t === tab));
        $('tab-contract').hidden = tab.dataset.tab !== 'contract';
        $('tab-text').hidden = tab.dataset.tab !== 'text';
        $('tab-compare').hidden = tab.dataset.tab !== 'compare';
    }));

    ['opt-perspective', 'opt-length', 'opt-explain'].forEach(id => $(id).addEventListener('change', () => {
        if (rerun) withBusy('Đang dựng lại bản tóm tắt', rerun);
    }));

    $('contract-select').addEventListener('change', event => {
        $('run-flow').disabled = !event.target.value;
        $('result').hidden = true;
        if (event.target.value) withBusy('Đang tải hợp đồng', () => loadContract(event.target.value));
        else $('steps').hidden = true;
    });
    $('run-ocr').addEventListener('click', () => withBusy('Đang trích xuất OCR (có thể vài phút)', runOcr));
    $('run-summary').addEventListener('click', () => withBusy('Đang tóm tắt', runSummary));
    $('run-flow').addEventListener('click', () => withBusy('Đang chạy cả luồng', async () => {
        await runOcr();
        if (!current.source.chars) throw new Error('Trích xuất xong nhưng không có text để tóm tắt.');
        await runSummary();
    }));

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
            $(id).disabled = versions.length < 2;
            if (versions.length) $(id).selectedIndex = index ? versions.length - 1 : Math.max(0, versions.length - 2);
        });
        if (event.target.value && versions.length < 2) alert('Hợp đồng này chỉ có một phiên bản. Hãy dùng chế độ dán hai văn bản.');
    }));
    async function runCompare() {
        const texts = document.querySelector('[name=compare-mode]:checked').value === 'texts';
        const body = texts ? {old_text: $('compare-old-text').value, new_text: $('compare-new-text').value}
            : {contract_id: $('compare-contract').value, old_version_id: $('compare-old').value, new_version_id: $('compare-new').value};
        if (!texts && !body.contract_id) throw new Error('Chọn hợp đồng và hai phiên bản.');
        const data = await api('/api/ai/summary-lab/compare/', {...body, force: $('compare-force').checked, ...opts()});
        $('compare-force').checked = false;
        rerun = runCompare;
        renderCompare(data);
    }
    $('run-compare').addEventListener('click', () => withBusy('Đang so sánh (tóm tắt hai bản)', runCompare));

    checkHealth();
})();
