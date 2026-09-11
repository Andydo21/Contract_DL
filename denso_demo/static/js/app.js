// DENSO Factory Memory Frontend Logic (Vanilla JS)

let currentGeneratedRuleId = null;

function setDemoQuery(step) {
  const input = document.getElementById('chat-input');
  if (!input) return;

  if (step === 1) {
    input.value = "Quy chuẩn độ rung trục chính máy M12 là bao nhiêu?";
  } else if (step === 2) {
    input.value = "Máy M12 bị rung giật khi nhiệt độ xưởng lên 45°C, có nên thay bearing ngay không?";
  } else if (step === 3) {
    input.value = "Nhiệt độ 45°C máy M12 rung thì xử lý thế nào?";
  }
  input.focus();
}

async function sendMessage() {
  const input = document.getElementById('chat-input');
  const chatHistory = document.getElementById('chat-history');
  const btnSend = document.getElementById('btn-send');
  if (!input || !chatHistory) return;

  const text = input.value.trim();
  if (!text) return;

  // 1. Render user message
  const userRow = document.createElement('div');
  userRow.className = 'message-row user';
  userRow.innerHTML = `
    <div class="message-avatar">E</div>
    <div class="message-bubble">${escapeHtml(text)}</div>
  `;
  chatHistory.appendChild(userRow);
  input.value = '';
  chatHistory.scrollTop = chatHistory.scrollHeight;

  // 2. Loading state
  btnSend.disabled = true;
  const loadingRow = document.createElement('div');
  loadingRow.className = 'message-row assistant';
  loadingRow.id = 'loading-bubble';
  loadingRow.innerHTML = `
    <div class="message-avatar">D</div>
    <div class="message-bubble" style="color: var(--text-muted);">
      <em>Đang tra cứu kho tài liệu SOP, ca sự cố CBR và đồ thị tri thức Neo4j...</em>
    </div>
  `;
  chatHistory.appendChild(loadingRow);
  chatHistory.scrollTop = chatHistory.scrollHeight;

  try {
    const response = await fetch('/api/chat/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: text })
    });

    const rawText = await response.text();
    let data;
    try {
      data = JSON.parse(rawText);
    } catch (parseErr) {
      throw new Error(`Máy chủ trả về phản hồi không hợp lệ (${response.status}): ${rawText.slice(0, 80)}`);
    }

    // Remove loading
    const loadingElem = document.getElementById('loading-bubble');
    if (loadingElem) loadingElem.remove();

    // 3. Render Assistant Response
    const botRow = document.createElement('div');
    botRow.className = 'message-row assistant';

    let contentHtml = '';

    if (data.has_gap) {
      // ⚠️ KNOWLEDGE GAP DETECTED BANNER
      const exp = data.recommended_expert || { id: 1, name: 'Kỹ sư Nguyễn Văn A', cases_count: 14 };
      const refinedText = data.refined_question || text;

      // Lưu an toàn payload phỏng vấn vào JS context, tránh lỗi escape quote trong inline HTML
      window.latestGapData = {
        expert_id: exp.id,
        topic: text,
        refined_question: refinedText
      };

      contentHtml = `
        <div class="message-bubble" style="border-color: rgba(239, 68, 68, 0.5);">
          ${marked.parse(data.answer || '')}
          
          <!-- Box hiển thị câu hỏi đã được AI tinh chỉnh chuẩn hóa -->
          <div style="margin-top: 14px; background: rgba(37, 99, 235, 0.12); border: 1px solid rgba(59, 130, 246, 0.4); border-radius: 8px; padding: 12px;">
            <div style="font-size: 11px; font-weight: 700; color: #60a5fa; margin-bottom: 6px; display: flex; align-items: center; gap: 6px;">
              <span>🔄 AI ĐÃ TINH CHỈNH CÂU HỎI THÀNH CÂU HỎI PHỎNG VẤN CHUYÊN NGHIỆP:</span>
            </div>
            <div style="font-size: 13px; color: #e5e7eb; line-height: 1.5; font-style: italic; background: rgba(0,0,0,0.25); padding: 8px 12px; border-radius: 6px;">
              "${escapeHtml(refinedText)}"
            </div>
          </div>

          <div class="gap-alert" style="margin-top: 12px;">
            <div class="gap-header">
              <span>⚠️ ĐỀ XUẤT CHUYÊN GIA DÂY CHUYỀN PHÙ HỢP NHẤT</span>
            </div>
            <div class="gap-body">
              ${data.gap_reason || 'Không tìm thấy quy chuẩn chính thức trong kho SOP.'}
            </div>
            <div class="gap-expert-card">
              <div class="expert-info">
                <div class="expert-avatar-sm">${exp.name.slice(exp.name.lastIndexOf(' ') + 1)[0] || 'A'}</div>
                <div>
                  <div class="expert-name">${exp.name}</div>
                  <div class="expert-sub">${exp.position || 'Senior Line Master'} • <strong>${exp.cases_count} ca sự cố</strong> đã xử lý</div>
                </div>
              </div>
              <button class="btn-action" id="btn-trigger-gap-itw" onclick="startInterviewFromCurrentGap(this)">
                📨 Gửi câu hỏi phỏng vấn đến Chuyên gia ➔
              </button>
            </div>
          </div>
        </div>
      `;
    } else {
      // Normal or Approved Rule response
      let citationsHtml = '';
      if (data.citations && data.citations.length > 0) {
        citationsHtml = `
          <div style="margin-top: 12px; padding-top: 8px; border-top: 1px solid var(--border-subtle); display: flex; flex-wrap: wrap; gap: 8px;">
            ${data.citations.map(c => `
              <span class="badge" style="background: rgba(37, 99, 235, 0.2); color: #60a5fa;">
                📌 ${c.title || c} (${c.type || 'SOP'})
              </span>
            `).join('')}
          </div>
        `;
      }

      contentHtml = `
        <div class="message-bubble">
          ${marked.parse(data.answer || '')}
          ${citationsHtml}
        </div>
      `;
    }

    botRow.innerHTML = `
      <div class="message-avatar">D</div>
      ${contentHtml}
    `;
    chatHistory.appendChild(botRow);
    chatHistory.scrollTop = chatHistory.scrollHeight;

  } catch (err) {
    console.error(err);
    const loadingElem = document.getElementById('loading-bubble');
    if (loadingElem) loadingElem.remove();

    const errRow = document.createElement('div');
    errRow.className = 'message-row assistant';
    errRow.innerHTML = `
      <div class="message-avatar">D</div>
      <div class="message-bubble" style="color: #f87171;">
        Có lỗi xảy ra khi kết nối máy chủ: ${err.message}
      </div>
    `;
    chatHistory.appendChild(errRow);
  } finally {
    btnSend.disabled = false;
  }
}

