// Photos of one document, page by page: the user sees them numbered and sets the order before sending.
// The server joins them into one PDF in exactly the order of the 'file' fields it receives.
(function () {
    const IMAGE = /\.(png|jpe?g|webp|bmp|tiff?)$/i;

    function attach(input, list, onChange) {
        let files = [];
        let dragged = null;
        list.classList.add('page-image-list');

        function render() {
            list.replaceChildren();
            if (files.length < 2) { list.style.display = 'none'; if (onChange) onChange(files); return; }
            list.style.display = 'grid';
            files.forEach((file, index) => {
                const item = document.createElement('div');
                item.className = 'page-image-item';
                item.draggable = true;
                item.dataset.index = index;
                const img = document.createElement('img');
                img.alt = file.name;
                img.src = URL.createObjectURL(file);
                img.onload = () => URL.revokeObjectURL(img.src);
                const label = document.createElement('div');
                label.className = 'page-image-label';
                label.textContent = `Trang ${index + 1}`;
                const name = document.createElement('div');
                name.className = 'page-image-name';
                name.textContent = file.name;
                const controls = document.createElement('div');
                controls.className = 'page-image-controls';
                [['↑', -1, 'Chuyển lên trước'], ['↓', 1, 'Chuyển xuống sau']].forEach(([text, step, title]) => {
                    const button = document.createElement('button');
                    button.type = 'button'; button.textContent = text; button.title = title;
                    button.disabled = index + step < 0 || index + step >= files.length;
                    button.onclick = (event) => { event.preventDefault(); event.stopPropagation(); move(index, index + step); };
                    controls.appendChild(button);
                });
                const remove = document.createElement('button');
                remove.type = 'button'; remove.textContent = '✕'; remove.title = 'Bỏ ảnh này';
                remove.onclick = (event) => { event.preventDefault(); event.stopPropagation(); files.splice(index, 1); render(); };
                controls.appendChild(remove);
                item.addEventListener('dragstart', () => { dragged = index; item.classList.add('dragging'); });
                item.addEventListener('dragend', () => item.classList.remove('dragging'));
                item.addEventListener('dragover', (event) => event.preventDefault());
                item.addEventListener('drop', (event) => {
                    event.preventDefault(); event.stopPropagation();
                    if (dragged !== null && dragged !== index) move(dragged, index);
                    dragged = null;
                });
                item.append(img, label, name, controls);
                list.appendChild(item);
            });
            if (onChange) onChange(files);
        }

        function move(from, to) {
            const [file] = files.splice(from, 1);
            files.splice(to, 0, file);
            render();
        }

        function set(fileList) {
            files = Array.from(fileList || []);
            // Phone photos: capture order by file time, then by name (IMG_0001, IMG_0002 …).
            if (files.length > 1 && files.every(f => IMAGE.test(f.name))) {
                files.sort((a, b) => (a.lastModified - b.lastModified) || a.name.localeCompare(b.name, undefined, { numeric: true }));
            }
            render();
        }

        input.addEventListener('change', () => set(input.files));
        return {
            set,
            files: () => files.slice(),
            // Several files are accepted only as photos of one document.
            error: () => files.length > 1 && !files.every(f => IMAGE.test(f.name))
                ? 'Khi chọn nhiều file, tất cả phải là ảnh chụp các trang của cùng một văn bản.' : '',
            appendTo(formData) {
                formData.delete('file');
                files.forEach(file => formData.append('file', file, file.name));
                return formData;
            },
            clear() { files = []; render(); },
        };
    }

    if (!document.getElementById('page-images-style')) {
        const style = document.createElement('style');
        style.id = 'page-images-style';
        style.textContent = `
            .page-image-list { display: none; grid-template-columns: repeat(auto-fill, minmax(110px, 1fr)); gap: 10px; margin-top: 12px; }
            .page-image-item { position: relative; border: 1px solid rgba(255,255,255,0.15); border-radius: 8px; padding: 6px; background: rgba(0,0,0,0.2); cursor: grab; text-align: center; }
            .page-image-item.dragging { opacity: 0.4; }
            .page-image-item img { width: 100%; height: 120px; object-fit: contain; display: block; border-radius: 4px; background: #fff; }
            .page-image-label { font-weight: 600; font-size: 12px; margin-top: 4px; }
            .page-image-name { font-size: 10.5px; opacity: 0.7; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
            .page-image-controls { display: flex; justify-content: center; gap: 4px; margin-top: 4px; }
            .page-image-controls button { min-width: 28px; padding: 2px 6px; border-radius: 4px; border: 1px solid rgba(255,255,255,0.2); background: rgba(255,255,255,0.08); color: inherit; cursor: pointer; }
            .page-image-controls button:disabled { opacity: 0.3; cursor: default; }`;
        document.head.appendChild(style);
    }

    window.PageImages = { attach };
})();
