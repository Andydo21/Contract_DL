document.querySelectorAll('.contract-card').forEach((card, index) => {
    card.style.animation = `cardIn .35s ease ${index * 35}ms both`;
});
const style = document.createElement('style');
style.textContent = '@keyframes cardIn{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}';
document.head.appendChild(style);

// Bulk upload: each file becomes its own document, and the documents are extracted one after another.
// The progress panel also follows a bulk rerun started from the admin page.
(() => {
    const csrf = document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';
    const progress = document.getElementById('bulk-progress');
    const upload = document.getElementById('bulk-upload');
    if (!progress) return;
    const label = {waiting: 'CHỜ', running: 'ĐANG CHẠY', complete: 'XONG', failed: 'LỖI'};
    const title = {waiting: 'Đang chờ trong hàng đợi', queued: 'Đang khởi động', running: 'Đang chạy', complete: 'Hoàn tất',
        partial: 'Xong, có văn bản lỗi', failed: 'Thất bại'};
    const entities = {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'};
    const escape = text => String(text ?? '').replace(/[&<>"']/g, c => entities[c]);
    let timer = null;

    const show = job => {
        if (!job) { progress.hidden = true; return; }
        progress.hidden = false;
        const kind = {rerun: 'Chạy lại hàng loạt', extract: 'Trích xuất', risk: 'Phân tích rủi ro'}[job.mode] || job.mode;
        const rows = job.items.map(i => `<li><span class="st st-${i.status}">${label[i.status] || i.status}</span>${escape(i.title)}` +
            (i.error ? `<span class="err">${escape(i.error)}</span>` : '') + '</li>').join('');
        progress.innerHTML = `<h3>${kind} · ${title[job.status] || job.status} · ${job.done}/${job.items.length}</h3><ol>${rows}</ol>` +
            (job.error ? `<p class="err">${escape(job.error)}</p>` : '');
    };
    const poll = async (id, started) => {
        clearTimeout(timer);
        try {
            const response = await fetch(id ? `/api/ai/bulk/${id}/` : '/api/ai/bulk/status/');
            const data = await response.json();
            show(data.job);
            const busy = Boolean(data.job && !['complete', 'partial', 'failed'].includes(data.job.status));
            if (busy) timer = setTimeout(() => poll(data.job.id, true), 4000);
            else if (started) setTimeout(() => location.reload(), 1500);
        } catch (error) {
            timer = setTimeout(() => poll(id, started), 8000);
        }
    };

    upload?.addEventListener('submit', async event => {
        event.preventDefault();
        const files = [...document.getElementById('bulk-files').files];
        const kind = document.getElementById('bulk-kind').value;
        if (!files.length) { alert('Chọn ít nhất một tệp.'); return; }
        const button = upload.querySelector('button');
        button.disabled = true;
        const ids = [];
        const stamp = new Date().toISOString().replace(/\D/g, '').slice(0, 14);
        try {
            for (const [index, file] of files.entries()) {
                progress.hidden = false;
                progress.innerHTML = `<h3>Đang tải lên ${index + 1}/${files.length}: ${escape(file.name)}</h3>`;
                const form = new FormData();
                form.append('contract_code', `${kind === 'legal' ? 'LAW' : 'DOC'}-${stamp}-${index + 1}`);
                form.append('title', file.name.replace(/\.[^.]+$/, ''));
                form.append('document_kind', kind);
                form.append('file', file);
                const response = await fetch('/api/contracts/create/', {method: 'POST', headers: {'X-CSRFToken': csrf}, body: form});
                const data = await response.json();
                if (!response.ok || !data.success) throw new Error(`${file.name}: ${data.error || 'HTTP ' + response.status}`);
                ids.push(data.contract_id);
            }
            // Each upload has already joined the extraction queue; follow the queue.
            poll(null, true);
        } catch (error) {
            const kept = ids.length ? `\n${ids.length} tệp tải lên trước lỗi vẫn được lưu và có trong danh sách.` : '';
            alert(error.message + kept);
        } finally {
            button.disabled = false;
        }
    });

    poll(null, false);
})();
