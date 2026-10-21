/**
 * DENSO ZERO-ERROR FACTORY COPILOT — NEWIDEA SCRIPT
 * Manages Unified Chat, Live Notification Polling, Canvas BBox Grounding,
 * and Expert Information Extraction into Neo4j.
 */

let chatHistory = [];
let lastCanvasGrounding = null;
let lastNeo4jPath = null;
let lastConfidence = null;
let lastActiveMachine = '';

document.addEventListener('DOMContentLoaded', () => {
    initNotifications();
    initNotificationBell();
    loadChatState(); // Khôi phục 100% lịch sử chat và trạng thái bản vẽ khi F5 hoặc quay lại
});

// ==============================================================================
// 1. NOTIFICATION POLLING & BELL DROPDOWN
// ==============================================================================

function initNotificationBell() {
    const bellBtn = document.getElementById('notif-bell-btn');
    const dropdown = document.getElementById('notif-dropdown');

    if (!bellBtn || !dropdown) return;

    bellBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        const isOpen = dropdown.style.display === 'block';
        dropdown.style.display = isOpen ? 'none' : 'block';
        if (!isOpen) {
            fetchNotifications(); // Lấy danh sách thắc mắc mới nhất khi click mở chuông
        }
    });

    document.addEventListener('click', (e) => {
        if (!dropdown.contains(e.target) && e.target !== bellBtn) {
            dropdown.style.display = 'none';
        }
    });
}

function initNotifications() {
    fetchNotifications();
}

async function fetchNotifications() {
    try {
        const res = await fetch('/api/notifications/');
        if (!res.ok) return;
        const data = await res.json();

        const badge = document.getElementById('notif-count-badge');
        const headerCount = document.getElementById('notif-header-count');
        const notifList = document.getElementById('notif-list');

        if (!badge || !notifList) return;

        if (data.count > 0) {
            badge.innerText = data.count;
            badge.style.display = 'flex';
            if (headerCount) headerCount.innerText = `${data.count} mới`;

            notifList.innerHTML = data.notifications.map(item => `
                <a href="/expert/ticket/${item.id}/" class="notif-item">
                    <div class="notif-item-top">
                        <span class="notif-item-code">${item.ticket_code}</span>
                        <span class="notif-item-time">${item.created_at}</span>
                    </div>
                    <div class="notif-item-q">"${escapeHtml(item.question)}"</div>
                    <div class="notif-item-meta">
                        ⚙️ ${escapeHtml(item.machine)} • Người hỏi: ${escapeHtml(item.operator_name)}
                    </div>
                </a>
            `).join('');
        } else {
            badge.style.display = 'none';
            if (headerCount) headerCount.innerText = '0 mới';
            notifList.innerHTML = '<div class="notif-empty">Không có thắc mắc nào đang chờ xử lý</div>';
        }
    } catch (err) {
        console.warn('[Notification Poll Error]', err);
    }
}

// ==============================================================================
// 2. UNIFIED CHAT: QUESTION SUBMISSION & 5-LAYER PROCESSING
// ==============================================================================

async function handleSendQuestion(event) {
    event.preventDefault();

    const qInput = document.getElementById('question-input');
    const nameInput = document.getElementById('operator-name-input');
    const machineSelect = document.getElementById('machine-select');
    const stream = document.getElementById('message-stream');
    const sendBtn = document.getElementById('send-btn');

    if (!qInput || !qInput.value.trim()) return;

    const query = qInput.value.trim();
    const operatorName = nameInput ? nameInput.value.trim() : 'Kỹ thuật viên';
    const machine = machineSelect ? machineSelect.value : '';

    // 1. Append User Message
    appendMessage({
        role: 'user',
        author: operatorName,
        text: query,
        time: getCurrentTime()
    });

    qInput.value = '';
    sendBtn.disabled = true;

    // 2. Append Loading Placeholder
    const loadingId = 'ai-loading-' + Date.now();
    const loadingEl = document.createElement('div');
    loadingEl.className = 'chat-msg ai-msg';
    loadingEl.id = loadingId;
    loadingEl.innerHTML = `
        <div class="msg-avatar">⚡</div>
        <div class="msg-content">
            <div class="msg-header">
                <strong class="msg-author">Hệ thống Động cơ 5 Lớp</strong>
                <span class="msg-time">Đang đối soát...</span>
            </div>
            <div class="msg-body" style="color: var(--neon-cyan); font-style: italic;">
                🔍 Đang quét chuỗi Neo4j Deterministic Graph ➔ Soi tọa độ BBox bản vẽ ➔ Chấm điểm Cross-Encoder Gating (≥ 85%)...
            </div>
        </div>
    `;
    stream.appendChild(loadingEl);
    stream.scrollTop = stream.scrollHeight;

    // 3. Call API /api/ask/
    try {
        const response = await fetch('/api/ask/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                query: query,
                operator_name: operatorName,
                machine: machine
            })
        });

        const data = await response.json();
        const placeholder = document.getElementById(loadingId);
        if (placeholder) placeholder.remove();

        if (data.success) {
            // Append AI Response
            appendMessage({
                role: 'ai',
                author: 'Hệ thống AI Zero-Error Copilot',
                text: data.answer_text || data.answer,
                failSafe: data.fail_safe,
                ticketId: data.ticket_id,
                confidence: data.confidence,
                time: getCurrentTime(),
                isKnowledgeContribution: data.is_knowledge_contribution,
                questionVariations: data.question_variations
            });

            // Update Multi-Document Pills & Canvas
            if (data.similar_cases && data.similar_cases.length) {
                appendMessage({
                    role: 'ai', author: 'Thư viện case A2 đã duyệt',
                    text: data.similar_cases.map(c =>
                        `${c.title} — ${c.machine} — r${c.revision}\n` +
                        `Xử lý: ${c.solution}\nXác minh: ${c.verification}\n` +
                        `Điều kiện áp dụng: ${c.applicability}\nNguồn: ${c.source_reference}\n` +
                        `ID: ${c.evidence_id}`
                    ).join('\n\n') + '\n\nGợi ý theo từ khóa; kiểm tra điều kiện áp dụng trong Thư viện case A2 trước khi sử dụng.',
                    time: getCurrentTime()
                });
            }
            if (data.related_documents && data.related_documents.length > 0) {
                renderRelatedDocsPills(data.related_documents);
            } else if (data.visual_grounding) {
                renderRelatedDocsPills([data.visual_grounding]);
            } else {
                renderRelatedDocsPills([]);
            }

            if (data.visual_grounding) {
                lastCanvasGrounding = data.visual_grounding;
                renderVisualCanvas(data.visual_grounding);
            } else {
                lastCanvasGrounding = null;
                renderVisualCanvas(null);
            }

            if (data.graph_paths && data.graph_paths.length > 0) {
                lastNeo4jPath = data.graph_paths[0];
                lastConfidence = data.confidence;
                renderNeo4jChain(data.graph_paths[0], data.confidence);
            } else {
                lastNeo4jPath = null;
                lastConfidence = null;
                renderNeo4jChain(null);
            }

            // Tự động đồng bộ dropdown hiển thị đúng máy AI đã nhận diện
            if (data.machine && machineSelect) {
                lastActiveMachine = data.machine;
                machineSelect.value = data.machine;
                updateActiveMachine();
            }

            saveChatState();

            // If Fail-Safe triggered, show emergency callout & refresh bell badge
            const calloutCard = document.getElementById('expert-callout-card');
            if (data.fail_safe) {
                if (calloutCard && data.assigned_expert) {
                    document.getElementById('callout-expert-name').innerText = data.assigned_expert.name;
                    document.getElementById('callout-expert-pos').innerText = data.assigned_expert.position;
                    document.getElementById('callout-action-link').href = `/expert/ticket/${data.ticket_id}/`;
                    calloutCard.style.display = 'block';
                }
                fetchNotifications();
            } else if (calloutCard) {
                calloutCard.style.display = 'none';
            }
        } else {
            appendMessage({
                role: 'ai',
                author: 'Lỗi Hệ Thống',
                text: `⚠️ Lỗi xử lý: ${data.error || 'Không xác định'}`,
                time: getCurrentTime()
            });
        }
    } catch (err) {
        const placeholder = document.getElementById(loadingId);
        if (placeholder) placeholder.remove();
        appendMessage({
            role: 'ai',
            author: 'Lỗi Kết Nối',
            text: `⚠️ Không thể kết nối tới máy chủ AI: ${err.message}`,
            time: getCurrentTime()
        });
    } finally {
        sendBtn.disabled = false;
        stream.scrollTop = stream.scrollHeight;
    }
}