async function startInterviewFromCurrentGap(btn) {
  if (!window.latestGapData) {
    alert("Không tìm thấy thông tin phiên phỏng vấn!");
    return;
  }
  if (btn) {
    btn.disabled = true;
    btn.innerText = "⏳ Đang kết nối Chuyên gia...";
  }
  try {
    const res = await fetch('/api/interviews/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(window.latestGapData)
    });
    const data = await res.json();
    if (data.success && data.redirect_url) {
      window.location.href = data.redirect_url;
    } else {
      alert("Lỗi tạo phỏng vấn: " + (data.error || 'Vui lòng thử lại'));
      if (btn) btn.disabled = false;
    }
  } catch (e) {
    alert("Lỗi kết nối: " + e.message);
    if (btn) btn.disabled = false;
  }
}

async function startInterviewFromGap(expertId, rawQuestion, refinedQuestion) {
  try {
    const res = await fetch('/api/interviews/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        expert_id: expertId,
        topic: rawQuestion,
        refined_question: refinedQuestion
      })
    });
    const data = await res.json();
    if (data.success && data.redirect_url) {
      window.location.href = data.redirect_url;
    }
  } catch (e) {
    alert("Lỗi tạo phỏng vấn: " + e.message);
  }
}

async function startInterviewWithExpert(expertId, expertName) {
  try {
    const res = await fetch('/api/interviews/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        expert_id: expertId,
        topic: `Kinh nghiệm bảo dưỡng và chuẩn đoán dung sai thiết bị gia công chính xác`
      })
    });
    const data = await res.json();
    if (data.success && data.redirect_url) {
      window.location.href = data.redirect_url;
    }
  } catch (e) {
    alert("Lỗi: " + e.message);
  }
}

