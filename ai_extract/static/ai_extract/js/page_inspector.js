document.querySelectorAll('.bbox').forEach(box => {
    box.addEventListener('click', () => {
        document.querySelectorAll('.bbox,.block-card').forEach(item => item.classList.remove('active'));
        box.classList.add('active');
        const card = document.getElementById(box.dataset.block);
        if (card) {
            card.classList.add('active');
            card.scrollIntoView({behavior: 'smooth', block: 'center'});
        }
    });
});
document.querySelectorAll('.block-card').forEach(card => {
    card.addEventListener('click', () => {
        const box = document.querySelector(`[data-block="${card.id}"]`);
        if (box) box.click();
    });
});