function appendMessage({ role, author, text, failSafe, ticketId, confidence, time, isKnowledgeContribution, questionVariations }, saveToLocal = true) {
    const stream = document.getElementById('message-stream');
    if (!stream) return;

    if (saveToLocal) {
        chatHistory.push({ role, author, text, failSafe, ticketId, confidence, time, isKnowledgeContribution, questionVariations });
        if (chatHistory.length > 50) chatHistory.shift();
        saveChatState();
    }

    const msgDiv = document.createElement('div');
    msgDiv.className = `chat-msg ${role === 'user' ? 'user-msg' : 'ai-msg'}`;

    let variationsHtml = '';
    if (questionVariations && questionVariations.length > 0) {
        variationsHtml = `
            <div style="margin-top: 12px; padding: 12px; background: rgba(59, 130, 246, 0.08); border: 1px dashed var(--neon-cyan); border-radius: 8px;">
                <div style="font-size: 11.5px; font-weight: 700; color: var(--neon-cyan); margin-bottom: 8px; display: flex; align-items: center; gap: 6px;">
                    <span>⚡</span> 5 BIẾN THỂ CÂU HỎI HIỆN TRƯỜNG ĐÃ TỰ ĐỘNG TẠO & ĐỒNG BỘ VECTOR:
                </div>
                <div style="display: flex; flex-direction: column; gap: 6px;">
                    ${questionVariations.map(q => `
                        <div style="display: flex; justify-content: space-between; align-items: center; background: rgba(0,0,0,0.3); padding: 6px 10px; border-radius: 6px; gap: 8px;">
                            <span style="font-size: 12.5px; color: #e2e8f0;">🔹 <em>"${escapeHtml(q)}"</em></span>
                            <button type="button" onclick="testAskVariation('${escapeHtml(q).replace(/'/g, "\\'")}')" style="background: rgba(59, 130, 246, 0.2); border: 1px solid var(--neon-cyan); color: var(--neon-cyan); padding: 3px 8px; border-radius: 4px; font-size: 11px; font-weight: 700; cursor: pointer; white-space: nowrap;">
                                💬 Thử hỏi
                            </button>
                        </div>
                    `).join('')}
                </div>
            </div>
        `;
    }

    let badgeHtml = '';
    if (role === 'ai') {
        if (isKnowledgeContribution) {
            badgeHtml = `
                <div class="msg-footer">
                    <span class="msg-badge" style="background: var(--neon-emerald); color: #000; font-weight: 800;">
                        ✅ ĐÃ THIẾT LẬP ĐẦY ĐỦ QUAN HỆ NEO4J
                    </span>
                    <span class="msg-badge badge-neo4j">🔗 5 QUESTION VARIATIONS VECTORIZED</span>
                </div>
            `;
        } else if (failSafe) {
            badgeHtml = `
                <div class="msg-footer">
                    <span class="msg-badge" style="background: rgba(245, 158, 11, 0.2); color: var(--neon-amber); border: 1px solid var(--neon-amber);">
                        🛡️ FAIL-SAFE ACTIVATED (ĐỘ TIN CẬY < 85%)
                    </span>
                    <a href="/expert/ticket/${ticketId}/" class="msg-badge" style="background: var(--neon-amber); color: #000; text-decoration: none; font-weight: 800;">
                        MỞ PHIÊN CHUYÊN GIA ➔
                    </a>
                </div>
            `;
        } else {
            const confPct = confidence ? Math.round(confidence * 100) : 98;
            badgeHtml = `
                <div class="msg-footer">
                    <span class="msg-badge badge-neo4j">✅ NEO4J CAUSAL PATH VERIFIED (${confPct}%)</span>
                    <span class="msg-badge badge-bbox" style="background: rgba(59, 130, 246, 0.2); color: var(--neon-cyan); border-color: var(--neon-cyan);">📄 TRANG QUY CHUẨN XÁC MINH</span>
                </div>
            `;
        }
    }

    msgDiv.innerHTML = `
        <div class="msg-avatar">${role === 'user' ? '👷' : '🤖'}</div>
        <div class="msg-content">
            <div class="msg-header">
                <strong class="msg-author">${escapeHtml(author)}</strong>
                <span class="msg-time">${time}</span>
            </div>
            <div class="msg-body" style="white-space: pre-line;">${escapeHtml(text)}</div>
            ${variationsHtml}
            ${badgeHtml}
        </div>
    `;

    stream.appendChild(msgDiv);
    stream.scrollTop = stream.scrollHeight;
}