async function submitExpertReply(interviewId, expertName) {
  const input = document.getElementById('expert-reply-text');
  const btn = document.getElementById('btn-expert-reply');
  const status = document.getElementById('ai-reply-status');
  const container = document.getElementById('interview-messages');

  const text = (input ? input.value : '').trim();
  if (!text) {
    alert("Vui lòng nhập nội dung câu trả lời của chuyên gia!");
    return;
  }

  // 1. Thêm tin nhắn của Chuyên gia vào giao diện ngay lập tức
  const expertMsgHtml = `
    <div style="display: flex; gap: 12px; align-items: flex-start;">
      <div style="width: 32px; height: 32px; border-radius: 6px; display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 12px; flex-shrink: 0; background: #2563eb; color: #fff;">
        EXP
      </div>
      <div style="flex: 1; background: var(--bg-card); border: 1px solid var(--border-subtle); padding: 12px 16px; border-radius: 8px; font-size: 13px; line-height: 1.6;">
        <strong>${escapeHtml(expertName)}:</strong>
        <div style="margin-top: 4px; white-space: pre-wrap;">${escapeHtml(text)}</div>
      </div>
    </div>
  `;
  if (container) {
    container.insertAdjacentHTML('beforeend', expertMsgHtml);
  }

  // Reset input & bật trạng thái loading
  input.value = '';
  if (btn) btn.disabled = true;
  if (status) status.style.display = 'flex';

  try {
    const res = await fetch(`/api/interviews/${interviewId}/reply/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text })
    });
    const data = await res.json();

    if (data.success && data.ai_question) {
      // 2. Thêm câu hỏi Socratic phản biện của AI vào biên bản
      const aiMsgHtml = `
        <div style="display: flex; gap: 12px; align-items: flex-start;">
          <div style="width: 32px; height: 32px; border-radius: 6px; display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 12px; flex-shrink: 0; background: var(--accent-red); color: #fff;">
            AI
          </div>
          <div style="flex: 1; background: var(--bg-card); border: 1px solid var(--border-subtle); padding: 12px 16px; border-radius: 8px; font-size: 13px; line-height: 1.6;">
            <strong>Trợ lý AI Interviewer:</strong>
            <div style="margin-top: 4px; white-space: pre-wrap;">${escapeHtml(data.ai_question)}</div>
          </div>
        </div>
      `;
      if (container) {
        container.insertAdjacentHTML('beforeend', aiMsgHtml);
        container.scrollIntoView({ behavior: 'smooth', block: 'end' });
      }
    } else {
      alert("Lỗi: " + (data.error || 'Không nhận được câu hỏi từ AI'));
    }
  } catch (err) {
    alert("Lỗi gửi phản hồi: " + err.message);
  } finally {
    if (btn) btn.disabled = false;
    if (status) status.style.display = 'none';
  }
}

async function generateRule(interviewId) {
  const btn = document.getElementById('btn-gen-rule');
  if (btn) {
    btn.disabled = true;
    btn.innerText = "⏳ Đang trích xuất...";
  }

  try {
    const res = await fetch(`/api/interviews/${interviewId}/generate-knowledge/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    });
    const data = await res.json();

    if (data.success) {
      currentGeneratedRuleId = data.rule_id;
      const box = document.getElementById('rule-result-box');
      if (box) {
        box.style.display = 'block';
        document.getElementById('rule-code-display').innerText = data.knowledge_code;
        document.getElementById('rule-title-display').innerText = data.title;
        document.getElementById('rule-content-display').innerText = data.content;
        document.getElementById('rule-confidence-display').innerText = `Độ tin cậy: ${Math.round(data.confidence * 100)}%`;
      }
    }
  } catch (e) {
    alert("Lỗi trích xuất tri thức: " + e.message);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerText = "✨ Tạo Tri thức Mới (K-102)";
    }
  }
}

async function approveRule() {
  if (!currentGeneratedRuleId) {
    alert("Vui lòng tạo quy tắc trước khi phê duyệt!");
    return;
  }

  const btnApprove = document.getElementById('btn-approve');
  if (btnApprove) btnApprove.disabled = true;

  try {
    const res = await fetch(`/api/knowledge/${currentGeneratedRuleId}/approve/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    });
    const data = await res.json();

    if (data.success) {
      const badge = document.getElementById('rule-status-badge');
      if (badge) {
        badge.className = 'badge badge-approved';
        badge.innerText = 'APPROVED (ACTIVE)';
      }
      document.getElementById('approve-action-row').style.display = 'none';
      document.getElementById('approve-success-banner').style.display = 'block';
    }
  } catch (e) {
    alert("Lỗi duyệt quy tắc: " + e.message);
    if (btnApprove) btnApprove.disabled = false;
  }
}

function escapeHtml(text) {
  const map = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#039;'
  };
  return text.replace(/[&<>"']/g, m => map[m]);
}
