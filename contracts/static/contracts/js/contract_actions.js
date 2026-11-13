// What a person can do to a contract itself, shared by the dashboard and the contract page: edit its details,
// delete it (with undo), read its change history, and bring deleted contracts back from the trash.
//   ContractActions.edit(contract, {opener, versionId, onSaved})
//   ContractActions.remove(contract, {opener, onDeleted})      ContractActions.removeMany(contracts, {opener, onDone})
//   ContractActions.history(contract, {opener})                ContractActions.trash({opener, onRestored})
//   ContractActions.toast(message, {action, onAction})         ContractActions.money(value) / .day(iso)
(() => {
    const FIELDS = ['contract_code', 'title', 'contract_type', 'start_date', 'end_date', 'contract_value'];

    function el(tag, attrs = {}, ...children) {
        const node = document.createElement(tag);
        Object.entries(attrs).forEach(([key, value]) => {
            if (value === null || value === undefined || value === false) return;
            if (key === 'class') node.className = value;
            else if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
            else node.setAttribute(key, value === true ? '' : value);
        });
        children.flat().filter(child => child !== null && child !== undefined && child !== false)
            .forEach(child => node.append(child instanceof Node ? child : document.createTextNode(String(child))));
        return node;
    }

    const icon = name => el('i', {class: `fa-solid ${name}`, 'aria-hidden': 'true'});

    function csrf() {
        const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
        return match ? decodeURIComponent(match[1]) : '';
    }

    async function api(url, method = 'GET', body) {
        let response;
        try {
            response = await fetch(url, method === 'GET' ? {} : {
                method, headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf()},
                body: JSON.stringify(body || {})});
        } catch (error) {
            throw new Error('Không kết nối được máy chủ. Kiểm tra mạng rồi thử lại.');
        }
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            const message = data.error || (response.status >= 500 ? 'Máy chủ gặp lỗi. Hãy thử lại sau ít phút.' : `Lỗi ${response.status}`);
            throw Object.assign(new Error(message), {status: response.status, data});
        }
        return data;
    }

    // Amounts are Vietnamese đồng; an amount nobody entered is a dash, not a zero.
    function money(value) {
        if (value === null || value === undefined || value === '') return '—';
        const amount = Number(value);
        return Number.isFinite(amount) ? `${amount.toLocaleString('vi-VN', {maximumFractionDigits: 2})} đ` : '—';
    }

    function day(value) {
        const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(value || '');
        return match ? `${match[3]}/${match[2]}/${match[1]}` : '';
    }

    function moment(value) {
        const date = new Date(value);
        return isNaN(date) ? '' : date.toLocaleString('vi-VN', {day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit'});
    }

    function period(start, end) {
        if (start && end) return `${day(start)} – ${day(end)}`;
        if (start) return `Từ ${day(start)}`;
        return end ? `Đến ${day(end)}` : '';
    }

    // One message at a time at the bottom of the screen, with an optional action such as Undo.
    function toast(message, {action, onAction, tone = '', timeout = 9000} = {}) {
        document.querySelectorAll('.ca-toast').forEach(node => node.remove());
        const close = () => node.remove();
        const node = el('div', {class: `ca-toast ${tone}`, role: 'status'}, el('span', {}, message),
            action ? el('button', {type: 'button', class: 'ca-toast-action', onclick: () => { close(); onAction(); }}, action) : null,
            el('button', {type: 'button', class: 'ca-toast-close', 'aria-label': 'Đóng thông báo', onclick: close}, '×'));
        document.body.append(node);
        if (timeout) setTimeout(close, timeout);
        return node;
    }

    // A modal dialog: focus moves in and stays in, Escape and the backdrop close it (not while a request runs),
    // and focus goes back to the button that opened it.
    function openDialog({title, iconName, body, footer, opener, initialFocus, alert = false, wide = false}) {
        const state = {busy: false};
        const titleId = `ca-title-${Date.now()}`;
        const error = el('div', {class: 'ca-error', role: 'alert', hidden: true});
        const close = () => {
            if (state.busy) return;
            overlay.remove();
            if (opener && opener.isConnected) opener.focus();
        };
        const dialog = el('div', {class: `ca-dialog ${wide ? 'wide' : ''}`, role: alert ? 'alertdialog' : 'dialog', 'aria-modal': 'true', 'aria-labelledby': titleId},
            el('div', {class: 'ca-head'}, el('h3', {id: titleId}, iconName ? icon(iconName) : null, ' ', title),
                el('button', {type: 'button', class: 'ca-close', 'aria-label': 'Đóng', onclick: close}, '×')),
            el('div', {class: 'ca-body'}, body, error),
            footer ? el('div', {class: 'ca-foot'}, footer) : null);
        const overlay = el('div', {class: 'ca-overlay'}, dialog);
        overlay.addEventListener('mousedown', event => { if (event.target === overlay) close(); });
        overlay.addEventListener('keydown', event => {
            if (event.key === 'Escape') return close();
            if (event.key !== 'Tab') return;
            const nodes = [...dialog.querySelectorAll('button, input, select, textarea, a[href]')].filter(node => !node.disabled && node.offsetParent !== null);
            if (!nodes.length) return;
            const first = nodes[0], last = nodes[nodes.length - 1];
            if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
            else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
        });
        document.body.append(overlay);
        const target = initialFocus || dialog.querySelector('.ca-close');
        target.focus();
        return {
            close, state, node: dialog,
            fail: message => { error.textContent = message || ''; error.hidden = !message; },
            // While a request runs the dialog cannot be closed and its button says what is happening.
            busy: (button, label) => {
                state.busy = !!label;
                if (!button.dataset.label) button.dataset.label = button.innerHTML;
                button.disabled = !!label;
                if (label) button.replaceChildren(el('i', {class: 'fa-solid fa-circle-notch fa-spin', 'aria-hidden': 'true'}), ` ${label}`);
                else button.innerHTML = button.dataset.label;
            },
        };
    }

    const cancelButton = dialog => el('button', {type: 'button', class: 'ca-btn', onclick: () => dialog.close()}, 'Hủy');

    function field(name, label, {full, ...attrs}, value, hint) {
        const input = el('input', {class: 'ca-input', id: `ca-${name}`, name, ...attrs});
        input.value = value === null || value === undefined ? '' : value;
        return el('div', {class: `ca-field ${full ? 'full' : ''}`}, el('label', {for: `ca-${name}`}, label), input,
            hint ? el('small', {class: 'ca-hint'}, hint) : null, el('div', {class: 'ca-suggestion', 'data-for': name, hidden: true}));
    }

    function edit(contract, {opener, versionId, onSaved} = {}) {
        const form = el('form', {class: 'ca-grid', novalidate: true},
            field('contract_code', 'Mã hợp đồng *', {type: 'text', maxlength: 50, required: true}, contract.contract_code),
            field('contract_type', 'Loại hợp đồng', {type: 'text', maxlength: 100}, contract.contract_type),
            field('title', 'Tiêu đề *', {type: 'text', maxlength: 255, required: true, full: true}, contract.title),
            field('start_date', 'Ngày bắt đầu', {type: 'date'}, contract.start_date),
            field('end_date', 'Ngày kết thúc', {type: 'date'}, contract.end_date),
            field('contract_value', 'Giá trị hợp đồng (đ)', {type: 'number', min: 0, step: '0.01', inputmode: 'decimal', full: true},
                  contract.contract_value, 'Để trống nếu chưa xác định.'));
        const values = () => Object.fromEntries(FIELDS.map(name => [name, form.elements[name].value.trim()]));
        const original = values();
        const note = el('p', {class: 'ca-note', hidden: true});
        const suggestButton = el('button', {type: 'button', class: 'ca-btn ghost', onclick: () => suggest()}, icon('fa-wand-magic-sparkles'), ' Gợi ý từ văn bản');
        const save = el('button', {type: 'submit', class: 'ca-btn primary'}, icon('fa-floppy-disk'), ' Lưu');
        const dialog = openDialog({title: 'Sửa thông tin hợp đồng', iconName: 'fa-pen', opener, initialFocus: form.elements.title,
                                   body: [form, note], footer: [suggestButton, el('span', {class: 'ca-spacer'}), null, save]});
        dialog.node.querySelector('.ca-foot').insertBefore(cancelButton(dialog), save);
        save.setAttribute('form', form.id = `ca-form-${Date.now()}`);

        // Values the document states about itself. An empty box is filled; a box that already holds something else
        // only gets the document's value offered beside it, for the person to accept.
        async function suggest() {
            dialog.fail('');
            dialog.busy(suggestButton, 'Đang đọc văn bản…');
            try {
                const query = versionId ? `?version_id=${encodeURIComponent(versionId)}` : '';
                const {suggest: found} = await api(`/api/ai/contracts/${contract.id}/summary/suggest/${query}`);
                let filled = 0, offered = 0;
                FIELDS.forEach(name => {
                    const input = form.elements[name];
                    const value = found[name] === null || found[name] === undefined ? '' : String(found[name]).trim();
                    const box = form.querySelector(`.ca-suggestion[data-for="${name}"]`);
                    box.hidden = true;
                    if (!value || value === input.value.trim() || (name === 'contract_value' && Number(value) === Number(input.value))) return;
                    if (!input.value.trim()) {
                        input.value = value;
                        input.classList.add('suggested');
                        filled++;
                        return;
                    }
                    offered++;
                    box.replaceChildren('Văn bản ghi: ', el('strong', {}, name.endsWith('_date') ? day(value) : name === 'contract_value' ? money(value) : value), ' ',
                        el('button', {type: 'button', class: 'ca-link', onclick: () => { input.value = value; input.classList.add('suggested'); box.hidden = true; }}, 'Dùng giá trị này'));
                    box.hidden = false;
                });
                note.textContent = filled || offered
                    ? `Đã điền ${filled} ô trống và đề xuất ${offered} giá trị khác với hiện tại. Hãy kiểm tra rồi mới lưu.`
                    : 'Văn bản không cho thêm thông tin nào khác với hiện tại.';
                note.hidden = false;
            } catch (error) {
                dialog.fail(`Không đọc được gợi ý: ${error.message.replace(/^ai_summary: /, '')}`);
            } finally {
                dialog.busy(suggestButton, '');
            }
        }

        form.addEventListener('submit', async event => {
            event.preventDefault();
            if (dialog.state.busy) return;
            const now = values();
            // Only what the person changed is sent, so a field they did not touch is never rewritten.
            const body = Object.fromEntries(Object.entries(now).filter(([name, value]) => value !== original[name]));
            if (!now.contract_code || !now.title) return dialog.fail('Cần nhập mã hợp đồng và tiêu đề.');
            if (!Object.keys(body).length) return dialog.fail('Chưa có thay đổi nào để lưu.');
            if (now.start_date && now.end_date && now.end_date < now.start_date) return dialog.fail('Ngày kết thúc phải sau ngày bắt đầu.');
            dialog.fail('');
            dialog.busy(save, 'Đang lưu…');
            try {
                const data = await api(`/api/contracts/${contract.id}/`, 'PATCH', body);
                dialog.busy(save, '');
                dialog.close();
                toast('Đã lưu thay đổi.', {tone: 'ok', timeout: 4000});
                if (onSaved) onSaved(data.contract || {...contract, ...body});
            } catch (error) {
                dialog.busy(save, '');
                dialog.fail(error.message);
            }
        });
        return dialog;
    }

    const restore = (id, body) => api(`/api/contracts/${id}/restore/`, 'POST', body);

    // Deleting hides the contract; the toast that follows can put it straight back.
    function undoToast(contracts, onRestored) {
        const text = contracts.length === 1 ? `Đã xóa hợp đồng ${contracts[0].contract_code}.` : `Đã xóa ${contracts.length} hợp đồng.`;
        toast(text, {action: 'Hoàn tác', onAction: async () => {
            const failed = [];
            for (const contract of contracts) {
                try { await restore(contract.id); } catch (error) { failed.push(`${contract.contract_code}: ${error.message}`); }
            }
            toast(failed.length ? `Chưa khôi phục được: ${failed.join('; ')}` : 'Đã khôi phục.', {tone: failed.length ? 'bad' : 'ok'});
            if (onRestored) onRestored(contracts);
        }});
    }

    function remove(contract, {opener, onDeleted, onRestored} = {}) {
        const confirm = el('button', {type: 'button', class: 'ca-btn danger'}, icon('fa-trash'), ' Xóa hợp đồng');
        const dialog = openDialog({
            title: 'Xóa hợp đồng?', iconName: 'fa-trash', alert: true, opener,
            body: el('p', {class: 'ca-text'}, el('strong', {}, contract.contract_code), ` · ${contract.title}`, el('br'),
                'Hợp đồng sẽ bị ẩn khỏi danh sách cùng mọi phiên bản của nó. Dữ liệu vẫn được giữ trong thùng rác và khôi phục lại được.'),
            footer: [el('span', {class: 'ca-spacer'}), confirm]});
        // Opens on Cancel: Enter pressed by habit must not delete anything.
        const cancel = cancelButton(dialog);
        dialog.node.querySelector('.ca-foot').insertBefore(cancel, confirm);
        cancel.focus();
        confirm.addEventListener('click', async () => {
            dialog.fail('');
            dialog.busy(confirm, 'Đang xóa…');
            try {
                await api(`/api/contracts/${contract.id}/`, 'DELETE');
                dialog.busy(confirm, '');
                dialog.close();
                if (onDeleted) onDeleted(contract);
                undoToast([contract], onRestored);
            } catch (error) {
                dialog.busy(confirm, '');
                dialog.fail(error.message);
            }
        });
        return dialog;
    }

    function removeMany(contracts, {opener, onDone} = {}) {
        const confirm = el('button', {type: 'button', class: 'ca-btn danger'}, icon('fa-trash'), ` Xóa ${contracts.length} hợp đồng`);
        const dialog = openDialog({
            title: `Xóa ${contracts.length} hợp đồng?`, iconName: 'fa-trash', alert: true, opener,
            body: [el('p', {class: 'ca-text'}, 'Các hợp đồng sau sẽ bị ẩn khỏi danh sách. Dữ liệu vẫn được giữ trong thùng rác và khôi phục lại được.'),
                   el('ul', {class: 'ca-list'}, contracts.map(c => el('li', {}, el('strong', {}, c.contract_code), ` · ${c.title}`)))],
            footer: [el('span', {class: 'ca-spacer'}), confirm]});
        const cancel = cancelButton(dialog);
        dialog.node.querySelector('.ca-foot').insertBefore(cancel, confirm);
        cancel.focus();
        confirm.addEventListener('click', async () => {
            dialog.fail('');
            dialog.busy(confirm, 'Đang xóa…');
            const deleted = [], failed = [];
            for (const contract of contracts) {
                try {
                    await api(`/api/contracts/${contract.id}/`, 'DELETE');
                    deleted.push(contract);
                } catch (error) {
                    failed.push(`${contract.contract_code}: ${error.message}`);
                }
            }
            dialog.busy(confirm, '');
            if (onDone) onDone(deleted);
            if (failed.length) {
                // What could not be deleted stays on screen with its reason; the rest is already gone.
                confirm.hidden = true;
                dialog.fail(`Đã xóa ${deleted.length}/${contracts.length}. Chưa xóa được — ${failed.join(' | ')}`);
            } else {
                dialog.close();
            }
            if (deleted.length) undoToast(deleted, onDone);
        });
        return dialog;
    }

    function history(contract, {opener} = {}) {
        const list = el('div', {class: 'ca-history'}, el('p', {class: 'ca-empty'}, 'Đang tải lịch sử…'));
        const dialog = openDialog({title: `Lịch sử thay đổi · ${contract.contract_code}`, iconName: 'fa-clock-rotate-left', opener, body: list, wide: true});
        api(`/api/contracts/${contract.id}/history/`).then(({history: rows}) => {
            list.replaceChildren(...(rows.length ? rows.map(row => el('div', {class: 'ca-history-row'},
                el('div', {class: 'ca-history-head'}, el('strong', {}, row.label),
                    row.detail && !row.changes.length ? el('span', {class: 'ca-history-detail'}, row.detail) : null,
                    el('span', {class: 'ca-history-meta'}, `${row.user || 'Hệ thống'} · ${moment(row.at)}`)),
                row.changes.length ? el('ul', {}, row.changes.map(change => el('li', {}, `${change.label}: `,
                    el('span', {class: 'ca-before'}, change.before === null || change.before === '' ? '(trống)' : change.before), ' → ',
                    el('span', {class: 'ca-after'}, change.after === null || change.after === '' ? '(trống)' : change.after)))) : null))
                : [el('p', {class: 'ca-empty'}, 'Chưa ghi nhận thay đổi nào cho hợp đồng này.')]));
        }).catch(error => { list.replaceChildren(); dialog.fail(error.message); });
        return dialog;
    }

    function trash({opener, onRestored} = {}) {
        const list = el('div', {class: 'ca-trash'}, el('p', {class: 'ca-empty'}, 'Đang tải thùng rác…'));
        const dialog = openDialog({title: 'Thùng rác', iconName: 'fa-trash-can-arrow-up', opener, body: list, wide: true});
        const row = item => {
            // Another contract uses the code now: the person picks a new one to restore under.
            const code = item.code_taken ? el('input', {class: 'ca-input', type: 'text', maxlength: 50, 'aria-label': `Mã mới cho ${item.contract_code}`}) : null;
            if (code) code.value = `${item.contract_code}-KP`.slice(0, 50);
            const button = el('button', {type: 'button', class: 'ca-btn primary'}, icon('fa-rotate-left'), ' Khôi phục');
            const problem = el('div', {class: 'ca-row-error', role: 'alert', hidden: true});
            const node = el('div', {class: 'ca-trash-row'},
                el('div', {class: 'ca-trash-info'}, el('strong', {}, item.contract_code), ` · ${item.title}`,
                    el('small', {}, `Xóa ${moment(item.deleted_at)}${item.deleted_by ? ` bởi ${item.deleted_by}` : ''}`),
                    code ? el('small', {class: 'ca-warn'}, 'Mã này đang được hợp đồng khác dùng. Nhập mã mới để khôi phục:') : null, code, problem),
                button);
            button.addEventListener('click', async () => {
                problem.hidden = true;
                dialog.busy(button, 'Đang khôi phục…');
                try {
                    const data = await restore(item.id, code ? {contract_code: code.value.trim()} : {});
                    dialog.busy(button, '');
                    node.remove();
                    if (!list.querySelector('.ca-trash-row')) list.replaceChildren(el('p', {class: 'ca-empty'}, 'Thùng rác trống.'));
                    toast(`Đã khôi phục hợp đồng ${data.contract_code}.`, {tone: 'ok', timeout: 5000});
                    if (onRestored) onRestored(data);
                } catch (error) {
                    dialog.busy(button, '');
                    problem.textContent = error.message;
                    problem.hidden = false;
                }
            });
            return node;
        };
        api('/api/contracts/trash/').then(({contracts}) => {
            list.replaceChildren(...(contracts.length ? contracts.map(row) : [el('p', {class: 'ca-empty'}, 'Thùng rác trống.')]));
        }).catch(error => { list.replaceChildren(); dialog.fail(error.message); });
        return dialog;
    }

    // A deletion made on the contract page is announced (with Undo) on the page the person lands on.
    function announceDeleted(contract) {
        try { sessionStorage.setItem('contract-deleted', JSON.stringify({id: contract.id, contract_code: contract.contract_code, title: contract.title})); } catch (error) { /* private mode */ }
    }

    function showAnnouncedDeletion(onRestored) {
        let contract = null;
        try {
            contract = JSON.parse(sessionStorage.getItem('contract-deleted'));
            sessionStorage.removeItem('contract-deleted');
        } catch (error) { /* nothing to announce */ }
        if (contract && contract.id) undoToast([contract], onRestored);
    }

    window.ContractActions = {edit, remove, removeMany, history, trash, toast, money, day, period, announceDeleted, showAnnouncedDeletion};
})();