// ==============================================================================
// 3.0. MULTI-DOCUMENT RETRIEVAL & PILLS CAROUSEL
// ==============================================================================

let currentRelatedDocs = [];

function renderRelatedDocsPills(relatedDocs) {
    currentRelatedDocs = relatedDocs || [];
    const panel = document.getElementById('related-docs-panel');
    const pillsContainer = document.getElementById('related-docs-pills');
    const countEl = document.getElementById('related-docs-count');
    if (!panel || !pillsContainer) return;

    if (!relatedDocs || !Array.isArray(relatedDocs) || relatedDocs.length === 0) {
        panel.style.display = 'none';
        return;
    }

    if (countEl) countEl.textContent = relatedDocs.length;
    panel.style.display = 'block';

    pillsContainer.innerHTML = '';
    relatedDocs.forEach((doc, idx) => {
        const pill = document.createElement('div');
        pill.className = `related-doc-pill ${idx === 0 ? 'active' : ''}`;
        pill.id = `related-doc-pill-${idx}`;
        pill.onclick = () => selectRelatedDocument(idx);
        pill.innerHTML = `
            <span class="pill-badge">#${idx + 1}</span>
            <span class="pill-code">[${escapeHtml(doc.doc_code || 'SOP')}]</span>
            <span class="pill-title">${escapeHtml(doc.doc_title || 'Tài liệu')} (Trang ${doc.page_number || 1})</span>
            <span class="pill-score">${doc.relevance_pct || 85}% khớp</span>
        `;
        pillsContainer.appendChild(pill);
    });
}

function selectRelatedDocument(idx) {
    if (!currentRelatedDocs || !currentRelatedDocs[idx]) return;
    const doc = currentRelatedDocs[idx];

    document.querySelectorAll('.related-doc-pill').forEach((el, i) => {
        el.classList.toggle('active', i === idx);
    });

    renderVisualCanvas(doc);
}

function selectExpertSop(sopCode, snippetText) {
    const sopSelect = document.getElementById('expert-sop-select');
    if (sopSelect && sopCode) {
        sopSelect.value = sopCode;
    }
    if (snippetText) {
        applySuggestionToComposer(snippetText);
    }
}

// ==============================================================================
// 3. CANVAS BBOX & GRAPH RENDERING
// ==============================================================================

// Biến toàn cục lưu trữ căn cứ trang tài liệu hiện tại để mở Full Lightbox
let currentGrounding = null;
let lightboxZoom = 1.0;

function renderVisualCanvas(grounding) {
    currentGrounding = grounding;
    const standbyEl = document.getElementById('canvas-standby-state');
    const bannerEl = document.getElementById('page-indicator-banner');
    const imageContainer = document.getElementById('canvas-image-container');
    const textSnippet = document.getElementById('canvas-text-snippet');
    const badge = document.getElementById('canvas-sop-badge');

    if (!grounding) {
        if (standbyEl) standbyEl.style.display = 'flex';
        if (bannerEl) bannerEl.style.display = 'none';
        if (imageContainer) imageContainer.style.display = 'none';
        if (textSnippet) textSnippet.style.display = 'none';
        if (badge) badge.innerText = 'TRẠNG THÁI: CHỜ CÂU HỎI';
        return;
    }

    if (standbyEl) standbyEl.style.display = 'none';
    if (bannerEl) bannerEl.style.display = 'flex';
    if (imageContainer) imageContainer.style.display = 'flex';
    if (textSnippet) textSnippet.style.display = 'block';

    const docCodeEl = document.getElementById('page-indicator-doc-code');
    const pageNumEl = document.getElementById('page-indicator-num');
    const docTitleEl = document.getElementById('page-indicator-title');
    const pdfLinkEl = document.getElementById('link-download-pdf');
    const img = document.getElementById('canvas-img');
    const snippet = document.getElementById('canvas-snippet-body');

    const docCode = grounding.doc_code || 'SOP';
    const pageNum = grounding.page_number || 1;
    const docTitle = grounding.doc_title || 'Tài Liệu Tiêu Chuẩn Kỹ Thuật';

    if (badge) badge.innerText = `${docCode}: ${docTitle}`;
    if (docCodeEl) docCodeEl.innerText = docCode;
    if (pageNumEl) pageNumEl.innerText = `TRANG ${pageNum}`;
    if (docTitleEl) docTitleEl.innerText = docTitle;

    if (pdfLinkEl) {
        if (grounding.pdf_url) {
            pdfLinkEl.href = grounding.pdf_url;
            pdfLinkEl.style.display = 'inline-flex';
        } else {
            pdfLinkEl.style.display = 'none';
        }
    }

    if (snippet) {
        snippet.innerText = grounding.content || 'Đang đối chiếu dữ liệu quy chuẩn...';
    }

    if (img && grounding.image_url) {
        img.src = grounding.image_url;
    }
}

// ==============================================================================
// 3.1. FULL-PAGE LIGHTBOX VIEWER (ZOOMABLE & KHÔNG THIẾU NỘI DUNG)
// ==============================================================================

