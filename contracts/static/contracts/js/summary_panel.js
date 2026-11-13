// Contract summary panel, shown before extraction and risk analysis.
// ai_summary reads the uploaded file itself, so this works whether or not extraction ever ran.
//   const panel = SummaryPanel.mount(element, {contractId, versionId});  panel.load(otherVersionId);
//   SummaryPanel.quick(element, {file, text});   // summarize an input before saving it; clearQuick(element) discards it
(() => {
    const AUTO = {
        queued: ['Đang chờ tóm tắt', 'busy'], running: ['Đang tóm tắt…', 'busy'],
        done: ['Đã tóm tắt', 'ok'], failed: ['Tóm tắt lỗi', 'bad'],
    };
    const KINDS = {pdf: 'PDF', docx: 'DOCX', txt: 'TXT'};
    const POLL_MS = 4000;
    const POLL_LIMIT = 150;  // 10 minutes
    const MAX_FILE_MB = 25;  // SUMMARY_MAX_FILE_MB in ai_summary

    function el(tag, attrs = {}, ...children) {
        const node = document.createElement(tag);
        Object.entries(attrs).forEach(([k, v]) => {
            if (k === 'class') node.className = v;
            else if (k.startsWith('on')) node.addEventListener(k.slice(2), v);
            else node.setAttribute(k, v);
        });
        children.flat().filter(c => c !== null && c !== undefined && c !== false)
            .forEach(c => node.append(c instanceof Node ? c : document.createTextNode(String(c))));
        return node;
    }

    function csrf() {
        const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
        return match ? decodeURIComponent(match[1]) : '';
    }

    async function api(url, body) {
        const form = body instanceof FormData;
        const response = await fetch(url, body === undefined ? {} : {
            method: 'POST', body: form ? body : JSON.stringify(body),
            headers: form ? {'X-CSRFToken': csrf()} : {'Content-Type': 'application/json', 'X-CSRFToken': csrf()}});
        const data = await response.json().catch(() => ({error: `HTTP ${response.status}`}));
        if (!response.ok) throw Object.assign(new Error(data.error || data.detail || `HTTP ${response.status}`), {status: response.status});
        return data;
    }

    // Say which part is down in plain words; internal URLs go to the console, not the screen.
    function friendly(message) {
        const known = /summary model request failed|chat\/completions/i.test(message)
            ? 'Model tóm tắt trên Kaggle chưa kết nối được (notebook đang tắt hoặc mất tunnel ngrok). Bật lại rồi bấm thử lại.'
            : /ai_summary không phản hồi/i.test(message) ? 'Dịch vụ ai_summary chưa chạy. Bật container ai-summary rồi bấm thử lại.' : '';
        if (known) console.warn('ai_summary:', message);
        return known || message.replace(/^ai_summary: /, '');
    }

    function optionsBar(onChange) {
        const perspective = el('select', {class: 'sp-select', title: 'Góc nhìn'},
            el('option', {value: 'general'}, 'Góc nhìn chung'),
            el('option', {value: 'employee'}, 'Người lao động'),
            el('option', {value: 'hr'}, 'HR / quản lý'));
        const length = el('select', {class: 'sp-select', title: 'Độ dài'},
            el('option', {value: 'detailed'}, 'Chi tiết'),
            el('option', {value: 'short'}, 'Ngắn'),
            el('option', {value: 'one_sentence'}, '1 câu'));
        const explain = el('input', {type: 'checkbox'});
        [perspective, length, explain].forEach(input => input.addEventListener('change', onChange));
        return {
            node: el('div', {class: 'sp-options'}, perspective, length,
                     el('label', {class: 'sp-check'}, explain, 'Giải thích thuật ngữ')),
            value: () => ({perspective: perspective.value, length: length.value, explain_terms: explain.checked}),
            set: view => {
                perspective.value = view.perspective;
                length.value = view.length;
                explain.checked = view.explain_terms;
            },
        };
    }

    function sourceLine(source, origin) {
        if (!source) return '';
        if (origin === 'database') return `Nguồn: text trong database · ${source.chars.toLocaleString('vi-VN')} ký tự`;
        const parts = [KINDS[source.kind] || source.kind, `${source.chars.toLocaleString('vi-VN')} ký tự`];
        if (source.pages) parts.push(`${source.pages} trang`);
        if (source.ocr_pages && source.ocr_pages.length) parts.push(`OCR ${source.ocr_pages.length} trang scan`);
        return `Đọc từ file: ${parts.join(' · ')}`;
    }

    function keyDates(items) {
        if (!items || !items.length) return [];
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        return [el('div', {class: 'sp-dates'}, items.map(item => {
            const day = /^\d{4}-\d{2}-\d{2}$/.test(item.date || '') ? new Date(`${item.date}T00:00:00`) : null;
            if (!day || isNaN(day)) return el('div', {class: 'sp-date'}, el('span', {class: 'sp-date-label'}, item.label));
            const left = Math.round((day - today) / 86400000);
            const tail = item.kind !== 'end' ? '' : left < 0 ? 'đã hết hạn' : left === 0 ? 'hết hạn hôm nay' : `còn ${left} ngày`;
            return el('div', {class: `sp-date ${item.kind === 'end' && left >= 0 && left <= 30 ? 'soon' : ''}`},
                el('span', {class: 'sp-date-label'}, item.label),
                el('strong', {}, day.toLocaleDateString('vi-VN')),
                item.computed ? el('small', {}, 'tính từ thời hạn') : null,
                tail ? el('small', {}, tail) : null);
        }))];
    }

    // Scalars carry confidence in structured.confidence; parties and list items carry their own.
    function lowConfidence(structured) {
        const items = Object.values(structured).filter(Array.isArray).flat();
        return [...Object.values(structured.confidence || {}), ...items.map(item => item && item.confidence)]
            .filter(c => c && c.level === 'low').length;
    }

    const CHECK = {found: ['✓', 'có'], partial: ['◐', 'thiếu một phần'], missing: ['✗', 'không thấy']};

    // Which required contents the document has. Open when something is missing, so the list card's
    // "missing N" chip is explained right here.
    function checklist(data) {
        const items = (data && data.items) || [];
        if (!items.length) return [];
        const gaps = items.filter(item => item.status !== 'found').length;
        return [el('details', {class: `sp-more sp-checklist ${gaps ? 'gaps' : 'full'}`, ...(gaps ? {open: ''} : {})},
            el('summary', {}, gaps ? `Thiếu ${gaps}/${items.length} nội dung bắt buộc` : `Đủ ${items.length} nội dung bắt buộc`,
                data.basis ? el('span', {class: 'sp-basis'}, ` · ${data.basis}`) : null),
            el('ul', {}, items.map(item => {
                const [mark, word] = CHECK[item.status] || ['•', item.status];
                const where = item.sections && item.sections.length ? ` (${item.sections.join(', ')})` : '';
                const lacking = item.status === 'partial' && item.missing && item.missing.length ? ` — thiếu ${item.missing.join(', ')}` : '';
                return el('li', {class: `st-${item.status}`}, `${mark} ${item.label}: ${word}${where}${lacking}`);
            })),
            gaps ? el('p', {class: 'sp-note'}, 'Đối chiếu theo từ khóa, cần người đọc kiểm tra lại với văn bản gốc.') : null)];
    }

    // Checklist gaps, dropped values and low-confidence fields from a full ai_summary result.
    function details(data) {
        const notes = [];
        const source = sourceLine(data.source, data.origin);
        if (source) notes.push(el('div', {class: 'sp-note'}, source));
        (data.source && data.source.warnings || []).forEach(w => notes.push(el('div', {class: 'sp-note warn'}, w)));
        if (data.unverified && data.unverified.length) {
            notes.push(el('details', {class: 'sp-more'},
                el('summary', {}, `${data.unverified.length} giá trị model đưa ra nhưng không khớp văn bản gốc — đã loại`),
                el('ul', {}, data.unverified.map(u => el('li', {}, `${u.field}: “${u.text}” — ${u.reason || 'số không có trong nguồn'}`)))));
        }
        const low = lowConfidence(data.structured || {});
        if (low) notes.push(el('div', {class: 'sp-note warn'}, `⚠ ${low} giá trị có độ tin cậy thấp, nên đối chiếu lại với văn bản gốc.`));
        return [...keyDates(data.key_dates), ...checklist(data.checklist), ...notes];
    }

    const DEFAULT_VIEW = {perspective: 'general', length: 'detailed', explain_terms: false};
    const IN_PROGRESS = new Set(['queued', 'running']);
    // Lookarounds, not \b: JavaScript does not count Đ as a word character.
    const CITATION = /(?<=\()(Điều \d+[a-zđ]?|Article \d+|Phần mở đầu)(?=\))/g;

    // One state object drives render(); a request only applies if it is still the latest one.
    class Panel {
        constructor(root, {contractId, versionId}) {
            this.root = root;
            this.contractId = contractId;
            this.versionId = versionId ? String(versionId) : null;
            this.state = {loading: true};
            this.seq = 0;
            this.polls = 0;
            this.timer = null;
            this.ticker = null;
            this.against = null;
            this.options = optionsBar(() => this.changeView());
            root.classList.add('summary-panel');
            root.setAttribute('aria-live', 'polite');
            this.refresh();
        }

        query() {
            return this.versionId ? `?version_id=${encodeURIComponent(this.versionId)}` : '';
        }

        // Same version: refresh in place, keeping the chosen view. Another version: start over.
        load(versionId) {
            const next = versionId ? String(versionId) : null;
            if (next === this.versionId) return this.refresh();
            this.versionId = next;
            this.seq++;  // answers for the previous version no longer apply
            this.polls = 0;
            this.sections = null;
            this.changesFor = null;
            this.against = null;
            this.stopTicker();
            this.options.set(DEFAULT_VIEW);
            this.state = {loading: true};
            this.render();
            return this.refresh();
        }

        update(changes) {
            this.state = {...this.state, ...changes};
            this.render();
        }

        async refresh() {
            clearTimeout(this.timer);
            if (!this.root.isConnected) return;  // the detail panel was redrawn for another contract
            const seq = this.seq;
            try {
                const saved = await api(`/api/ai/contracts/${this.contractId}/summary/${this.query()}`);
                if (seq !== this.seq) return;
                const same = JSON.stringify(saved) === JSON.stringify(this.state.saved);
                const previous = this.state.saved;
                if (previous && previous.updated_at !== saved.updated_at && !this.ownRun) {
                    // Regenerated by the worker: what is on screen is the old text.
                    this.options.set(DEFAULT_VIEW);
                    this.sections = null;
                    this.changesFor = null;
                    this.state = {...this.state, result: null, citation: null, changes: null};
                }
                this.ownRun = false;
                // Redrawing on every poll would close an open dropdown and reset scrolling.
                if (!same || this.state.loading) this.update({saved, loading: false, error: ''});
                this.loadChanges(saved);
                const inProgress = !!(saved.status && IN_PROGRESS.has(saved.status.state));
                // A stale summary is only worth watching when the worker will redo it on its own.
                if (inProgress || (saved.stale && saved.auto_refresh)) {
                    if (this.polls++ < POLL_LIMIT) this.timer = setTimeout(() => this.refresh(), POLL_MS);
                    else if (inProgress) this.update({error: 'Tóm tắt chạy lâu bất thường. Tải lại trang sau ít phút để kiểm tra.'});
                } else {
                    this.polls = 0;
                }
            } catch (error) {
                if (seq === this.seq) this.update({loading: false, error: error.message});
            }
        }

        // Once per version: what changed since the previous one.
        async loadChanges(saved) {
            if (saved.versions.length < 2 || !saved.summary || this.changesFor === `${this.versionId}|${this.against}`) return;
            if (!saved.has_previous && !this.against) return;  // the first version has nothing before it by default
            const key = this.changesFor = `${this.versionId}|${this.against}`;
            const params = new URLSearchParams();
            if (this.versionId) params.set('version_id', this.versionId);
            if (this.against) params.set('against', this.against);
            try {
                const changes = await api(`/api/ai/contracts/${this.contractId}/summary/changes/?${params}`);
                if (key === this.changesFor) this.update({changes});
            } catch (error) {
                // Shown once and not retried on every poll; choosing another version or a new run tries again.
                console.warn('summary changes:', error.message);
                if (key === this.changesFor) this.update({changes: {previous_number: null, changes: [],
                    summary: `Không so sánh được: ${friendly(error.message)}`}});
            }
        }

        async openCitation(label) {
            try {
                this.sections = this.sections || (await api(`/api/ai/contracts/${this.contractId}/summary/sections/${this.query()}`)).sections;
                this.update({citation: {label, text: this.sections[label] || 'Không tìm thấy điều khoản này trong văn bản.'}});
            } catch (error) {
                this.update({citation: {label, text: `Không mở được điều khoản: ${friendly(error.message)}`}});
            }
        }

        changesSection(saved, changes) {
            const others = saved.versions.filter(v => v.number !== saved.version_number);
            const shown = changes && changes.previous_number;
            const select = el('select', {class: 'sp-select', 'aria-label': 'Phiên bản để so sánh'},
                !saved.has_previous && !this.against ? el('option', {value: ''}, 'Chọn phiên bản') : null,
                others.map(v => el('option', {value: v.id}, `v${v.number}`)));
            const current = this.against || others.filter(v => v.number === shown).map(v => v.id)[0] || (saved.has_previous ? others.filter(v => v.number < saved.version_number).pop().id : '');
            select.value = current;
            select.addEventListener('change', () => {
                this.against = select.value || null;
                this.update({changes: null});
                this.loadChanges(saved);
            });
            return el('div', {class: 'sp-changes'},
                el('div', {class: 'sp-changes-head'}, el('strong', {}, 'So sánh với'), select,
                    shown ? el('span', {class: 'sp-version'}, `${changes.changes.length} thay đổi`) : null),
                changes ? el('pre', {}, changes.summary || 'Chọn một phiên bản để xem thay đổi.')
                    : saved.has_previous || this.against ? el('p', {class: 'sp-empty'}, 'Đang so sánh…') : null);
        }

        textWithCitations(text) {
            const parts = text.split(CITATION);
            // split with one capture group: odd indexes are the cited labels
            return el('pre', {class: 'sp-text'}, parts.map((part, index) => index % 2
                ? el('button', {class: 'sp-cite', type: 'button', title: 'Xem điều khoản gốc', onclick: () => this.openCitation(part)}, part)
                : part));
        }

        changeView() {
            const view = this.options.value();
            // Before the first summary there is nothing to render another way: the choice waits for the run button,
            // so opening a dropdown never starts a run by itself.
            if (!(this.state.saved && this.state.saved.summary)) return;
            if (JSON.stringify(view) === JSON.stringify(DEFAULT_VIEW)) {
                this.seq++;  // a view still on its way no longer applies
                this.stopTicker();
                this.update({result: null, working: null, error: ''});
                return;
            }
            this.request(view, false, 'view');
        }

        async request(view, force, working) {
            const seq = ++this.seq;
            clearTimeout(this.timer);
            this.startTicker();
            this.update({working, error: ''});
            try {
                const data = await api(`/api/ai/contracts/${this.contractId}/summarize/`,
                                       {...view, force, version_id: this.versionId});
                if (seq !== this.seq) return;
                this.stopTicker();
                this.update({working: null, result: {...data, view}});
                if (data.saved || force) {
                    this.ownRun = true;
                    this.sections = null;
                    this.changesFor = null;
                    this.refresh();
                }
            } catch (error) {
                if (seq !== this.seq) return;
                this.stopTicker();
                // Go back to the view whose text is on screen so the controls and the text agree; with no text on
                // screen the choice stays for the next try.
                const onScreen = this.state.result ? this.state.result.view : this.state.saved && this.state.saved.summary ? DEFAULT_VIEW : null;
                if (onScreen) this.options.set(onScreen);
                this.update({working: null, error: error.message});
                if (error.status === 409) this.refresh();
            }
        }

        // The Word file holds the view on screen (audience, length), not always the stored default.
        async exportWord() {
            const view = this.state.result ? this.state.result.view : DEFAULT_VIEW;
            const params = new URLSearchParams(Object.entries(view).map(([key, value]) => [key, String(value)]));
            if (this.versionId) params.set('version_id', this.versionId);
            this.update({exporting: true, error: ''});
            try {
                const response = await fetch(`/api/ai/contracts/${this.contractId}/summary/export/?${params}`);
                if (!response.ok) {
                    const data = await response.json().catch(() => ({}));
                    throw new Error(data.error || `HTTP ${response.status}`);
                }
                const header = response.headers.get('Content-Disposition') || '';
                const encoded = /filename\*=UTF-8''([^;]+)/i.exec(header);
                const plain = /filename="?([^";]+)"?/i.exec(header);
                const link = el('a', {href: URL.createObjectURL(await response.blob()),
                                      download: encoded ? decodeURIComponent(encoded[1]) : plain ? plain[1] : 'tom-tat-hop-dong.docx'});
                document.body.append(link);
                link.click();
                link.remove();
                setTimeout(() => URL.revokeObjectURL(link.href), 1000);
                this.update({exporting: false});
            } catch (error) {
                this.update({exporting: false, error: `Không tải được file Word: ${error.message}`});
            }
        }

        startTicker() {
            this.started = performance.now();
            clearInterval(this.ticker);
            this.ticker = setInterval(() => {
                const pill = this.root.querySelector('.sp-pill');
                if (pill && this.root.isConnected) pill.textContent = this.progressLabel();
                else this.stopTicker();
            }, 1000);
        }

        stopTicker() {
            clearInterval(this.ticker);
        }

        progressLabel() {
            return `Đang tóm tắt… ${Math.round((performance.now() - this.started) / 1000)}s`;
        }

        copy(text, button) {
            const done = message => {
                button.textContent = message;
                setTimeout(() => { button.replaceChildren(el('i', {class: 'fa-regular fa-copy'}), ' Sao chép'); }, 1500);
            };
            // navigator.clipboard exists only on https or localhost.
            (navigator.clipboard ? navigator.clipboard.writeText(text) : Promise.reject())
                .then(() => done('Đã sao chép'), () => done('Không sao chép được'));
        }

        render() {
            const {loading, saved, result, working, error, changes, citation, confirming, exporting} = this.state;
            const status = saved && saved.status;
            const running = !!(status && IN_PROGRESS.has(status.state));
            const text = result ? result.summary : saved && saved.summary;
            const failed = !!(status && status.state === 'failed') && !working;
            const [label, tone] = working ? [this.progressLabel(), 'busy']
                : running ? AUTO[status.state]
                : loading ? ['Đang tải…', 'busy']
                : saved && saved.stale ? [saved.auto_refresh ? 'Text đã đổi, chờ cập nhật' : 'Text đã đổi', saved.auto_refresh ? 'busy' : '']
                : failed && !text ? AUTO.failed
                : text ? ['Đã có tóm tắt', 'ok'] : ['Chưa tóm tắt', ''];
            const meta = result ? `${result.model_id} · ${result.cached ? 'từ cache' : `${(result.elapsed_ms / 1000).toFixed(1)}s`}`
                : saved && saved.summary ? `${saved.model_id} · ${new Date(saved.updated_at).toLocaleString('vi-VN')}` : '';

            const body = [];
            if (saved && saved.stale && !working) body.push(el('div', {class: 'sp-note warn'}, saved.auto_refresh
                ? 'Bản dưới đây được tạo từ text cũ. Hệ thống tự tóm tắt lại khi text ổn định và model trên Kaggle đang hoạt động.'
                : 'Bản dưới đây được tạo từ text cũ. Bấm “Tóm tắt lại” để cập nhật theo text hiện tại.'));
            if (loading) body.push(el('p', {class: 'sp-empty'}, 'Đang tải bản tóm tắt…'));
            else if (text) body.push(this.textWithCitations(text));
            else if (running || working) body.push(el('p', {class: 'sp-empty'}, 'Hệ thống đang đọc file và tóm tắt. Trang sẽ tự cập nhật khi xong.'));
            else if (saved && !saved.preliminary) body.push(el('p', {class: 'sp-empty'}, saved.has_text || saved.file_name
                ? 'Chưa có bản tóm tắt cho phiên bản này.' : 'Phiên bản này chưa có text hay file để tóm tắt.'));
            else if (saved && saved.preliminary && !running && !working) {
                body.push(el('div', {class: 'sp-note warn'}, 'Bản sơ bộ: các giá trị chép nguyên từ văn bản, chưa qua AI. Bản đầy đủ sẽ tự chạy khi model hoạt động lại.'),
                          el('pre', {class: 'sp-text'}, saved.preliminary));
            }
            if (citation) {
                body.push(el('div', {class: 'sp-citation'},
                    el('div', {class: 'sp-citation-head'}, el('strong', {}, citation.label),
                        el('button', {class: 'sp-cite', type: 'button', onclick: () => this.update({citation: null})}, 'Đóng')),
                    el('pre', {}, citation.text)));
            }
            if (result || (saved && saved.result)) body.push(...details(result || saved.result));
            if (saved && saved.summary && saved.versions && saved.versions.length > 1) body.push(this.changesSection(saved, changes));
            const previous = saved && saved.result && saved.result.previous;
            if (previous && previous.summary) {
                body.push(el('details', {class: 'sp-more sp-previous'},
                    el('summary', {}, `Bản tóm tắt trước${previous.updated_at ? ` · ${new Date(previous.updated_at).toLocaleString('vi-VN')}` : ''}`),
                    el('pre', {class: 'sp-text'}, previous.summary)));
            }
            const problem = error || (failed ? status.error : '');
            if (problem) body.push(el('div', {class: 'sp-error', role: 'alert'}, friendly(problem)));

            const canRun = !loading && !working && !running && saved && (saved.has_text || saved.file_name);
            const actionLabel = text ? ' Tóm tắt lại' : failed ? ' Thử lại' : ' Tóm tắt ngay';
            const focused = this.root.contains(document.activeElement) ? document.activeElement : null;
            this.root.replaceChildren(
                el('div', {class: 'sp-head'},
                    el('div', {class: 'sp-title'}, el('i', {class: 'fa-solid fa-wand-magic-sparkles'}), ' Tóm tắt hợp đồng',
                        saved && saved.version_number ? el('span', {class: 'sp-version'}, `v${saved.version_number}`) : null),
                    el('span', {class: `sp-pill ${tone}`}, label)),
                el('p', {class: 'sp-sub'}, saved && saved.has_text ? 'Tóm tắt từ text hợp đồng trong database. '
                    : saved && saved.file_name ? `Chưa có text trong database nên đọc trực tiếp từ ${saved.file_name}. ` : '',
                    meta ? el('span', {class: 'sp-meta'}, meta) : null),
                this.options.node,
                el('div', {class: 'sp-body'}, body),
                // A re-run takes minutes and replaces the text on screen, so it asks once before starting.
                confirming && canRun ? el('div', {class: 'sp-confirm', role: 'group', 'aria-label': 'Xác nhận tóm tắt lại'},
                    el('span', {}, 'Tóm tắt lại sẽ thay bản đang hiển thị và có thể mất vài phút. Bản hiện tại vẫn xem lại được ở mục “Bản tóm tắt trước”.'),
                    el('div', {class: 'sp-buttons'},
                        el('button', {class: 'sp-btn primary sp-confirm-yes', type: 'button', onclick: () => {
                            this.state.confirming = false;
                            this.request(this.options.value(), true, 'run');
                        }}, el('i', {class: 'fa-solid fa-rotate'}), ' Tóm tắt lại'),
                        el('button', {class: 'sp-btn', type: 'button', onclick: () => this.update({confirming: false})}, 'Hủy'))) : null,
                el('div', {class: 'sp-actions'},
                    el('div', {class: 'sp-buttons'},
                        confirming && canRun ? null : el('button', {class: 'sp-btn primary sp-run', type: 'button', ...(canRun ? {} : {disabled: ''}),
                                      onclick: () => text ? this.update({confirming: true}) : this.request(this.options.value(), false, 'run')},
                            el('i', {class: text ? 'fa-solid fa-rotate' : 'fa-solid fa-play'}), actionLabel),
                        text ? el('button', {class: 'sp-btn', type: 'button', onclick: event => this.copy(text, event.currentTarget)},
                            el('i', {class: 'fa-regular fa-copy'}), ' Sao chép') : null,
                        saved && saved.summary ? el('button', {class: 'sp-btn', type: 'button', ...(exporting || working ? {disabled: ''} : {}),
                                                              title: result ? 'Tải bản đang xem (đúng góc nhìn và độ dài đã chọn)' : 'Tải bản tóm tắt kèm ngày quan trọng và nội dung còn thiếu',
                                                              onclick: () => this.exportWord()},
                            el('i', {class: exporting ? 'fa-solid fa-circle-notch fa-spin' : 'fa-regular fa-file-word'}), exporting ? ' Đang tạo file…' : ' Tải Word') : null),
                    el('a', {class: 'sp-link', href: `/ai-extract/summary-lab/?contract=${encodeURIComponent(this.contractId)}`, target: '_blank', rel: 'noopener'},
                        'Xem chi tiết trong Summary Lab ↗')));
            // A run replaces the analysis the views are rendered from, so views wait for it. Before the first summary
            // the options stay open: they choose how that first run is written.
            const hasSource = !!(saved && (saved.has_text || saved.file_name));
            this.options.node.querySelectorAll('select, input').forEach(input => { input.disabled = loading || !hasSource || working === 'run' || running; });
            if (focused && this.root.contains(focused) && !focused.disabled) focused.focus();
            // The buttons are drawn anew each time: keep the keyboard on the step the person is in.
            else if (focused && confirming) this.root.querySelector('.sp-confirm-yes')?.focus();
            else if (focused && focused.classList.contains('sp-btn')) this.root.querySelector('.sp-run:not(:disabled)')?.focus();
        }
    }

    // Why a chosen file cannot be summarized, before sending it anywhere.
    function fileProblem(file) {
        if (!file) return '';
        if (!/\.(pdf|docx|txt)$/i.test(file.name)) return 'Chỉ tóm tắt được PDF, DOCX hoặc TXT. File Word cũ (.doc) hãy lưu lại thành .docx.';
        if (file.size > MAX_FILE_MB * 1024 * 1024) return `File lớn hơn ${MAX_FILE_MB} MB nên không tóm tắt được.`;
        return '';
    }

    function clearQuick(root) {
        root.quickToken = null;  // a result still on its way no longer belongs to the current input
        root.hidden = true;
        root.replaceChildren();
    }

    // Summarize the file or pasted text of an upload form before anything is saved.
    async function quick(root, {file, text, options}) {
        const token = {};
        root.quickToken = token;
        root.classList.add('summary-panel', 'sp-quick');
        root.hidden = false;
        root.replaceChildren(el('p', {class: 'sp-empty'}, el('i', {class: 'fa-solid fa-circle-notch fa-spin'}),
            file ? ` Đang đọc ${file.name} và tóm tắt…` : ' Đang tóm tắt văn bản…'));
        try {
            const problem = fileProblem(file);
            if (problem) throw new Error(problem);
            let data;
            if (file) {
                const form = new FormData();
                form.append('file', file);
                Object.entries(options || {}).forEach(([k, v]) => form.append(k, String(v)));
                data = await api('/api/ai/summary-lab/file/', form);
            } else {
                data = await api('/api/ai/summary-lab/text/', {text, ...(options || {})});
            }
            if (root.quickToken !== token) return;
            root.replaceChildren(
                el('div', {class: 'sp-head'}, el('div', {class: 'sp-title'}, 'Tóm tắt nhanh (chưa lưu)'),
                    el('span', {class: 'sp-pill ok'}, `${(data.elapsed_ms / 1000).toFixed(1)}s`)),
                el('pre', {class: 'sp-text'}, data.summary), ...details(data));
        } catch (error) {
            if (root.quickToken === token) root.replaceChildren(el('div', {class: 'sp-error', role: 'alert'}, `Không tóm tắt được. ${friendly(error.message)}`));
        }
    }

    // Values the document states about itself, for the person to check before saving. Never calls the model.
    async function suggest(file) {
        const form = new FormData();
        form.append('file', file);
        return (await api('/api/ai/summary-lab/read/', form)).suggest;
    }

    const overview = () => api('/api/ai/summaries/overview/');

    function expiryText(days) {
        return days < 0 ? `Đã hết hạn ${-days} ngày` : days === 0 ? 'Hết hạn hôm nay' : `Còn ${days} ngày`;
    }

    // Chips on each contract card: summary state, missing clauses, approaching end date.
    function decorateCards(data) {
        const STATES = {queued: ['Đang chờ tóm tắt', 'busy'], running: ['Đang tóm tắt', 'busy'], stale: ['Text đã đổi', 'busy'],
                        failed: ['Tóm tắt lỗi', 'bad'], done: ['Đã tóm tắt', 'ok']};
        document.querySelectorAll('.contract-card').forEach(card => {
            card.querySelector('.card-summary')?.remove();
            const item = data.contracts[card.dataset.id];
            if (!item) return;
            const chips = [];
            const state = STATES[item.state] || (item.has_summary ? STATES.done : null);
            if (state) chips.push(el('span', {class: `sp-chip ${state[1]}`}, state[0]));
            if (item.gaps) chips.push(el('span', {class: 'sp-chip warn', title: 'Nội dung bắt buộc theo Điều 21 BLLĐ 2019, đối chiếu theo từ khóa'}, `Thiếu ${item.gaps} nội dung`));
            if (item.days_left !== null && item.days_left <= 30) chips.push(el('span', {class: `sp-chip ${item.days_left < 0 ? 'bad' : 'warn'}`}, expiryText(item.days_left)));
            if (chips.length) card.append(el('div', {class: 'card-summary'}, chips));
        });
    }

    // What ends within the next 90 days or ended within the last 90, soonest first.
    function renderExpiring(root, data, open) {
        root.hidden = !data.expiring.length;
        root.replaceChildren(!data.expiring.length ? '' : el('details', {class: 'sp-expiring', ...(data.expiring.some(e => e.days_left <= 30) ? {open: ''} : {})},
            el('summary', {}, el('i', {class: 'fa-regular fa-calendar-xmark'}), ` Hết hạn trong 90 ngày qua hoặc 90 ngày tới (${data.expiring.length})`),
            data.expiring.map(e => el('button', {class: 'sp-expiring-row', type: 'button', onclick: () => open(e.contract_id)},
                el('span', {class: 'sp-expiring-name'}, `${e.code} · ${e.title}`),
                el('span', {class: `sp-chip ${e.days_left < 0 ? 'bad' : e.days_left <= 30 ? 'warn' : ''}`}, expiryText(e.days_left))))));
    }

    window.SummaryPanel = {mount: (root, args) => new Panel(root, args), quick, clearQuick, fileProblem, suggest,
                           overview, decorateCards, renderExpiring};
})();
