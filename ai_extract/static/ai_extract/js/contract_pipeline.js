const form = document.getElementById('extract-form');
const message = document.getElementById('pipeline-message');
if (form) form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const button = form.querySelector('button');
    const label = button.querySelector('.button-label');
    button.disabled = true;
    label.textContent = 'Đang chạy PlanA dual pipeline…';
    message.hidden = false;
    message.classList.remove('error');
    message.textContent = 'Đang chạy Surya layout và hai nhánh Qdrant dense/ColPali.';
    try {
        const csrf = form.querySelector('[name=csrfmiddlewaretoken]').value;
        const response = await fetch(form.dataset.endpoint, {method: 'POST', headers: {'X-CSRFToken': csrf}});
        const data = await response.json();
        if (!response.ok || !data.success) throw new Error(data.error || 'Extraction failed');
        message.textContent = `Hoàn tất ${data.total_pages} trang, ${data.total_blocks} blocks · Dense ${data.dense_index_status} · ColPali ${data.colpali_index_status}.`;
        window.setTimeout(() => window.location.reload(), 700);
    } catch (error) {
        message.classList.add('error');
        message.textContent = error.message;
        button.disabled = false;
        label.textContent = 'Thử lại extraction';
    }
});