function openPageLightbox(initialTab = 'image') {
    if (!currentGrounding) return;
    const modal = document.getElementById('page-lightbox-modal');
    if (!modal) return;

    const titleEl = document.getElementById('lightbox-modal-title');
    const subtitleEl = document.getElementById('lightbox-modal-subtitle');
    const fullImg = document.getElementById('lightbox-full-img');
    const tabLink = document.getElementById('lightbox-open-tab-btn');
    const fullTextEl = document.getElementById('lightbox-full-text');

    const docCode = currentGrounding.doc_code || 'SOP';
    const pageNum = currentGrounding.page_number || 1;
    const docTitle = currentGrounding.doc_title || 'Tài Liệu Tiêu Chuẩn Kỹ Thuật';

    if (titleEl) titleEl.innerText = docTitle;
    if (subtitleEl) subtitleEl.innerText = `Mã tài liệu: ${docCode} • TRANG ${pageNum} (Bản Gốc Đầy Đủ Chất Lượng Cao)`;

    if (fullImg && currentGrounding.image_url) {
        fullImg.src = currentGrounding.image_url;
    }

    if (tabLink && currentGrounding.image_url) {
        tabLink.href = currentGrounding.image_url;
    }

    if (fullTextEl) {
        fullTextEl.innerText = currentGrounding.full_page_text || currentGrounding.content || 'Không có văn bản trích xuất.';
    }

    resetLightboxZoom();
    switchLightboxTab(initialTab);
    modal.style.display = 'flex';
}

function closePageLightbox() {
    const modal = document.getElementById('page-lightbox-modal');
    if (modal) modal.style.display = 'none';
}

function handleLightboxBackdropClick(event) {
    if (event.target && event.target.id === 'page-lightbox-modal') {
        closePageLightbox();
    }
}

function switchLightboxTab(tab) {
    const imgView = document.getElementById('lightbox-image-view');
    const txtView = document.getElementById('lightbox-text-view');
    const btnImg = document.getElementById('tab-btn-image');
    const btnTxt = document.getElementById('tab-btn-text');

    if (tab === 'text') {
        if (imgView) imgView.style.display = 'none';
        if (txtView) txtView.style.display = 'flex';
        if (btnImg) btnImg.classList.remove('active');
        if (btnTxt) btnTxt.classList.add('active');
    } else {
        if (imgView) imgView.style.display = 'flex';
        if (txtView) txtView.style.display = 'none';
        if (btnImg) btnImg.classList.add('active');
        if (btnTxt) btnTxt.classList.remove('active');
    }
}

function changeLightboxZoom(delta) {
    lightboxZoom = Math.min(3.0, Math.max(0.5, Math.round((lightboxZoom + delta) * 10) / 10));
    const fullImg = document.getElementById('lightbox-full-img');
    if (fullImg) {
        fullImg.style.transform = `scale(${lightboxZoom})`;
    }
}

function resetLightboxZoom() {
    lightboxZoom = 1.0;
    const fullImg = document.getElementById('lightbox-full-img');
    if (fullImg) {
        fullImg.style.transform = 'scale(1)';
    }
}

function copyFullPageText() {
    const textEl = document.getElementById('lightbox-full-text');
    if (textEl && textEl.innerText) {
        navigator.clipboard.writeText(textEl.innerText).then(() => {
            alert('📋 Đã sao chép toàn bộ văn bản của trang vào clipboard!');
        }).catch(() => {
            alert('Không thể sao chép văn bản.');
        });
    }
}

// Bắt phím Escape để đóng Lightbox
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        closePageLightbox();
    }
});

function renderNeo4jChain(path, confidence) {
    const chainCard = document.getElementById('neo4j-chain-card');
    if (!path) {
        if (chainCard) chainCard.style.display = 'none';
        return;
    }

    if (chainCard) chainCard.style.display = 'block';

    const mNode = document.getElementById('node-machine');
    const cNode = document.getElementById('node-component');
    const sNode = document.getElementById('node-symptom');
    const solNode = document.getElementById('node-solution');
    const confEl = document.getElementById('neo4j-chain-conf');

    if (mNode) mNode.innerText = path.machine || '---';
    if (cNode) cNode.innerText = path.component || '---';
    if (sNode) sNode.innerText = path.symptom ? (path.symptom.length > 35 ? path.symptom.substring(0, 35) + '...' : path.symptom) : '---';
    if (solNode) solNode.innerText = path.solution ? (path.solution.length > 35 ? path.solution.substring(0, 35) + '...' : path.solution) : '---';
    if (confEl && confidence) confEl.innerText = `${Math.round(confidence * 100)}% Verified`;
}

function handleImageFallback(img) {
    img.src = "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='800' height='600' viewBox='0 0 800 600' fill='%230f172a'><rect width='800' height='600' fill='%230b1120'/><text x='50%' y='45%' font-family='sans-serif' font-size='22' font-weight='bold' fill='%2338bdf8' text-anchor='middle'>SOP-023: BẢN VẼ TIÊU CHUẨN KỸ THUẬT</text><text x='50%' y='55%' font-family='sans-serif' font-size='16' fill='%2394a3b8' text-anchor='middle'>Mức rung trục chính máy M12 cho phép &lt; 2.5 mm/s RMS</text><rect x='100' y='320' width='600' height='120' fill='rgba(225,29,72,0.1)' stroke='%23e11d48' stroke-width='3' stroke-dasharray='6 3'/></svg>";
}

// ==============================================================================
// 4. EXPERT WORKSPACE: SUBMIT OFFICIAL ANSWER TO NEO4J
// ==============================================================================

function fillExpertConsult(text) {
    const input = document.getElementById('expert-consult-input');
    if (input) {
        input.value = text;
        input.focus();
    }
}

async function handleExpertConsultAI(event) {
    event.preventDefault();

    const ticketId = document.getElementById('expert-consult-ticket-id').value;
    const inputEl = document.getElementById('expert-consult-input');
    const expertName = (document.getElementById('expert-name-input') ? document.getElementById('expert-name-input').value : 'Chuyên gia Line Master').trim();
    const sendBtn = document.getElementById('btn-expert-consult');
    const stream = document.getElementById('expert-ai-stream');

    const query = inputEl ? inputEl.value.trim() : '';
    if (!query || !stream) return;

    // 1. Thêm tin nhắn câu hỏi của Chuyên gia vào stream
    const userTime = getCurrentTime();
    const expertMsgDiv = document.createElement('div');
    expertMsgDiv.className = 'chat-msg user-msg';
    expertMsgDiv.innerHTML = `
        <div class="msg-avatar" style="background: rgba(245, 158, 11, 0.2); border-color: var(--neon-amber);">👨‍🏭</div>
        <div class="msg-content" style="background: linear-gradient(135deg, #1e3a8a, #0f172a); border: 1px solid var(--neon-cyan);">
            <div class="msg-header">
                <strong class="msg-author" style="color: var(--neon-amber);">${escapeHtml(expertName)} (Chuyên gia hỏi AI)</strong>
                <span class="msg-time">${userTime}</span>
            </div>
            <div class="msg-body" style="white-space: pre-line;">${escapeHtml(query)}</div>
            <div class="msg-footer">
                <span class="msg-badge" style="background: rgba(245, 158, 11, 0.15); color: var(--neon-amber); border: 1px solid var(--neon-amber);">
                    ⚡ TRA CỨU TÀI LIỆU
                </span>
            </div>
        </div>
    `;
    stream.appendChild(expertMsgDiv);

    // Xóa input
    inputEl.value = '';
    sendBtn.disabled = true;

    // 2. Thêm placeholder loading
    const loadingId = 'ai-loading-' + Date.now();
    const loadingDiv = document.createElement('div');
    loadingDiv.id = loadingId;
    loadingDiv.className = 'chat-msg ai-msg';
    loadingDiv.innerHTML = `
        <div class="msg-avatar">🤖</div>
        <div class="msg-content">
            <div class="msg-header">
                <strong class="msg-author">Hệ thống AI Zero-Error Copilot</strong>
                <span class="msg-time">Đang tra cứu...</span>
            </div>
            <div class="msg-body" style="color: var(--neon-cyan); display: flex; align-items: center; gap: 8px;">
                <span class="loading-spinner">⚡</span> Đang đối soát Vector SOP & truy vết mắt xích Đồ thị Neo4j...
            </div>
        </div>
    `;
    stream.appendChild(loadingDiv);
    stream.scrollTop = stream.scrollHeight;

    try {
        const response = await fetch('/api/expert_consult/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                ticket_id: ticketId,
                query: query,
                expert_name: expertName
            })
        });

        const data = await response.json();
        const placeholder = document.getElementById(loadingId);
        if (placeholder) placeholder.remove();

        if (data.success) {
            const aiMsgDiv = document.createElement('div');
            aiMsgDiv.className = 'chat-msg ai-msg';

            let suggestionHtml = '';
            if (data.suggested_text) {
                const escapedSuggested = escapeHtml(data.suggested_text).replace(/'/g, "\\'");
                suggestionHtml = `
                    <div style="margin-top: 10px; padding: 10px; background: rgba(16, 185, 129, 0.1); border: 1px dashed var(--neon-emerald); border-radius: 6px;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                            <span style="font-size: 11px; font-weight: 700; color: var(--neon-emerald);">💡 ĐỀ XUẤT NỘI DUNG CHO CHUYÊN GIA:</span>
                            <button type="button" onclick="applySuggestionToComposer('${escapedSuggested}')" style="background: var(--neon-emerald); color: #000; border: none; padding: 4px 10px; border-radius: 4px; font-size: 11px; font-weight: 800; cursor: pointer;">
                                📋 Chèn vào ô trả lời
                            </button>
                        </div>
                        <div style="font-size: 12px; color: #cbd5e1; font-style: italic;">
                            "${escapeHtml(data.suggested_text)}"
                        </div>
                    </div>
                `;
            }

            let variationsHtml = '';
            if (data.question_variations && data.question_variations.length > 0) {
                variationsHtml = `
                    <div style="margin-top: 12px; padding: 12px; background: rgba(59, 130, 246, 0.08); border: 1px dashed var(--neon-cyan); border-radius: 8px;">
                        <div style="font-size: 11.5px; font-weight: 700; color: var(--neon-cyan); margin-bottom: 8px; display: flex; align-items: center; gap: 6px;">
                            <span>⚡</span> 5 BIẾN THỂ CÂU HỎI HIỆN TRƯỜNG ĐÃ TỰ ĐỘNG TẠO & ĐỒNG BỘ VECTOR:
                        </div>
                        <div style="display: flex; flex-direction: column; gap: 6px;">
                            ${data.question_variations.map(q => `
                                <div style="display: flex; justify-content: space-between; align-items: center; background: rgba(0,0,0,0.3); padding: 6px 10px; border-radius: 6px; gap: 8px;">
                                    <span style="font-size: 12.5px; color: #e2e8f0;">🔹 <em>"${escapeHtml(q)}"</em></span>
                                    <button type="button" onclick="testAskVariation('${escapeHtml(q).replace(/'/g, "\\'")}')" style="background: rgba(59, 130, 246, 0.2); border: 1px solid var(--neon-cyan); color: var(--neon-cyan); padding: 3px 8px; border-radius: 4px; font-size: 11px; font-weight: 700; cursor: pointer; white-space: nowrap;">
                                        💬 Thử hỏi
                                    </button>
                                </div>
                            `).join('')}
                        </div>
                    </div>
                `;
            }

            let footerHtml = '';
            if (data.is_knowledge_contribution) {
                footerHtml = `
                    <div class="msg-footer">
                        <span class="msg-badge" style="background: var(--neon-emerald); color: #000; font-weight: 800;">
                            ✅ ĐÃ THIẾT LẬP ĐẦY ĐỦ QUAN HỆ NEO4J
                        </span>
                        <span class="msg-badge badge-neo4j">🔗 5 QUESTION VARIATIONS VECTORIZED</span>
                    </div>
                `;
            } else {
                footerHtml = `
                    <div class="msg-footer">
                        <span class="msg-badge badge-neo4j">✅ NEO4J CAUSAL CHAIN</span>
                        <span class="msg-badge badge-bbox">📑 DẪN CHIẾU SOP</span>
                    </div>
                `;
            }

            aiMsgDiv.innerHTML = `
                <div class="msg-avatar">🤖</div>
                <div class="msg-content">
                    <div class="msg-header">
                        <strong class="msg-author">Hệ thống AI Zero-Error Copilot</strong>
                        <span class="msg-time">${data.created_at || getCurrentTime()}</span>
                    </div>
                    <div class="msg-body" style="white-space: pre-line;">${escapeHtml(data.answer_text || data.answer)}</div>
                    ${variationsHtml}
                    ${suggestionHtml}
                    ${footerHtml}
                </div>
            `;
            stream.appendChild(aiMsgDiv);
        } else {
            const errDiv = document.createElement('div');
            errDiv.className = 'chat-msg ai-msg';
            errDiv.innerHTML = `
                <div class="msg-avatar">⚠️</div>
                <div class="msg-content">
                    <div class="msg-header"><strong class="msg-author">Lỗi Hệ Thống</strong></div>
                    <div class="msg-body">${escapeHtml(data.error || 'Không thể tra cứu')}</div>
                </div>
            `;
            stream.appendChild(errDiv);
        }
    } catch (err) {
        const placeholder = document.getElementById(loadingId);
        if (placeholder) placeholder.remove();
        alert('Lỗi kết nối tới máy chủ AI: ' + err.message);
    } finally {
        sendBtn.disabled = false;
        stream.scrollTop = stream.scrollHeight;
    }
}

async function handleSubmitExpertAnswer(event) {
    event.preventDefault();

    const ticketId = document.getElementById('ticket-id').value;
    const answerText = document.getElementById('expert-answer-text').value.trim();
    const expertName = document.getElementById('expert-name-input').value.trim();
    const submitBtn = document.getElementById('btn-submit-expert');
    const sopSelect = document.getElementById('expert-sop-select');
    const sopCode = sopSelect ? sopSelect.value : '';
    const fileInput = document.getElementById('expert-upload-file');

    if (!answerText) return;

    // Button loading animation
    const originalText = submitBtn.innerHTML;
    submitBtn.innerHTML = `
        <span class="btn-icon">⚡</span>
        <span class="btn-text">ĐANG BÓC TÁCH ENTITIES & THỰC THI CYPHER MERGE VÀO NEO4J...</span>
    `;
    submitBtn.disabled = true;

    try {
        const formData = new FormData();
        formData.append('ticket_id', ticketId);
        formData.append('expert_answer', answerText);
        formData.append('expert_name', expertName);
        if (sopCode) {
            formData.append('sop_code', sopCode);
        }
        if (fileInput && fileInput.files && fileInput.files[0]) {
            formData.append('document_file', fileInput.files[0]);
        }

        const response = await fetch('/api/expert_answer/', {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        if (data.success) {
            // Reveal distillation card
            const distillCard = document.getElementById('distillation-result-card');
            if (distillCard) distillCard.style.display = 'block';

            const ent = data.extracted_entities;
            if (ent) {
                document.getElementById('ent-machine').innerText = ent.machine;
                document.getElementById('ent-component').innerText = ent.component;
                document.getElementById('ent-symptom').innerText = ent.symptom;
                document.getElementById('ent-root-cause').innerText = ent.root_cause;
                document.getElementById('ent-solution').innerText = ent.solution;
                document.getElementById('ent-sop').innerText = ent.sop_code;
                document.getElementById('ent-expert').innerText = expertName;
            }

            if (data.cypher) {
                document.getElementById('cypher-code-preview').innerText = data.cypher;
            }

            // Update banner status
            const statusBadge = document.getElementById('ticket-status-badge');
            if (statusBadge) {
                statusBadge.innerText = '✅ ĐÃ GIẢI ĐÁP & ĐỒNG BỘ NEO4J';
                statusBadge.style.color = 'var(--neon-emerald)';
            }

            // Thêm thẻ KẾT QUẢ GIẢI ĐÁP CHÍNH THỨC CỦA CHUYÊN GIA trực tiếp vào khung chat bên trái
            const stream = document.getElementById('expert-ai-stream');
            if (stream) {
                const resMsgDiv = document.createElement('div');
                resMsgDiv.className = 'chat-msg';
                resMsgDiv.style.width = '100%';
                resMsgDiv.style.maxWidth = '100%';
                resMsgDiv.innerHTML = `
                    <div class="msg-avatar" style="background: rgba(16, 185, 129, 0.25); border-color: var(--neon-emerald); font-size: 20px;">🎖️</div>
                    <div class="msg-content" style="background: linear-gradient(135deg, rgba(6, 78, 59, 0.5), rgba(17, 26, 46, 0.95)); border: 1.5px solid var(--neon-emerald); width: 100%;">
                        <div class="msg-header" style="border-bottom: 1px solid rgba(16, 185, 129, 0.3); padding-bottom: 6px; margin-bottom: 8px;">
                            <strong style="color: var(--neon-emerald); font-size: 13px;">👨‍🏭 ${escapeHtml(expertName)} — KẾT QUẢ GIẢI ĐÁP CHÍNH THỨC ĐÃ LƯU NEO4J</strong>
                            <span class="msg-time">${data.created_at || getCurrentTime()}</span>
                        </div>
                        <div class="msg-body" style="white-space: pre-line; color: #fff; font-size: 13.5px; line-height: 1.6;">${escapeHtml(answerText)}</div>
                        <div class="msg-footer" style="display: flex; gap: 8px; flex-wrap: wrap; margin-top: 10px; border-top: 1px dashed rgba(16, 185, 129, 0.3); padding-top: 8px;">
                            <span class="msg-badge" style="background: var(--neon-emerald); color: #000; font-weight: 800;">
                                ✅ ĐÃ KÝ DUYỆT & ĐỒNG BỘ ĐỒ THỊ NEO4J
                            </span>
                            <span class="msg-badge badge-neo4j">
                                🔗 DETERMINISTIC MERGE EXECUTED
                            </span>
                        </div>
                    </div>
                `;
                stream.appendChild(resMsgDiv);
                stream.scrollTop = stream.scrollHeight;
            }

            if (typeof fetchNotifications === 'function') {
                fetchNotifications();
            }

            submitBtn.innerHTML = `
                <span class="btn-icon">✅</span>
                <span class="btn-text">ĐÃ NẠP CHÍNH THỨC VÀO NEO4J GRAPH & HOÀN TẤT TICKET</span>
            `;
            submitBtn.style.background = 'linear-gradient(135deg, #10b981, #059669)';
        } else {
            alert(`Lỗi lưu vào Neo4j: ${data.error}`);
            submitBtn.innerHTML = originalText;
            submitBtn.disabled = false;
        }
    } catch (err) {
        alert(`Lỗi kết nối máy chủ: ${err.message}`);
        submitBtn.innerHTML = originalText;
        submitBtn.disabled = false;
    }
}

function applySuggestionToComposer(text) {
    const textarea = document.getElementById('expert-answer-text');
    if (textarea && text) {
        textarea.value = text;
        textarea.focus();
    }
}

function openKnowledgeModal(machineName) {
    const modal = document.getElementById('knowledge-modal');
    if (!modal) return;
    if (machineName) {
        const select = document.getElementById('contrib-machine');
        if (select) select.value = machineName;
    }
    modal.style.display = 'flex';
}

function closeKnowledgeModal() {
    const modal = document.getElementById('knowledge-modal');
    if (modal) modal.style.display = 'none';
}

function testAskVariation(questionText) {
    const qInput = document.getElementById('question-input') || document.getElementById('expert-consult-input');
    if (qInput) {
        qInput.value = questionText;
        qInput.focus();
        const form = qInput.closest('form');
        if (form) {
            form.dispatchEvent(new Event('submit', { cancelable: true }));
        }
    }
}

async function submitKnowledgeContribution(event) {
    event.preventDefault();
    const expertName = document.getElementById('contrib-expert-name').value.trim();
    const machine = document.getElementById('contrib-machine').value.trim();
    const knowledgeText = document.getElementById('contrib-knowledge-text').value.trim();
    const btn = document.getElementById('btn-submit-knowledge');

    if (!knowledgeText) return;

    const originalText = btn.innerHTML;
    btn.innerHTML = '<span>⚡ ĐANG BÓC TÁCH ENTITIES & TẠO 5 BIẾN THỂ CÂU HỎI...</span>';
    btn.disabled = true;

    try {
        const response = await fetch('/api/contribute_knowledge/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                expert_name: expertName,
                machine: machine,
                knowledge_text: knowledgeText
            })
        });

        const data = await response.json();
        closeKnowledgeModal();
        btn.innerHTML = originalText;
        btn.disabled = false;

        if (data.success) {
            // 1. Nếu đang ở màn hình Unified Chat (/chat/)
            const stream = document.getElementById('message-stream');
            if (stream) {
                // Thêm tin nhắn Chuyên gia nạp tri thức
                appendMessage({
                    role: 'user',
                    author: `${expertName} (Chuyên gia Đóng góp Tri thức)`,
                    text: `[Đóng góp tri thức mới cho ${machine}]:\n${knowledgeText}`,
                    time: getCurrentTime()
                });

                // Thêm tin nhắn AI phản hồi với 5 biến thể câu hỏi
                appendMessage({
                    role: 'ai',
                    author: 'Hệ thống AI Zero-Error Copilot',
                    text: data.answer_text || data.answer,
                    time: getCurrentTime(),
                    isKnowledgeContribution: true,
                    questionVariations: data.question_variations
                });

                // Cập nhật Causal Chain Live Visualizer
                if (data.graph_paths && data.graph_paths.length > 0) {
                    renderNeo4jChain(data.graph_paths[0], 0.98);
                }
            }

            // 2. Nếu đang ở màn hình Expert Workspace (/expert/ticket/<id>/)
            const expertStream = document.getElementById('expert-ai-stream');
            if (expertStream) {
                const userMsgDiv = document.createElement('div');
                userMsgDiv.className = 'chat-msg user-msg';
                userMsgDiv.innerHTML = `
                    <div class="msg-avatar" style="background: rgba(16, 185, 129, 0.2); border-color: var(--neon-emerald);">👨‍🏭</div>
                    <div class="msg-content" style="background: linear-gradient(135deg, rgba(6, 78, 59, 0.4), #0f172a); border: 1.5px solid var(--neon-emerald);">
                        <div class="msg-header">
                            <strong class="msg-author" style="color: var(--neon-emerald);">${escapeHtml(expertName)} (Đóng góp Tri thức Mới)</strong>
                            <span class="msg-time">${getCurrentTime()}</span>
                        </div>
                        <div class="msg-body" style="white-space: pre-line;">${escapeHtml(knowledgeText)}</div>
                        <div class="msg-footer">
                            <span class="msg-badge" style="background: rgba(16, 185, 129, 0.2); color: var(--neon-emerald); border: 1px solid var(--neon-emerald); font-weight: 700;">
                                💡 NẠP TRI THỨC KỸ THUẬT
                            </span>
                        </div>
                    </div>
                `;
                expertStream.appendChild(userMsgDiv);

                let variationsHtml = '';
                if (data.question_variations && data.question_variations.length > 0) {
                    variationsHtml = `
                        <div style="margin-top: 12px; padding: 12px; background: rgba(59, 130, 246, 0.08); border: 1px dashed var(--neon-cyan); border-radius: 8px;">
                            <div style="font-size: 11.5px; font-weight: 700; color: var(--neon-cyan); margin-bottom: 8px; display: flex; align-items: center; gap: 6px;">
                                <span>⚡</span> 5 BIẾN THỂ CÂU HỎI HIỆN TRƯỜNG ĐÃ TỰ ĐỘNG TẠO & ĐỒNG BỘ VECTOR:
                            </div>
                            <div style="display: flex; flex-direction: column; gap: 6px;">
                                ${data.question_variations.map(q => `
                                    <div style="display: flex; justify-content: space-between; align-items: center; background: rgba(0,0,0,0.3); padding: 6px 10px; border-radius: 6px; gap: 8px;">
                                        <span style="font-size: 12.5px; color: #e2e8f0;">🔹 <em>"${escapeHtml(q)}"</em></span>
                                        <button type="button" onclick="testAskVariation('${escapeHtml(q).replace(/'/g, "\\'")}')" style="background: rgba(59, 130, 246, 0.2); border: 1px solid var(--neon-cyan); color: var(--neon-cyan); padding: 3px 8px; border-radius: 4px; font-size: 11px; font-weight: 700; cursor: pointer; white-space: nowrap;">
                                            💬 Thử hỏi
                                        </button>
                                    </div>
                                `).join('')}
                            </div>
                        </div>
                    `;
                }

                const aiMsgDiv = document.createElement('div');
                aiMsgDiv.className = 'chat-msg ai-msg';
                aiMsgDiv.innerHTML = `
                    <div class="msg-avatar">🤖</div>
                    <div class="msg-content">
                        <div class="msg-header">
                            <strong class="msg-author">Hệ thống AI Zero-Error Copilot</strong>
                            <span class="msg-time">${getCurrentTime()}</span>
                        </div>
                        <div class="msg-body" style="white-space: pre-line;">${escapeHtml(data.answer_text || data.answer)}</div>
                        ${variationsHtml}
                        <div class="msg-footer">
                            <span class="msg-badge" style="background: var(--neon-emerald); color: #000; font-weight: 800;">
                                ✅ ĐÃ THIẾT LẬP ĐẦY ĐỦ QUAN HỆ NEO4J
                            </span>
                            <span class="msg-badge badge-neo4j">🔗 5 QUESTION VARIATIONS VECTORIZED</span>
                        </div>
                    </div>
                `;
                expertStream.appendChild(aiMsgDiv);
                expertStream.scrollTop = expertStream.scrollHeight;

                // Tự động gợi ý điền giải pháp vào textarea giải quyết ticket
                if (data.extracted_entities && data.extracted_entities.solution) {
                    const ansTextarea = document.getElementById('expert-answer-text');
                    if (ansTextarea && !ansTextarea.value.trim()) {
                        ansTextarea.value = data.extracted_entities.solution;
                    }
                }
            }

            alert('🎉 Tri thức mới đã được bóc tách và đồng bộ 100% vào Đồ thị Neo4j & CSDL Vector Qdrant!');
        } else {
            alert('⚠️ Lỗi: ' + (data.error || 'Không thể nạp tri thức'));
        }
    } catch (err) {
        btn.innerHTML = originalText;
        btn.disabled = false;
        alert('Lỗi kết nối tới máy chủ AI: ' + err.message);
    }
}

// ==============================================================================
// 5. UTILITY & HELPER FUNCTIONS
// ==============================================================================

function applyQuickPrompt(promptText, machineName) {
    const qInput = document.getElementById('question-input');
    const machineSelect = document.getElementById('machine-select');
    if (qInput) qInput.value = promptText;
    if (machineSelect && machineName) {
        machineSelect.value = machineName;
        updateActiveMachine();
    }
    const form = document.getElementById('chat-form');
    if (form) form.dispatchEvent(new Event('submit', { cancelable: true }));
}

function updateActiveMachine() {
    const select = document.getElementById('machine-select');
    const label = document.getElementById('active-machine-label');
    if (select && label) {
        label.innerText = `Thiết bị: ${select.value}`;
    }
}

function toggleExpertModal() {
    const modal = document.getElementById('expert-modal');
    if (!modal) return;
    modal.style.display = modal.style.display === 'flex' ? 'none' : 'flex';
}

function getCurrentTime() {
    const now = new Date();
    return `${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}`;
}

function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;')
              .replace(/</g, '&lt;')
              .replace(/>/g, '&gt;')
              .replace(/"/g, '&quot;')
              .replace(/'/g, '&#039;');
}

// ==============================================================================
// 6. CHAT SESSION PERSISTENCE (LOCALSTORAGE & ZERO-DATA-LOSS RECOVERY)
// ==============================================================================

function saveChatState() {
    try {
        localStorage.setItem('denso_chat_history', JSON.stringify({
            messages: chatHistory,
            lastGrounding: lastCanvasGrounding,
            lastPath: lastNeo4jPath,
            lastConfidence: lastConfidence,
            lastMachine: lastActiveMachine
        }));
    } catch (e) {
        console.warn('[LocalStorage Save Error]', e);
    }
}

function loadChatState() {
    // 1. Tự động cuộn xuống cuối luồng tin nhắn vừa được nạp từ CSDL Database SQLite
    const stream = document.getElementById('message-stream');
    if (stream) {
        setTimeout(() => {
            stream.scrollTop = stream.scrollHeight;
        }, 100);
    }
    const expertStream = document.getElementById('expert-ai-stream');
    if (expertStream) {
        setTimeout(() => {
            expertStream.scrollTop = expertStream.scrollHeight;
        }, 100);
    }

    // 2. Khôi phục trạng thái bản vẽ BBox, danh sách tài liệu và nhánh Neo4j từ CSDL Database SQLite
    if (window.INITIAL_DB_GROUNDING) {
        renderVisualCanvas(window.INITIAL_DB_GROUNDING);
    }
    if (window.INITIAL_DB_RELATED_DOCS && window.INITIAL_DB_RELATED_DOCS.length > 0) {
        renderRelatedDocsPills(window.INITIAL_DB_RELATED_DOCS);
    }
    if (window.INITIAL_DB_GRAPH) {
        renderNeo4jChain(window.INITIAL_DB_GRAPH, window.INITIAL_DB_CONFIDENCE);
    }
    if (window.INITIAL_DB_MACHINE) {
        const select = document.getElementById('machine-select');
        if (select) {
            select.value = window.INITIAL_DB_MACHINE;
            updateActiveMachine();
        }
    }
}

async function clearChatHistory() {
    if (!confirm('Bạn có chắc chắn muốn xóa toàn bộ lịch sử đoạn chat trong CSDL để bắt đầu phiên mới?')) return;
    try {
        await fetch('/api/clear_chat_history/', { method: 'POST' });
        localStorage.removeItem('denso_chat_history');
        window.location.reload();
    } catch (e) {
        console.warn('[Clear Chat Error]', e);
        window.location.reload();
    }
}

