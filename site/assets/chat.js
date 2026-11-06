const API_URL = (typeof window !== 'undefined' && window.location && window.location.protocol.startsWith('http'))
  ? '/chat'
  : 'http://127.0.0.1:8000/chat';

const launcher = document.getElementById('chat-launcher');
const panel = document.getElementById('chat-panel');
const closeBtn = document.getElementById('chat-close');
const body = document.getElementById('chat-body');
const form = document.getElementById('chat-form');
const input = document.getElementById('chat-input');

let chatHistory = [];
let inspectorEl = null;
let currentInspectorData = null;
let currentInspectorTab = 'workflow';
let selectedModel = localStorage.getItem('chat_model') || 'cloud';
// Reset conversation memory on page load/refresh so each page visit or reload starts 100% fresh.
let conversationId = null;
try {
  const staleId = sessionStorage.getItem('chat_conversation_id') || localStorage.getItem('chat_conversation_id');
  sessionStorage.removeItem('chat_conversation_id');
  localStorage.removeItem('chat_conversation_id');
  if (staleId) {
    fetch('/chat/reset', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ conversation_id: staleId }),
    }).catch(() => {});
  }
} catch (_) {}

// Send beacon on page unload/refresh to guarantee backend session memory is wiped
window.addEventListener('beforeunload', () => {
  if (conversationId) {
    try {
      sessionStorage.removeItem('chat_conversation_id');
      localStorage.removeItem('chat_conversation_id');
      const payload = JSON.stringify({ conversation_id: conversationId });
      if (navigator.sendBeacon) {
        navigator.sendBeacon('/chat/reset', new Blob([payload], { type: 'application/json' }));
      } else {
        fetch('/chat/reset', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: payload,
          keepalive: true,
        }).catch(() => {});
      }
    } catch (_) {}
  }
});

/* ---------- Header Action Buttons (New Chat, Expand, Close) ---------- */
const NEW_CHAT_ICON = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14"></path></svg>';
const EXPAND_ICON = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M8 3H5a2 2 0 0 0-2 2v3M16 3h3a2 2 0 0 1 2 2v3M21 16v3a2 2 0 0 1-2 2h-3M8 21H5a2 2 0 0 1-2-2v-3"></path></svg>';
const COLLAPSE_ICON = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 3v4a1 1 0 0 1-1 1H4M20 8h-4a1 1 0 0 1-1-1V3M3 16h4a1 1 0 0 1 1 1v4M15 20v-4a1 1 0 0 1 1-1h4"></path></svg>';

let isExpanded = false;
let newChatBtn = null;
let expandBtn = null;
let chatBackdrop = null;

function newChatTitle() {
  const isAr = getLang() === 'ar';
  return isAr ? 'محادثة جديدة' : 'New Chat';
}

function expandTitle() {
  const isAr = getLang() === 'ar';
  return isExpanded
    ? (isAr ? 'تصغير الشات' : 'Collapse chat')
    : (isAr ? 'تكبير الشات' : 'Expand chat');
}

function setExpanded(next) {
  if (!panel) return;
  isExpanded = next;
  panel.classList.toggle('chat-expanded', isExpanded);
  if (chatBackdrop) chatBackdrop.classList.toggle('open', isExpanded);
  if (expandBtn) {
    expandBtn.innerHTML = isExpanded ? COLLAPSE_ICON : EXPAND_ICON;
    expandBtn.setAttribute('aria-label', expandTitle());
    expandBtn.title = expandTitle();
  }
}

function startNewChat() {
  const oldId = conversationId;
  conversationId = null;
  try {
    sessionStorage.removeItem('chat_conversation_id');
    localStorage.removeItem('chat_conversation_id');
  } catch (_) {}

  chatHistory = [];

  if (body) {
    const isAr = getLang() === 'ar';
    const greetingText = isAr
      ? 'أهلاً بك! تم بدء محادثة جديدة 👋 اسألني عن أي باقة أو خدمة في اتصالات مصر.'
      : "Hi! Started a fresh conversation 👋 Ask me about any e& Egypt package or service.";
    body.innerHTML = `<div class="msg bot" data-i18n="chat.greeting">${greetingText}</div>`;
  }

  if (typeof closeInspector === 'function') {
    closeInspector();
  }

  if (oldId) {
    fetch('/chat/reset', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ conversation_id: oldId }),
    }).catch(() => {});
  }

  if (input) {
    input.value = '';
    input.focus();
  }
}

function initHeaderActions() {
  if (!panel) return;
  const head = panel.querySelector('.chat-head');
  const closeButton = document.getElementById('chat-close');

  if (typeof document !== 'undefined' && document.body && document.body.classList.contains('chatbot-page')) {
    if (closeButton) closeButton.style.display = 'none';
    if (!newChatBtn && head) {
      newChatBtn = document.createElement('button');
      newChatBtn.type = 'button';
      newChatBtn.id = 'chat-new';
      newChatBtn.innerHTML = NEW_CHAT_ICON;
      newChatBtn.setAttribute('aria-label', newChatTitle());
      newChatBtn.title = newChatTitle();
      head.appendChild(newChatBtn);
      newChatBtn.addEventListener('click', (e) => {
        e.preventDefault();
        startNewChat();
      });
    }
    return;
  }

  if (!head || !closeButton) return;

  if (!newChatBtn) {
    newChatBtn = document.createElement('button');
    newChatBtn.type = 'button';
    newChatBtn.id = 'chat-new';
    newChatBtn.innerHTML = NEW_CHAT_ICON;
    newChatBtn.setAttribute('aria-label', newChatTitle());
    newChatBtn.title = newChatTitle();
    head.insertBefore(newChatBtn, closeButton);

    newChatBtn.addEventListener('click', (e) => {
      e.preventDefault();
      startNewChat();
    });
  }

  if (!expandBtn) {
    expandBtn = document.createElement('button');
    expandBtn.type = 'button';
    expandBtn.id = 'chat-expand';
    expandBtn.innerHTML = EXPAND_ICON;
    expandBtn.setAttribute('aria-label', expandTitle());
    expandBtn.title = expandTitle();
    head.insertBefore(expandBtn, closeButton);

    expandBtn.addEventListener('click', (e) => {
      e.preventDefault();
      setExpanded(!isExpanded);
    });
  }

  if (!chatBackdrop) {
    chatBackdrop = document.createElement('div');
    chatBackdrop.id = 'chat-backdrop';
    document.body.appendChild(chatBackdrop);
    chatBackdrop.addEventListener('click', () => setExpanded(false));
  }
}

function initExpandToggle() {
  initHeaderActions();
}

function initModelSelector() {
  const modelBtns = document.querySelectorAll('.model-btn');
  if (!modelBtns.length) return;

  modelBtns.forEach((btn) => {
    const model = btn.getAttribute('data-model');
    btn.classList.toggle('active', model === selectedModel);

    if (!btn._modelBound) {
      btn._modelBound = true;
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        selectedModel = model;
        try {
          localStorage.setItem('chat_model', selectedModel);
        } catch (_) {}
        document.querySelectorAll('.model-btn').forEach((b) => {
          b.classList.toggle('active', b.getAttribute('data-model') === selectedModel);
        });
      });
    }
  });
}

// Initialize immediately and on DOM load
if (typeof document !== 'undefined') {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initModelSelector);
  } else {
    initModelSelector();
  }
}

function getLang() {
  return document.documentElement.getAttribute('lang') || 'en';
}

function currentDict() {
  const lang = getLang();
  if (typeof translations !== 'undefined' && translations[lang]) {
    return translations[lang];
  }

  return {
    'chat.noAnswer': "I couldn't find an answer to that, could you rephrase it?",
    'chat.offline': "The chatbot isn't connected right now. Start the server, then try again.",
    'chat.btnWorkflow': "Workflow",
    'chat.btnSources': "Sources",
    'chat.confidence': "Confidence",
    'chat.modalWorkflowTitle': "Agentic RAG Pipeline Workflow",
    'chat.modalSourcesTitle': "Verified Knowledge Citations",
    'chat.noSources': "No external document retrieval was required for this response.",
    'chat.page': "Page",
    'chat.category': "Category",
    'chat.product': "Product",
    'chat.snippet': "Verified Context Snippet",
    'chat.pipelineTitle': "Pipeline Flowchart",
    'chat.stepsTitle': "Step-by-Step Execution Trace",
    'chat.close': "Close",
  };
}

function formatDuration(ms, isAr = false) {
  if (ms === undefined || ms === null || isNaN(ms)) return '';
  if (ms < 1000) {
    return isAr ? `${ms} مللي ثانية` : `${ms}ms`;
  }
  const sec = (ms / 1000).toFixed(2);
  return isAr ? `${sec} ثانية` : `${sec}s`;
}

function formatDurationCompact(ms) {
  if (ms === undefined || ms === null || isNaN(ms)) return '';
  if (ms < 1000) {
    return `${ms}ms`;
  }
  return `${(ms / 1000).toFixed(2)}s`;
}

const GRAPH_NODE_META = {
  input_guard:     { icon: '🛡️', labelEn: 'Input Guardrail',       labelAr: 'حارس المدخلات والأمان', color: '#EF4444' },
  intent:          { icon: '🎯', labelEn: 'Intent Classifier',     labelAr: 'تصنيف النية والتوجيه',  color: '#06B6D4' },
  greeting:        { icon: '⚡', labelEn: 'Fast Greeting',         labelAr: 'رد ترحيبي فوري',       color: '#F59E0B' },
  safe_response:   { icon: '🛑', labelEn: 'Safe Response',         labelAr: 'المسار والرد الآمن',   color: '#F43F5E' },
  understand:      { icon: '🧠', labelEn: 'Query Understanding',   labelAr: 'تحليل وتنميط الاستفسار',color: '#818CF8' },
  strategy_router: { icon: '🧭', labelEn: 'Strategy Router',       labelAr: 'موجه الاستراتيجية',     color: '#A855F7' },
  clarify:         { icon: '❓', labelEn: 'Device Clarification', labelAr: 'توضيح نوع الجهاز',     color: '#F59E0B' },
  mcp_tool:        { icon: '🛠️', labelEn: 'Deterministic Tools',   labelAr: 'الحقيقة المؤكدة',       color: '#FB923C' },
  query_rewrite:   { icon: '🔄', labelEn: 'Query Rewrite',        labelAr: 'إعادة صياغة الاستعلام', color: '#0EA5E9' },
  retrieve:        { icon: '🔍', labelEn: 'Hybrid Retrieval',      labelAr: 'استرجاع هجين متوازي',   color: '#10B981' },
  generate:        { icon: '✍️', labelEn: 'Grounded Generation',   labelAr: 'توليد الإجابة الصارمة', color: '#C084FC' },
  validate:        { icon: '⚖️', labelEn: 'Fact Validator',        labelAr: 'فحص وتدقيق الحقائق',   color: '#2DD4BF' },
  output_guard:    { icon: '🔒', labelEn: 'Output Guardrail',      labelAr: 'حارس المخرجات والتنقيح',color: '#60A5FA' },
};

function isArabicText(str) {
  if (!str) return false;

  const arabicMatches = str.match(/[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]/g);
  const arabicCount = arabicMatches ? arabicMatches.length : 0;
  const latinMatches = str.match(/[a-zA-Z]/g);
  const latinCount = latinMatches ? latinMatches.length : 0;

  if (arabicCount === 0) return false;
  if (latinCount === 0) return true;

  return arabicCount > latinCount;
}

function decodeHtmlEntities(text) {
  const str = String(text || '');

  if (typeof document === 'undefined' || !document.createElement) {
    return str
      .replace(/&#x([0-9a-f]+);/gi, (_, hex) => String.fromCharCode(parseInt(hex, 16)))
      .replace(/&#(\d+);/g, (_, num) => String.fromCharCode(parseInt(num, 10)))
      .replace(/&lt;/gi, '<')
      .replace(/&gt;/gi, '>')
      .replace(/&amp;/gi, '&')
      .replace(/&quot;/gi, '"')
      .replace(/&#39;/g, "'");
  }

  const textarea = document.createElement('textarea');
  textarea.innerHTML = str;
  return textarea.value;
}

function normalizeEscapedHtml(text) {
  let str = String(text || '');

  for (let i = 0; i < 3; i += 1) {
    const previous = str;
    str = decodeHtmlEntities(str);
    str = str.replace(/\\+([<>])/g, '$1');
    str = str.replace(/<\\+\//g, '</');

    if (str === previous) break;
  }

  return str;
}

function cleanBotText(text) {
  let str = normalizeEscapedHtml(text);

  str = str.replace(/<\s*br\s*\/?\s*>/gi, '\n');
  str = str.replace(/<\s*li\b[^>]*>/gi, '\n- ');
  str = str.replace(/<\/\s*li\s*>/gi, '');
  str = str.replace(/<\/?\s*(ul|ol)\b[^>]*>/gi, '\n');
  str = str.replace(/<\/\s*(p|div|section|article|tr)\s*>/gi, '\n');
  str = str.replace(/<\s*(p|div|section|article|tr)\b[^>]*>/gi, '');
  str = str.replace(/<\/?\s*(strong|b|em|i|span|code|table|thead|tbody|th|td)\b[^>]*>/gi, '');
  str = str.replace(/<\/?\s*[a-zA-Z][^>]*>/g, '');
  str = str.replace(/[ \t]+\n/g, '\n');
  str = str.replace(/\n{3,}/g, '\n\n');
  str = str.replace(/[ \t]{2,}/g, ' ');

  return str.trim();
}

function escapeHtml(str) {
  return String(str || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function formatInlineMarkdown(text) {
  if (!text) return '';
  let s = escapeHtml(text);

  // 1. Backtick code: `*319*80#` or `code`
  const codeBlocks = [];
  s = s.replace(/`([^`]+)`/g, (_, code) => {
    codeBlocks.push(`<code class="chat-code-chip" dir="ltr">${code}</code>`);
    return `___CODE_${codeBlocks.length - 1}___`;
  });

  // 2. Standalone USSD codes like *319*80# or *858#
  s = s.replace(/(?<![>\w*])(\*[\d*#]{2,}#)(?![<\w*])/g, (_, ussd) => {
    codeBlocks.push(`<code class="chat-code-chip ussd-chip" dir="ltr">${ussd}</code>`);
    return `___CODE_${codeBlocks.length - 1}___`;
  });

  // 3. Bold: **text**
  s = s.replace(/\*\*([^*]+)\*\*/g, '<strong class="chat-bold">$1</strong>');

  // 4. Italic: *text* (letters only, avoiding numbers/symbols)
  s = s.replace(/(?<![\w*])\*([a-zA-Z\u0600-\u06FF\s]+)\*(?![\w*])/g, '<em>$1</em>');

  // Restore code blocks
  s = s.replace(/___CODE_(\d+)___/g, (_, idx) => codeBlocks[Number(idx)]);

  return s;
}

function renderMarkdown(rawText) {
  if (!rawText) return '';
  let str = normalizeEscapedHtml(rawText);
  str = str.replace(/\r\n/g, '\n').replace(/\r/g, '\n');

  const lines = str.split('\n');
  const blocks = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];
    const trimmed = line.trim();

    if (!trimmed) {
      i++;
      continue;
    }

    // A. Markdown Tables: rows starting and ending with '|'
    if (trimmed.startsWith('|') && trimmed.endsWith('|') && (trimmed.match(/\|/g) || []).length >= 2) {
      const tableLines = [];
      while (i < lines.length && lines[i].trim().startsWith('|') && lines[i].trim().endsWith('|')) {
        tableLines.push(lines[i].trim());
        i++;
      }

      if (tableLines.length >= 2) {
        const parseCells = (row) => {
          return row
            .slice(1, -1)
            .split('|')
            .map(cell => cell.trim());
        };

        const headers = parseCells(tableLines[0]);
        let startRow = 1;
        // Check if row 1 is a separator row like | :--- | :--- |
        if (tableLines.length > 1 && /^\|(\s*:?-+:?\s*\|)+$/.test(tableLines[1])) {
          startRow = 2;
        }

        let tableHtml = '<div class="bot-table-wrap"><table class="bot-table"><thead><tr>';
        headers.forEach(h => {
          tableHtml += `<th>${formatInlineMarkdown(h)}</th>`;
        });
        tableHtml += '</tr></thead><tbody>';

        for (let r = startRow; r < tableLines.length; r++) {
          const cells = parseCells(tableLines[r]);
          tableHtml += '<tr>';
          for (let c = 0; c < headers.length; c++) {
            const val = cells[c] !== undefined ? cells[c] : '';
            tableHtml += `<td>${formatInlineMarkdown(val)}</td>`;
          }
          tableHtml += '</tr>';
        }

        tableHtml += '</tbody></table></div>';
        blocks.push(tableHtml);
        continue;
      }
    }

    // B. Headings: ###, ##, #
    if (trimmed.startsWith('### ')) {
      blocks.push(`<h3 class="chat-heading chat-h3">${formatInlineMarkdown(trimmed.slice(4))}</h3>`);
      i++;
      continue;
    }
    if (trimmed.startsWith('## ')) {
      blocks.push(`<h2 class="chat-heading chat-h2">${formatInlineMarkdown(trimmed.slice(3))}</h2>`);
      i++;
      continue;
    }
    if (trimmed.startsWith('# ')) {
      blocks.push(`<h1 class="chat-heading chat-h1">${formatInlineMarkdown(trimmed.slice(2))}</h1>`);
      i++;
      continue;
    }

    // C. Callouts / Tips (💡, ℹ️, > [!TIP], > )
    if (trimmed.startsWith('💡') || trimmed.startsWith('ℹ️') || trimmed.startsWith('&gt; ') || trimmed.startsWith('> ')) {
      let calloutText = trimmed;
      if (calloutText.startsWith('> [!TIP]') || calloutText.startsWith('> [!NOTE]') || calloutText.startsWith('> [!IMPORTANT]')) {
        calloutText = calloutText.replace(/^>\s*\[!(TIP|NOTE|IMPORTANT|WARNING)\]\s*/i, '💡 ');
      } else if (calloutText.startsWith('&gt; ') || calloutText.startsWith('> ')) {
        calloutText = calloutText.replace(/^(&gt;|>)\s*/, '');
      }
      blocks.push(`<div class="chat-callout">${formatInlineMarkdown(calloutText)}</div>`);
      i++;
      continue;
    }

    // D. Unordered Lists (- , * , •)
    if (/^\s*[-*•]\s+/.test(line)) {
      let listHtml = '<ul class="chat-list">';
      while (i < lines.length && /^\s*[-*•]\s+/.test(lines[i])) {
        const itemLine = lines[i];
        const isNested = /^\s{2,}[-*•]\s+/.test(itemLine);
        const itemContent = itemLine.replace(/^\s*[-*•]\s+/, '').trim();
        listHtml += `<li class="${isNested ? 'chat-list-nested' : ''}">${formatInlineMarkdown(itemContent)}</li>`;
        i++;
      }
      listHtml += '</ul>';
      blocks.push(listHtml);
      continue;
    }

    // E. Ordered Lists (1. , 2. )
    if (/^\s*\d+\.\s+/.test(line)) {
      let oListHtml = '<ol class="chat-list chat-ordered-list">';
      while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) {
        const itemLine = lines[i];
        const itemContent = itemLine.replace(/^\s*\d+\.\s+/, '').trim();
        oListHtml += `<li>${formatInlineMarkdown(itemContent)}</li>`;
        i++;
      }
      oListHtml += '</ol>';
      blocks.push(oListHtml);
      continue;
    }

    // F. Normal Paragraphs
    const pLines = [];
    while (
      i < lines.length &&
      lines[i].trim() &&
      !lines[i].trim().startsWith('|') &&
      !lines[i].trim().startsWith('#') &&
      !lines[i].trim().startsWith('💡') &&
      !lines[i].trim().startsWith('ℹ️') &&
      !lines[i].trim().startsWith('> ') &&
      !/^\s*[-*•]\s+/.test(lines[i]) &&
      !/^\s*\d+\.\s+/.test(lines[i])
    ) {
      pLines.push(lines[i].trim());
      i++;
    }
    if (pLines.length > 0) {
      blocks.push(`<p class="chat-p">${pLines.map(formatInlineMarkdown).join('<br>')}</p>`);
    }
  }

  return blocks.join('\n');
}

function addMsg(text, cls) {
  const div = document.createElement('div');
  const displayText = cls === 'bot' ? cleanBotText(text) : text;
  const isRTL = isArabicText(displayText);

  div.className = 'msg ' + cls + (isRTL ? ' msg-rtl' : ' msg-ltr');
  div.setAttribute('dir', isRTL ? 'rtl' : 'ltr');
  div.textContent = displayText;

  body.appendChild(div);
  body.scrollTop = body.scrollHeight;
  return div;
}

/* ---------- Inspector Drawer (Workflow & Sources) ---------- */
function initInspector() {
  if (inspectorEl || !panel) return;

  inspectorEl = document.createElement('div');
  inspectorEl.className = 'chat-inspector';
  inspectorEl.id = 'chat-inspector';

  inspectorEl.innerHTML = `
    <div class="inspector-head">
      <div class="inspector-tabs">
        <button type="button" class="inspector-tab active" data-tab="workflow">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="6" y1="3" x2="6" y2="15"></line>
            <circle cx="18" cy="6" r="3"></circle>
            <circle cx="6" cy="18" r="3"></circle>
            <path d="M18 9a9 9 0 0 1-9 9"></path>
          </svg>
          <span class="tab-label" data-i18n="chat.btnWorkflow">Workflow</span>
        </button>
        <button type="button" class="inspector-tab" data-tab="sources">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"></path>
            <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"></path>
          </svg>
          <span class="tab-label" data-i18n="chat.btnSources">Sources</span>
          <span class="action-count-badge" id="inspector-sources-count">0</span>
        </button>
      </div>
      <button type="button" class="inspector-close-btn" id="inspector-close-btn" aria-label="Close">✕</button>
    </div>
    <div class="inspector-body" id="inspector-body"></div>
  `;

  panel.appendChild(inspectorEl);

  const closeBtnEl = inspectorEl.querySelector('#inspector-close-btn');
  if (closeBtnEl) {
    closeBtnEl.addEventListener('click', closeInspector);
  }

  inspectorEl.querySelectorAll('.inspector-tab').forEach((tabBtn) => {
    tabBtn.addEventListener('click', () => {
      const tab = tabBtn.getAttribute('data-tab');
      if (tab === 'workflow') {
        closeInspector();
        openHdGraphModal(currentInspectorData);
      } else {
        switchInspectorTab(tab);
      }
    });
  });
}

function openInspector(tab, data) {
  if (data) currentInspectorData = data;
  if (tab === 'workflow') {
    closeInspector();
    openHdGraphModal(data || currentInspectorData);
    return;
  }
  initInspector();
  if (!inspectorEl) return;

  currentInspectorData = data || currentInspectorData || {};
  switchInspectorTab(tab || 'sources');
  inspectorEl.classList.add('open');
}

function closeInspector() {
  if (inspectorEl) {
    inspectorEl.classList.remove('open');
  }
}

function switchInspectorTab(tab) {
  currentInspectorTab = tab;
  if (!inspectorEl) return;

  inspectorEl.querySelectorAll('.inspector-tab').forEach((btn) => {
    btn.classList.toggle('active', btn.getAttribute('data-tab') === tab);
  });

  const countBadge = inspectorEl.querySelector('#inspector-sources-count');
  if (countBadge && currentInspectorData) {
    const count = (currentInspectorData.sources || []).length;
    countBadge.textContent = count;
  }

  const inspectorBody = inspectorEl.querySelector('#inspector-body');
  if (!inspectorBody) return;

  if (tab === 'workflow') {
    renderWorkflowView(inspectorBody, currentInspectorData);
  } else {
    renderSourcesView(inspectorBody, currentInspectorData);
  }
}

/* ---------- Render Dynamic SVG Flowchart — Complete 12-Node LangGraph Architecture ---------- */
function renderWorkflowView(container, data) {
  const isAr = getLang() === 'ar';
  const workflow = data.workflow || [];

  /* ── 1. Build lookup maps from the workflow trace ─────────────────────── */
  const executedIds = new Set(workflow.map((w) => w.node));
  const seqMap = new Map();   // node-id → step-number (1-based)
  const stepMap = new Map();  // node-id → step object
  workflow.forEach((step, idx) => {
    seqMap.set(step.node, idx + 1);
    stepMap.set(step.node, step);
  });

  /* ── 2. Full 12-Node Pipeline Definition (Topological Graph Layout) ───── */
  const GRAPH_NODES = [
    // Top Rows
    { id: 'input_guard',     icon: '🛡️', labelEn: '1. Input Guardrail',      labelAr: '١. حارس المدخلات والأمان',    subEn: 'Prompt Injection Defense',      subAr: 'كشف وحجب هجمات الحقن',       cx: 400, cy: 75,  w: 240, h: 46, color: '#EF4444' },
    { id: 'intent',          icon: '🎯', labelEn: '2. Intent Classifier',    labelAr: '٢. تصنيف النية والتوجيه',     subEn: 'Fast Regex / 1-Call LLM',       subAr: 'توجيه سريع / استدعاء ذكي',    cx: 400, cy: 145, w: 240, h: 46, color: '#06B6D4' },
    
    // Fast & Safe Branches (Left & Right)
    { id: 'greeting',        icon: '⚡', labelEn: 'Fast Greeting',           labelAr: 'رد ترحيبي فوري',              subEn: 'Instant Warm Reply',            subAr: 'رد فوري دون استرجاع',        cx: 130, cy: 215, w: 190, h: 46, color: '#F59E0B' },
    { id: 'safe_response',   icon: '🛑', labelEn: 'Safe Response',           labelAr: 'المسار والرد الآمن',          subEn: 'Out-of-Scope & 111 Support',    subAr: 'خدمات غير مدعومة / تحويل',   cx: 670, cy: 215, w: 190, h: 46, color: '#F43F5E' },
    
    // Core Pipeline
    { id: 'understand',      icon: '🧠', labelEn: '3. Query Understanding',  labelAr: '٣. تحليل وتنميط الاستفسار',   subEn: 'Entity & Budget Profiling',     subAr: 'استخراج الباقة والميزانية',  cx: 400, cy: 215, w: 240, h: 46, color: '#818CF8' },
    { id: 'strategy_router', icon: '🧭', labelEn: '4. Strategy Router',      labelAr: '٤. موجه استراتيجية الرد',     subEn: 'TOOL_EXACT / REC / RAG_ONLY',   subAr: 'توجيه المسار الحتمي',        cx: 400, cy: 285, w: 250, h: 48, color: '#A855F7' },
    
    // Clarify Branch (Left) & Core Tools
    { id: 'clarify',         icon: '❓', labelEn: 'Device Clarification',    labelAr: 'توضيح نوع الجهاز',            subEn: 'Phone vs. Router/MiFi',         subAr: 'موبايل أم راوتر/MiFi',       cx: 130, cy: 360, w: 190, h: 46, color: '#F59E0B' },
    { id: 'mcp_tool',        icon: '🛠️', labelEn: '5. Deterministic Tools',  labelAr: '٥. الحقيقة المؤكدة',          subEn: 'Single-Source Catalog Facts',   subAr: 'الأسعار الرسمية وأكواد USSD',cx: 400, cy: 360, w: 250, h: 48, color: '#FB923C' },

    // Query Rewrite (bridges Arabic/English & resolves references before every retrieval call)
    { id: 'query_rewrite',   icon: '🔄', labelEn: '5b. Query Rewrite',       labelAr: '٥ب. إعادة صياغة الاستعلام',   subEn: 'Reference Resolution + AR/EN Bridge', subAr: 'حل الإشارات وربط اللغتين', cx: 400, cy: 430, w: 250, h: 46, color: '#0EA5E9' },

    // Hybrid Retrieval & Generation
    { id: 'retrieve',        icon: '🔍', labelEn: '6. Hybrid Retrieval',     labelAr: '٦. استرجاع هجين متوازي',      subEn: 'Dense + BM25 Sparse + RRF',     subAr: 'فكتور + كلمات مفتاحية',      cx: 400, cy: 500, w: 250, h: 48, color: '#10B981' },
    { id: 'generate',        icon: '✍️', labelEn: '7. Grounded Generation',  labelAr: '٧. توليد الإجابة الصارمة',    subEn: 'Verified Facts & Context',      subAr: 'بناء الرد من الحقائق فقط',    cx: 400, cy: 585, w: 250, h: 48, color: '#C084FC' },

    // Validation (with repair loop) & Output Guard
    { id: 'validate',        icon: '⚖️', labelEn: '8. 3-Tier Fact Validator',labelAr: '٨. فحص وتدقيق الحقائق',    subEn: 'PASS | REPAIR (1x) | REFUSE',   subAr: 'مطابقة الأسعار وأكواد USSD', cx: 400, cy: 675, w: 250, h: 48, color: '#2DD4BF' },
    { id: 'output_guard',    icon: '🔒', labelEn: '9. Output Guardrail',     labelAr: '٩. حارس المخرجات والتنقيح',   subEn: 'Secret Scrubbing & Formatting', subAr: 'تنظيف الوسوم وضمان السرية',   cx: 400, cy: 765, w: 240, h: 46, color: '#60A5FA' },
  ];

  const nodeById = {};
  GRAPH_NODES.forEach(n => { nodeById[n.id] = n; });

  const SVG_W = 800;
  const SVG_H = 870;

  /* ── 3. SVG Helper Functions ─────────────────────────────────────────── */
  function renderNode(n) {
    const isExecuted = executedIds.has(n.id);
    const seq = seqMap.get(n.id);
    const step = stepMap.get(n.id) || {};
    const latency = step.latency_ms !== undefined ? (step.latency_ms < 1000 ? `${step.latency_ms}ms` : `${(step.latency_ms/1000).toFixed(1)}s`) : '';

    const lx = n.cx - n.w / 2;
    const ly = n.cy - n.h / 2;
    const strokeCol = isExecuted ? n.color : 'rgba(148, 163, 184, 0.25)';
    const bgFill = isExecuted ? 'rgba(15, 23, 42, 0.92)' : 'rgba(15, 23, 42, 0.4)';
    const textTitleCol = isExecuted ? '#F8FAFC' : 'rgba(148, 163, 184, 0.55)';
    const textSubCol = isExecuted ? n.color : 'rgba(148, 163, 184, 0.4)';
    const strokeDash = isExecuted ? 'none' : '4 3';
    const strokeWidth = isExecuted ? 2.5 : 1.2;

    const seqBadge = isExecuted ? `
      <g transform="translate(${n.cx + n.w/2 - 12}, ${n.cy - n.h/2 + 2})">
        <circle cx="0" cy="0" r="10" fill="${n.color}" filter="url(#glowTiny)"/>
        <text x="0" y="3.5" text-anchor="middle" font-family="'Cairo', sans-serif" font-size="10" font-weight="900" fill="#FFFFFF">${seq}</text>
      </g>
    ` : '';

    const latencyBadge = (isExecuted && latency) ? `
      <g transform="translate(${n.cx - n.w/2 + 14}, ${n.cy - n.h/2 + 2})">
        <rect x="-6" y="-8" width="${latency.length * 7 + 16}" height="16" rx="8" fill="rgba(15, 23, 42, 0.92)" stroke="${n.color}" stroke-width="1.2"/>
        <text x="${(latency.length * 7) / 2 + 2}" y="3.5" text-anchor="middle" font-family="monospace" font-size="9" font-weight="800" fill="${n.color}">⏱️ ${latency}</text>
      </g>
    ` : '';

    const titleText = isAr ? n.labelAr : n.labelEn;
    const subText = isAr ? n.subAr : n.subEn;

    return `
      <g class="svg-wf-node ${isExecuted ? 'svg-node-active' : 'svg-node-idle'}"
         data-node-id="${n.id}"
         style="cursor: ${isExecuted ? 'pointer' : 'default'};"
         ${isExecuted ? `onclick="(function(){var el=document.getElementById('wf-step-${seq}');if(el){el.scrollIntoView({behavior:'smooth',block:'center'});el.style.outline='2px solid ${n.color}';setTimeout(function(){el.style.outline=''},1500);}})()"` : ''}>
        <rect x="${lx}" y="${ly}" width="${n.w}" height="${n.h}" rx="12"
              fill="${bgFill}" stroke="${strokeCol}" stroke-width="${strokeWidth}"
              stroke-dasharray="${strokeDash}"
              ${isExecuted ? `filter="url(#nodeGlow)"` : ''}/>
        <text x="${lx + 24}" y="${n.cy + 5}" font-size="18" text-anchor="middle">${n.icon}</text>
        <text x="${lx + 46}" y="${n.cy - 4}" font-family="'Cairo', sans-serif" font-size="11.5" font-weight="800" fill="${textTitleCol}">${titleText}</text>
        <text x="${lx + 46}" y="${n.cy + 13}" font-family="'Cairo', sans-serif" font-size="9" font-weight="600" fill="${textSubCol}">${subText}</text>
        ${seqBadge}
        ${latencyBadge}
      </g>
    `;
  }

  function renderTerminal(cx, cy, w, h, label, bg, isExecuted) {
    return `
      <g transform="translate(${cx}, ${cy})">
        <rect x="${-w/2}" y="${-h/2}" width="${w}" height="${h}" rx="${h/2}"
              fill="${isExecuted ? bg : 'rgba(30, 41, 59, 0.4)'}"
              stroke="${isExecuted ? 'rgba(255,255,255,0.4)' : 'rgba(148, 163, 184, 0.2)'}"
              stroke-width="1.5"/>
        <text x="0" y="4" text-anchor="middle" font-family="'Cairo', sans-serif" font-size="11" font-weight="800" fill="#FFFFFF">${label}</text>
      </g>
    `;
  }

  function renderEdge(d, isTraversed, color = '#10B981', customMarker = null) {
    const stroke = isTraversed ? color : 'rgba(148, 163, 184, 0.25)';
    const sw = isTraversed ? 2.8 : 1.4;
    const dash = isTraversed ? 'none' : '4 4';
    const marker = isTraversed ? (customMarker || 'url(#arrowActive)') : 'url(#arrowDim)';
    return `<path d="${d}" fill="none" stroke="${stroke}" stroke-width="${sw}" stroke-dasharray="${dash}" marker-end="${marker}"/>`;
  }

  /* ── 4. Build Flowchart SVG Parts ─────────────────────────────────────── */
  const svgParts = [];

  // SVG Defs
  svgParts.push(`
    <defs>
      <linearGradient id="eandRedGrad" x1="0%" y1="0%" x2="100%" y2="0%">
        <stop offset="0%" stop-color="#FF2E4D"/>
        <stop offset="100%" stop-color="#B8001F"/>
      </linearGradient>
      <filter id="nodeGlow" x="-20%" y="-20%" width="140%" height="140%">
        <feDropShadow dx="0" dy="3" stdDeviation="5" flood-color="#000000" flood-opacity="0.5"/>
      </filter>
      <filter id="glowTiny" x="-50%" y="-50%" width="200%" height="200%">
        <feDropShadow dx="0" dy="1" stdDeviation="2" flood-color="#000000" flood-opacity="0.6"/>
      </filter>
      <marker id="arrowActive" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
        <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="#10B981"/>
      </marker>
      <marker id="arrowPurpleActive" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
        <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="#C084FC"/>
      </marker>
      <marker id="arrowTealActive" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
        <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="#2DD4BF"/>
      </marker>
      <marker id="arrowCyanActive" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
        <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="#38BDF8"/>
      </marker>
      <marker id="arrowAmberActive" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
        <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="#F59E0B"/>
      </marker>
      <marker id="arrowRedActive" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
        <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="#EF4444"/>
      </marker>
      <marker id="arrowDim" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
        <path d="M 0 2 L 7 5 L 0 8 z" fill="rgba(148, 163, 184, 0.35)"/>
      </marker>
    </defs>
  `);

  // Background Grid inside SVG
  svgParts.push(`
    <rect width="100%" height="100%" fill="#0B0F17" rx="14"/>
    <g opacity="0.04">
      <pattern id="wfGrid" width="30" height="30" patternUnits="userSpaceOnUse">
        <path d="M 30 0 L 0 0 0 30" fill="none" stroke="#FFFFFF" stroke-width="1"/>
      </pattern>
      <rect width="100%" height="100%" fill="url(#wfGrid)"/>
    </g>
  `);

  /* ── 5. Connecting Flow Paths ─────────────────────────────────────────── */
  // START -> Input Guard
  svgParts.push(renderEdge('M 400 38 L 400 48', executedIds.has('input_guard'), '#10B981'));

  // Input Guard -> Intent (Allowed)
  svgParts.push(renderEdge('M 400 98 L 400 118', executedIds.has('input_guard') && executedIds.has('intent'), '#10B981'));

  // Input Guard -> Output Guard (Blocked attack bypass)
  const isInputBlocked = executedIds.has('input_guard') && !executedIds.has('intent') && executedIds.has('output_guard');
  svgParts.push(renderEdge('M 520 75 H 770 V 765 H 520', isInputBlocked, '#EF4444', 'url(#arrowRedActive)'));

  // Intent -> Greeting (Branch Left)
  const isGreetingPath = executedIds.has('intent') && executedIds.has('greeting');
  svgParts.push(renderEdge('M 280 145 H 130 V 188', isGreetingPath, '#F59E0B', 'url(#arrowAmberActive)'));

  // Intent -> Safe Response (Branch Right)
  const isSafePath = executedIds.has('intent') && executedIds.has('safe_response');
  svgParts.push(renderEdge('M 520 145 H 670 V 188', isSafePath, '#F43F5E', 'url(#arrowRedActive)'));

  // Intent -> Understand (Center Path)
  const isUnderstandPath = executedIds.has('intent') && executedIds.has('understand');
  svgParts.push(renderEdge('M 400 168 L 400 188', isUnderstandPath, '#06B6D4', 'url(#arrowCyanActive)'));

  // Greeting -> Output Guard (Direct to finish)
  svgParts.push(renderEdge('M 130 238 V 765 H 280', isGreetingPath && executedIds.has('output_guard'), '#F59E0B', 'url(#arrowAmberActive)'));

  // Safe Response -> Output Guard (Direct to finish)
  svgParts.push(renderEdge('M 670 238 V 765 H 520', isSafePath && executedIds.has('output_guard'), '#F43F5E', 'url(#arrowRedActive)'));

  // Understand -> Strategy Router
  const isStrategyPath = executedIds.has('understand') && executedIds.has('strategy_router');
  svgParts.push(renderEdge('M 400 238 L 400 258', isStrategyPath, '#A855F7', 'url(#arrowPurpleActive)'));

  // Strategy Router -> Clarify (Branch Left)
  const isClarifyPath = (executedIds.has('strategy_router') && executedIds.has('clarify')) || executedIds.has('clarify');
  svgParts.push(renderEdge('M 275 285 H 130 V 334', isClarifyPath, '#F59E0B', 'url(#arrowAmberActive)'));

  // Clarify -> Output Guard (Direct to finish)
  svgParts.push(renderEdge('M 130 383 V 765 H 280', isClarifyPath && executedIds.has('output_guard'), '#F59E0B', 'url(#arrowAmberActive)'));

  // Strategy Router -> Tools (Center Path)
  const isMcpPath = executedIds.has('strategy_router') && executedIds.has('mcp_tool');
  svgParts.push(renderEdge('M 400 309 L 400 333', isMcpPath, '#FB923C', 'url(#arrowAmberActive)'));

  // Strategy Router -> Query Rewrite (RAG_ONLY bypass — skips Tools entirely)
  const isRagOnlyPath = executedIds.has('strategy_router') && executedIds.has('query_rewrite') && !executedIds.has('mcp_tool');
  svgParts.push(renderEdge('M 275 285 H 240 V 430 H 275', isRagOnlyPath, '#0EA5E9'));

  // Tools -> Query Rewrite (Fusion)
  const isToolsToRewrite = executedIds.has('mcp_tool') && executedIds.has('query_rewrite');
  svgParts.push(renderEdge('M 400 384 L 400 407', isToolsToRewrite, '#0EA5E9'));

  // Query Rewrite -> Retrieve
  const isRewriteToRetrieve = executedIds.has('query_rewrite') && executedIds.has('retrieve');
  svgParts.push(renderEdge('M 400 453 L 400 476', isRewriteToRetrieve, '#10B981'));

  // Retrieve -> Generate
  const isRetrieveToGen = executedIds.has('retrieve') && executedIds.has('generate');
  svgParts.push(renderEdge('M 400 524 L 400 561', isRetrieveToGen, '#10B981'));

  // ── Critical Section: Generate (7) -> Validate (8) -> Output Guard (9) ──
  // Generate -> Validate
  const isGenToVal = executedIds.has('generate') && executedIds.has('validate');
  svgParts.push(renderEdge('M 400 609 L 400 651', isGenToVal, '#C084FC', 'url(#arrowPurpleActive)'));

  // Validate -> Targeted Repair (Loop back to Generate)
  const isRepairPath = executedIds.has('validate') && stepMap.get('validate')?.details?.validation_result === 'REPAIR';
  svgParts.push(renderEdge('M 275 675 H 220 V 585 H 270', isRepairPath, '#2DD4BF', 'url(#arrowTealActive)'));

  // Validate -> Output Guard (PASS / REFUSE)
  const isValToOut = executedIds.has('validate') && executedIds.has('output_guard');
  svgParts.push(renderEdge('M 400 699 L 400 742', isValToOut, '#10B981', 'url(#arrowActive)'));

  // Output Guard -> END
  const isOutToEnd = executedIds.has('output_guard');
  svgParts.push(renderEdge('M 400 788 L 400 821', isOutToEnd, '#38BDF8', 'url(#arrowCyanActive)'));

  /* ── 6. Terminals & Nodes Render ──────────────────────────────────────── */
  // START Terminal
  svgParts.push(renderTerminal(400, 25, 120, 24, '🚀 START', '#1E293B', true));

  // Render all nodes (idle first, then active on top)
  GRAPH_NODES.forEach(n => {
    if (!executedIds.has(n.id)) svgParts.push(renderNode(n));
  });
  GRAPH_NODES.forEach(n => {
    if (executedIds.has(n.id)) svgParts.push(renderNode(n));
  });

  // END Terminal
  svgParts.push(renderTerminal(400, 835, 160, 28, '🏁 FINAL OUTPUT', 'url(#eandRedGrad)', executedIds.has('validate') || executedIds.has('output_guard')));

  const totalLatency = data.latency_ms || workflow.reduce((sum, s) => sum + (s.latency_ms || 0), 0) || 0;
  const totalFormatted = formatDuration(totalLatency, isAr);

  const svgGraph = `
    <div class="wf-svg-toolbar" style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; flex-wrap:wrap; gap:6px;">
      <div style="display:flex; align-items:center; gap:8px;">
        <span style="font-size:11.5px; font-weight:700; color:#94A3B8;">${isAr ? 'مخطط سير العمل المباشر للطلب الحالي:' : 'Real-time Request Execution Pipeline:'}</span>
        ${totalLatency > 0 ? `<span class="wf-total-badge">⏱️ ${totalFormatted}</span>` : ''}
      </div>
      <button type="button" onclick="openHdGraphModal()" class="wf-fullscreen-btn" style="background:#1E293B; border:1px solid #334155; color:#F8FAFC; padding:4px 10px; border-radius:6px; font-size:11px; cursor:pointer; font-weight:700; display:inline-flex; align-items:center; gap:5px;">
        🔍 ${isAr ? 'تكبير المخطط الكامل بدقة عالية (HD)' : 'View Full HD Architecture'}
      </button>
    </div>
    <div class="wf-svg-wrap" style="background:#0b0f17; border-color:#1e293b;">
      <svg xmlns="http://www.w3.org/2000/svg"
           viewBox="0 0 ${SVG_W} ${SVG_H}"
           width="100%"
           style="display:block; max-height:580px;"
           class="wf-svg-graph">
        ${svgParts.join('\n')}
      </svg>
    </div>`;

  /* ── 7. Path Execution Chips Strip ────────────────────────────────────── */
  let pathStrip = '';
  if (workflow.length > 0) {
    const chips = workflow.map((step, i) => {
      const n = nodeById[step.node];
      const icon = n ? n.icon : '●';
      const label = n ? (isAr ? n.labelAr : n.labelEn) : step.node;
      const color = n ? n.color : '#10B981';
      const timeStr = step.latency_ms !== undefined ? `<span style="font-family:monospace; font-size:9.5px; opacity:0.9; margin-inline-start:4px;">⏱️${formatDurationCompact(step.latency_ms)}</span>` : '';
      return `<span class="wf-path-chip" style="border-color:${color}40; background:${color}15; color:${color};">
                <span class="wf-path-chip-num" style="background:${color}; color:#fff;">${i+1}</span>
                <span>${icon} ${label}</span>
                ${timeStr}
              </span>${i < workflow.length-1 ? '<span class="wf-path-sep" style="color:var(--slate);">→</span>' : ''}`;
    }).join('');
    pathStrip = `<div class="wf-path-strip" style="background:#131C2E; border-color:#1E293B;">${chips}</div>`;
  }

  /* ── 8. Step Detail Cards ─────────────────────────────────────────────── */
  let stepsHtml = '<div class="wf-steps-container">';
  if (workflow.length === 0) {
    stepsHtml += `<div class="empty-state-card">
      <span class="empty-state-ic">🔄</span>
      <p>${isAr ? 'تمت معالجة الاستفسار بنجاح.' : 'Query processed successfully.'}</p>
    </div>`;
  } else {
    workflow.forEach((step, idx) => {
      const n = nodeById[step.node];
      const title = isAr ? (step.title_ar || (n ? n.labelAr : step.node))
                         : (step.title_en || (n ? n.labelEn : step.node));
      const rawDesc = (step.description_en || '').trim();
      const rawBadge = step.badge || (step.status === 'completed' ? '✅ Done' : step.status || '');
      const badgeText = String(rawBadge).replace(/\s*\(\s*\d+%\s*\)/g, '').trim();

      let badgeClass = 'badge-success';
      if (['blocked','RETRIEVAL_FAILED','UNSUPPORTED'].includes(step.status)) badgeClass = 'badge-danger';
      else if (['warning','RETRIEVAL_WEAK'].includes(step.status)) badgeClass = 'badge-warning';

      const stepLatencyCompact = step.latency_ms !== undefined ? formatDurationCompact(step.latency_ms) : '';
      const stepLatencyFull = step.latency_ms !== undefined ? formatDuration(step.latency_ms, isAr) : '';

      const details = step.details || {};
      let chipsHtml = '';
      const chipEntries = [];
      if (stepLatencyFull) chipEntries.push({ l: isAr ? 'مدة الخطوة' : 'Duration', v: stepLatencyFull });
      if (details.intent) chipEntries.push({ l: 'Intent', v: details.intent });
      if (details.category) chipEntries.push({ l: 'Category', v: details.category });
      if (details.service && details.service !== 'general') chipEntries.push({ l: 'Service', v: details.service });
      if (details.language) chipEntries.push({ l: 'Language', v: details.language });
      if (details.candidate_count !== undefined) chipEntries.push({ l: 'Candidates', v: details.candidate_count });
      if (details.selected_count !== undefined) chipEntries.push({ l: 'Selected', v: details.selected_count });
      if (details.grounding_ratio !== undefined) chipEntries.push({ l: 'Grounding', v: Math.round(details.grounding_ratio*100)+'%' });
      if (details.confidence !== undefined) chipEntries.push({ l: 'Confidence', v: Math.round(details.confidence*100)+'%' });

      if (chipEntries.length) {
        chipsHtml = '<div class="wf-details-grid">'
          + chipEntries.map(c => `<div class="wf-chip"><span class="wf-chip-label">${c.l}:</span><span class="wf-chip-val">${c.v}</span></div>`).join('')
          + '</div>';
      }

      stepsHtml += `
        <div class="wf-step-card" id="wf-step-${idx+1}" style="border-left: 4px solid ${n ? n.color : '#10B981'};">
          <div class="wf-step-header">
            <div class="wf-step-title-wrap">
              <span class="wf-step-num" style="background:${n ? n.color : '#10B981'}; color:#fff;">${idx+1}</span>
              <span class="wf-step-name">${n ? n.icon : ''} ${title}</span>
            </div>
            <div style="display:flex; align-items:center; gap:6px;">
              ${stepLatencyCompact ? `<span class="wf-step-time">⏱️ ${stepLatencyCompact}</span>` : ''}
              <span class="wf-step-badge ${badgeClass}">${badgeText}</span>
            </div>
          </div>
          ${rawDesc ? `<p class="wf-step-desc">${rawDesc}</p>` : ''}
          ${chipsHtml}
        </div>`;
    });
  }
  stepsHtml += '</div>';

  /* ── 9. Assemble Inspector View ───────────────────────────────────────── */
  container.innerHTML = `
    <div class="wf-section-title">
      <span>${isAr ? 'مخطط مسار الـ LangGraph المنفّذ' : 'LangGraph Execution State Machine'}</span>
      <span style="font-size:11px;color:var(--slate);font-weight:600;">${workflow.length} ${isAr ? 'عقد منفذة' : 'executed nodes'} ${totalLatency > 0 ? `• ${totalFormatted}` : ''}</span>
    </div>
    ${svgGraph}
    ${pathStrip}
    <div class="wf-section-title" style="margin-top:8px;">
      <span>${isAr ? 'تفاصيل خطوات التنفيذ' : 'Step-by-Step Execution Details'}</span>
    </div>
    ${stepsHtml}`;
}


/* ---------- Render Sources View ---------- */

/**
 * Convert internal technical source filenames / paths to a human-readable
 * display name shown in the Sources panel.
 * Examples:
 *   "hekaya_mixat.yaml"   → "Hekaya Mixat"
 *   "tax_rules.yaml"      → "Tax Rules"
 *   "e& Egypt Knowledge Base" → unchanged
 *   ""                    → fallback
 */
function normalizeSourceName(raw, isAr) {
  if (!raw || !raw.trim()) {
    return isAr ? 'قاعدة المعرفة – e& مصر' : 'e& Egypt Knowledge Base';
  }
  const s = raw.trim();
  // Already a nice human-readable name (no file extension, contains spaces / Arabic)
  if (!s.includes('.') && (s.includes(' ') || /[\u0600-\u06FF]/.test(s))) {
    return s;
  }
  // Strip path separators — keep only the final segment
  const basename = s.replace(/\\/g, '/').split('/').pop() || s;
  // Remove file extension
  const noExt = basename.replace(/\.[a-zA-Z0-9]+$/, '');
  // Convert underscores/hyphens to spaces and title-case each word
  const spaced = noExt.replace(/[_-]/g, ' ');
  const titled = spaced.replace(/\b\w/g, ch => ch.toUpperCase());
  return titled || (isAr ? 'قاعدة المعرفة – e& مصر' : 'e& Egypt Knowledge Base');
}

function renderSourcesView(container, data) {
  const dict = currentDict();
  const isAr = getLang() === 'ar';
  const rawSources = data.sources || [];

  // ── Deduplicate by chunk_id, then by snippet identity ──────────────────
  const seen = new Set();
  const sources = rawSources.filter((src) => {
    const key = src.chunk_id || src.snippet || JSON.stringify(src);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });

  if (sources.length === 0) {
    container.innerHTML = `
      <div class="empty-state-card">
        <span class="empty-state-ic">📄</span>
        <p>${dict['chat.noSources'] || (isAr ? 'لم يتم استخدام وثائق خارجية (تمت معالجة الاستفسار مباشرة عبر قواعد التوجيه المباشر والأمان).' : 'No external document retrieval was required for this response.')}</p>
      </div>
    `;
    return;
  }

  const SNIPPET_PREVIEW_CHARS = 320;

  let html = `
    <div class="wf-section-title" style="margin-bottom:10px;">
      <span>${isAr ? 'المقاطع والوثائق المعتمدة المسترجعة' : 'Retrieved Verified Knowledge Chunks'}</span>
      <span style="font-size:11px; color:var(--slate); font-weight:600;">${sources.length} ${isAr ? 'مقطع مسترجع' : 'chunks retrieved'}</span>
    </div>
    <div class="sources-container">
  `;

  sources.forEach((src, idx) => {
    const rawSource   = src.source || '';
    const displayName = normalizeSourceName(rawSource, isAr);
    const technicalId = rawSource && rawSource !== displayName ? escapeHtml(rawSource) : '';

    const page     = src.page !== undefined && src.page !== '' ? `${dict['chat.page'] || (isAr ? 'صفحة' : 'Page')} ${escapeHtml(String(src.page))}` : '';
    const category = escapeHtml(src.category || '');
    const product  = escapeHtml(src.product || '');
    const chunkId  = escapeHtml(src.chunk_id || '');

    // Safely escape the raw snippet text before rendering
    const rawSnippet     = (src.snippet || '').trim();
    const escapedSnippet = escapeHtml(rawSnippet);
    const isLong         = rawSnippet.length > SNIPPET_PREVIEW_CHARS;
    const preview        = isLong ? escapeHtml(rawSnippet.slice(0, SNIPPET_PREVIEW_CHARS)) + '…' : escapedSnippet;
    const isSnippetRTL   = isArabicText(rawSnippet);

    const chunkLabel = `${dict['chat.chunk'] || (isAr ? 'المقطع' : 'Chunk')} #${idx + 1}`;

    html += `
      <div class="source-card" data-src-idx="${idx}">
        <div class="source-head">
          <div class="source-title-wrap">
            <span class="source-chunk-badge">${chunkLabel}</span>
            <span class="source-ic">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                <polyline points="14 2 14 8 20 8"></polyline>
              </svg>
            </span>
            <span class="source-filename" title="${technicalId || escapeHtml(displayName)}">${escapeHtml(displayName)}</span>
          </div>
          <div style="display:flex; align-items:center; gap:6px;">
            ${page ? `<span class="source-page-badge">${page}</span>` : ''}
            <button type="button" class="source-copy-btn" data-chunk-idx="${idx}" title="${dict['chat.copyChunk'] || (isAr ? 'نسخ المقطع' : 'Copy Chunk')}">
              📋 <span>${dict['chat.copyChunk'] || (isAr ? 'نسخ' : 'Copy')}</span>
            </button>
          </div>
        </div>

        ${(category || product) ? `
          <div class="source-tags">
            ${category ? `<span class="source-tag">🏷️ ${category}</span>` : ''}
            ${product  ? `<span class="source-tag">📦 ${product}</span>`  : ''}
          </div>
        ` : ''}

        ${rawSnippet ? `
          <div class="source-snippet-box ${isSnippetRTL ? 'source-rtl' : 'source-ltr'}" dir="${isSnippetRTL ? 'rtl' : 'ltr'}">
            <span class="src-snippet-preview">${preview}</span>
            ${isLong ? `
              <span class="src-snippet-full" style="display:none;">${escapedSnippet}</span>
              <button type="button" class="src-expand-btn" data-expanded="false">
                ${isAr ? 'عرض الكل ▼' : 'Show more ▼'}
              </button>
            ` : ''}
          </div>
        ` : ''}

        ${chunkId ? `<div class="source-chunk-id" title="${isAr ? 'معرف المقطع الداخلي' : 'Internal chunk ID'}">🔗 ${chunkId}</div>` : ''}
      </div>
    `;
  });
  html += '</div>';

  container.innerHTML = html;

  // ── Expand / Collapse snippet buttons ──────────────────────────────────
  container.querySelectorAll('.src-expand-btn').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      const box      = btn.closest('.source-snippet-box');
      const preview  = box && box.querySelector('.src-snippet-preview');
      const fullEl   = box && box.querySelector('.src-snippet-full');
      const expanded = btn.getAttribute('data-expanded') === 'true';
      if (!preview || !fullEl) return;
      if (expanded) {
        fullEl.style.display   = 'none';
        preview.style.display  = '';
        btn.setAttribute('data-expanded', 'false');
        btn.textContent = isAr ? 'عرض الكل ▼' : 'Show more ▼';
      } else {
        preview.style.display  = 'none';
        fullEl.style.display   = '';
        btn.setAttribute('data-expanded', 'true');
        btn.textContent = isAr ? 'تصغير ▲' : 'Show less ▲';
      }
    });
  });

  // ── Copy button handlers ────────────────────────────────────────────────
  container.querySelectorAll('.source-copy-btn').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      const idx = parseInt(btn.getAttribute('data-chunk-idx'), 10);
      const textToCopy = sources[idx]?.snippet || '';
      if (textToCopy) {
        navigator.clipboard.writeText(textToCopy).then(() => {
          const span = btn.querySelector('span');
          if (span) {
            const original = span.textContent;
            span.textContent = dict['chat.copied'] || (isAr ? 'تم النسخ!' : 'Copied!');
            btn.style.borderColor = '#10B981';
            btn.style.color = '#10B981';
            setTimeout(() => {
              span.textContent = original;
              btn.style.borderColor = '';
              btn.style.color = '';
            }, 1500);
          }
        }).catch(() => {});
      }
    });
  });
}

/* ---------- Build Claude-style Post-Response Thought Accordion ---------- */
function buildThoughtAccordion(data) {
  const isAr = getLang() === 'ar';
  const dict = currentDict();
  const workflow = data.workflow || [];
  const latencyMs = data.latency_ms || workflow.reduce((sum, s) => sum + (s.latency_ms || 0), 0) || 0;
  const timeFormatted = formatDurationCompact(latencyMs);
  const stepCount = workflow.length;

  if (stepCount === 0 && !latencyMs) return null;

  const thoughtBox = document.createElement('div');
  thoughtBox.className = 'thought-box';

  let titleTemplate = dict['chat.thoughtFor'] || (isAr ? 'تم التفكير خلال {time} • {steps} مراحل' : 'Thought for {time} • {steps} steps');
  const titleText = titleTemplate.replace('{time}', timeFormatted).replace('{steps}', stepCount);

  let stepsHtml = '';
  if (stepCount > 0) {
    stepsHtml = '<div class="thought-timeline">';
    workflow.forEach((step, idx) => {
      const meta = GRAPH_NODE_META[step.node] || { icon: '●', labelEn: step.node, labelAr: step.node, color: '#10B981' };
      const name = isAr ? (step.title_ar || meta.labelAr) : (step.title_en || meta.labelEn);
      const stepLatency = step.latency_ms !== undefined ? formatDurationCompact(step.latency_ms) : '';
      stepsHtml += `
        <div class="thought-step-item">
          <div class="thought-step-info">
            <span>${meta.icon}</span>
            <span>${idx + 1}. ${name}</span>
          </div>
          ${stepLatency ? `<span class="thought-step-time">⏱️ ${stepLatency}</span>` : ''}
        </div>
      `;
    });
    stepsHtml += '</div>';
  }

  thoughtBox.innerHTML = `
    <button type="button" class="thought-toggle-btn" aria-expanded="false">
      <div class="thought-label-wrap">
        <span class="thought-icon">💭</span>
        <span>${titleText}</span>
      </div>
      <span class="thought-chevron">▼</span>
    </button>
    <div class="thought-content">
      ${stepsHtml}
      <button type="button" class="thought-graph-link">
        🧭 ${dict['chat.viewFullGraph'] || (isAr ? 'عرض المخطط التفاعلي الكامل' : 'Open Full Visual Pipeline')} ↗
      </button>
    </div>
  `;

  const toggleBtn = thoughtBox.querySelector('.thought-toggle-btn');
  const graphLink = thoughtBox.querySelector('.thought-graph-link');

  if (toggleBtn) {
    toggleBtn.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      const isOpen = thoughtBox.classList.toggle('open');
      toggleBtn.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
    });
  }

  if (graphLink) {
    graphLink.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      closeInspector();
      openHdGraphModal(data);
    });
  }

  return thoughtBox;
}

/* ---------- Add Bot Message with Action Buttons ---------- */
function addBotResponse(data) {
  const dict = currentDict();
  const rawAnswer = data.answer || dict['chat.noAnswer'];
  const isRTL = isArabicText(rawAnswer);
  const isAr = getLang() === 'ar';

  const groupDiv = document.createElement('div');
  groupDiv.className = 'bot-msg-group';

  // 1. Claude-style Thought Accordion
  const thoughtBox = buildThoughtAccordion(data);
  if (thoughtBox) {
    groupDiv.appendChild(thoughtBox);
  }

  // 2. Bot message bubble
  const msgDiv = document.createElement('div');
  msgDiv.className = 'msg bot ' + (isRTL ? 'msg-rtl' : 'msg-ltr');
  msgDiv.setAttribute('dir', isRTL ? 'rtl' : 'ltr');

  // Model badge indicator
  if (data.model_used) {
    const badge = document.createElement('div');
    const isLocal = data.model_used.toLowerCase().includes('local') || data.model_used.toLowerCase().includes('gpu') || data.model_used.toLowerCase().includes('qwen');
    badge.className = 'msg-model-badge ' + (isLocal ? 'local' : 'cloud');
    badge.innerHTML = (isLocal ? '⚡ ' : '☁️ ') + data.model_used;
    msgDiv.appendChild(badge);
  }

  const textNode = document.createElement('div');
  textNode.className = 'msg-content-text formatted-content';
  textNode.innerHTML = renderMarkdown(rawAnswer);
  msgDiv.appendChild(textNode);

  groupDiv.appendChild(msgDiv);

  // 3. Action buttons toolbar
  const actionsDiv = document.createElement('div');
  actionsDiv.className = 'msg-actions';

  // Latency chip in action bar
  if (data.latency_ms) {
    const latencyPill = document.createElement('span');
    latencyPill.className = 'msg-action-latency';
    latencyPill.title = dict['chat.totalLatency'] || (isAr ? 'إجمالي وقت التنفيذ' : 'Total latency');
    latencyPill.innerHTML = `⏱️ ${formatDurationCompact(data.latency_ms)}`;
    actionsDiv.appendChild(latencyPill);
  }

  // Workflow button -> Opens Full HD Architecture Directly!
  const wfBtn = document.createElement('button');
  wfBtn.type = 'button';
  wfBtn.className = 'msg-action-btn wf-btn';
  wfBtn.innerHTML = `
    <svg viewBox="0 0 24 24" fill="none" stroke-width="2">
      <line x1="6" y1="3" x2="6" y2="15"></line>
      <circle cx="18" cy="6" r="3"></circle>
      <circle cx="6" cy="18" r="3"></circle>
      <path d="M18 9a9 9 0 0 1-9 9"></path>
    </svg>
    <span>${dict['chat.btnWorkflow'] || (isAr ? 'مسار العمل' : 'Workflow')}</span>
  `;
  wfBtn.addEventListener('click', () => {
    closeInspector();
    openHdGraphModal(data);
  });
  actionsDiv.appendChild(wfBtn);

  // Sources button
  const sourcesCount = (data.sources || []).length;
  const sourcesBtn = document.createElement('button');
  sourcesBtn.type = 'button';
  sourcesBtn.className = 'msg-action-btn sources-btn';
  sourcesBtn.innerHTML = `
    <svg viewBox="0 0 24 24" fill="none" stroke-width="2">
      <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"></path>
      <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"></path>
    </svg>
    <span>${dict['chat.btnSources'] || (isAr ? 'المصادر' : 'Sources')}</span>
    <span class="action-count-badge">${sourcesCount}</span>
  `;
  sourcesBtn.addEventListener('click', () => openInspector('sources', data));
  actionsDiv.appendChild(sourcesBtn);

  groupDiv.appendChild(actionsDiv);
  body.appendChild(groupDiv);

  // Scroll to the beginning of the bot response (or user prompt if short)
  // so the user can read the response from the very start instead of jumping to the end.
  requestAnimationFrame(() => {
    if (!body) return;
    const bodyRect = body.getBoundingClientRect();
    const prevMsg = groupDiv.previousElementSibling;

    // If the immediately preceding user message is short, keep it visible at the top for context;
    // otherwise, align directly to the start of the bot response group.
    let targetEl = groupDiv;
    if (prevMsg && prevMsg.classList.contains('user') && prevMsg.offsetHeight <= 85) {
      targetEl = prevMsg;
    }

    const targetRect = targetEl.getBoundingClientRect();
    const scrollTarget = body.scrollTop + (targetRect.top - bodyRect.top) - 10;

    body.scrollTo({
      top: Math.max(0, Math.round(scrollTarget)),
      behavior: 'smooth'
    });
  });

  chatHistory.push({ role: 'assistant', content: rawAnswer });
}


/* ---------- Claude-style Live Reasoning / Working Widget ---------- */
let thinkingTimerInterval = null;
let thinkingStageTimeout = null;
let thinkingStartTime = null;

function showTyping() {
  hideTyping();

  const isAr = getLang() === 'ar';
  const dict = currentDict();

  const stages = [
    { icon: '🛡️', text: dict['chat.liveStep1'] || (isAr ? 'فحص الأمان وحارس المدخلات...' : 'Checking guardrails & query safety...') },
    { icon: '🎯', text: dict['chat.liveStep2'] || (isAr ? 'تحليل النية وتحديد الباقة والميزانية...' : 'Analyzing intent & customer requirements...') },
    { icon: '🛠️', text: dict['chat.liveStep3'] || (isAr ? 'استرجاع الأسعار الرسمية وأكواد USSD...' : 'Querying catalog facts & official prices...') },
    { icon: '🔍', text: dict['chat.liveStep4'] || (isAr ? 'بحث هجين في قاعدة المعرفة والوثائق...' : 'Running hybrid semantic & keyword retrieval...') },
    { icon: '✍️', text: dict['chat.liveStep5'] || (isAr ? 'صياغة الرد النهائي وتدقيق صحة الأرقام...' : 'Formulating grounded response & verifying facts...') },
  ];

  let currentStageIdx = 0;
  thinkingStartTime = Date.now();

  const card = document.createElement('div');
  card.className = 'agent-thinking-card';
  card.id = 'agent-thinking-card';

  card.innerHTML = `
    <div class="thinking-header">
      <div class="thinking-status-wrap">
        <div class="thinking-beacon">
          <div class="thinking-beacon-ring"></div>
          <div class="thinking-beacon-dot"></div>
        </div>
        <span class="thinking-title">${dict['chat.working'] || (isAr ? 'جارٍ العمل...' : 'Working...')}</span>
      </div>
      <span class="thinking-timer" id="thinking-timer-val">⏱️ 0.0s</span>
    </div>
    <div class="thinking-stage-wrap">
      <span class="thinking-stage-text" id="thinking-stage-txt">${stages[0].icon} ${stages[0].text}</span>
    </div>
    <div class="thinking-shimmer-bar">
      <div class="thinking-shimmer-thumb"></div>
    </div>
  `;

  body.appendChild(card);
  body.scrollTop = body.scrollHeight;

  thinkingTimerInterval = setInterval(() => {
    const elapsedSec = ((Date.now() - thinkingStartTime) / 1000).toFixed(1);
    const timerVal = document.getElementById('thinking-timer-val');
    if (timerVal) {
      timerVal.textContent = `⏱️ ${elapsedSec}s`;
    }
  }, 100);

  function advanceStage() {
    currentStageIdx = (currentStageIdx + 1) % stages.length;
    const stageTxt = document.getElementById('thinking-stage-txt');
    if (stageTxt) {
      stageTxt.style.opacity = '0';
      stageTxt.style.transform = 'translateY(3px)';
      setTimeout(() => {
        stageTxt.textContent = `${stages[currentStageIdx].icon} ${stages[currentStageIdx].text}`;
        stageTxt.style.opacity = '1';
        stageTxt.style.transform = 'translateY(0)';
      }, 150);
    }
    const nextInterval = currentStageIdx === 1 ? 1200 : (currentStageIdx === 2 ? 1500 : 1800);
    thinkingStageTimeout = setTimeout(advanceStage, nextInterval);
  }

  thinkingStageTimeout = setTimeout(advanceStage, 1000);
}

function hideTyping() {
  if (thinkingTimerInterval) {
    clearInterval(thinkingTimerInterval);
    thinkingTimerInterval = null;
  }
  if (thinkingStageTimeout) {
    clearTimeout(thinkingStageTimeout);
    thinkingStageTimeout = null;
  }
  const card = document.getElementById('agent-thinking-card');
  if (card) card.remove();
  const legacyTyping = document.getElementById('typing-indicator');
  if (legacyTyping) legacyTyping.remove();
}

function openChat() {
  if (!panel) return;
  panel.classList.add('open');
  initModelSelector();
  initExpandToggle();
  if (input) input.focus();
}

function closeChat() {
  if (panel) {
    panel.classList.remove('open');
    closeInspector();
    setExpanded(false);
  }
}

if (launcher && panel) {
  launcher.addEventListener('click', () => {
    if (panel.classList.contains('open')) {
      closeChat();
    } else {
      openChat();
    }
  });
}

if (closeBtn) {
  closeBtn.addEventListener('click', closeChat);
}

document.addEventListener('click', (event) => {
  const target = event.target.closest('a, button');
  if (!target) return;

  const href = target.getAttribute('href') || '';
  const text = (target.textContent || '').trim().toLowerCase();
  const i18n = target.getAttribute('data-i18n') || '';

  // If already linking directly to chatbot.html, allow normal browser navigation
  if (href.includes('chatbot.html')) {
    return;
  }

  // If on chatbot page, do not trigger popup open/close
  if (typeof document !== 'undefined' && document.body && document.body.classList.contains('chatbot-page')) {
    return;
  }

  if (
    target.classList.contains('open-chat')
    || href === '#chat'
    || i18n.includes('ctaSecondary')
    || text.includes('ask the chatbot')
    || text.includes('ask the e&')
    || text.includes('smart assistant')
  ) {
    event.preventDefault();
    window.location.href = 'chatbot.html';
  }
});

if (form && input) {
  form.addEventListener('submit', async (event) => {
    event.preventDefault();

    const question = input.value.trim();
    if (!question) return;

    if (body) {
      body.querySelectorAll('.msg.error').forEach(el => el.remove());
    }

    addMsg(question, 'user');
    chatHistory.push({ role: 'user', content: question });
    input.value = '';
    input.disabled = true;
    showTyping();

    const dict = currentDict();
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 120000);

    try {
      const response = await fetch(API_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question,
          history: chatHistory.slice(-6),
          model: selectedModel,
          conversation_id: conversationId,
        }),
        signal: controller.signal,
      });

      clearTimeout(timeoutId);
      hideTyping();

      if (!response.ok) {
        let detail = '';
        try {
          const errorData = await response.json();
          detail = errorData.detail || '';
        } catch (_) {
          detail = '';
        }

        addMsg(detail || dict['chat.offline'], 'error');
        return;
      }

      const data = await response.json();
      if (data.conversation_id) {
        conversationId = data.conversation_id;
      }
      addBotResponse(data);
    } catch (err) {
      console.error('Chat error:', err);
      clearTimeout(timeoutId);
      hideTyping();
      addMsg(dict['chat.offline'], 'error');
    } finally {
      input.disabled = false;
      try {
        input.focus({ preventScroll: true });
      } catch (_) {
        input.focus();
      }
    }
  });
}

function initMessagesDirection() {
  if (!body) return;

  body.querySelectorAll('.msg').forEach((msg) => {
    const text = msg.textContent || '';
    const isRTL = isArabicText(text);
    msg.classList.add(isRTL ? 'msg-rtl' : 'msg-ltr');
    msg.setAttribute('dir', isRTL ? 'rtl' : 'ltr');
  });
}

if (input) {
  input.setAttribute('dir', 'auto');
  input.addEventListener('input', () => {
    const value = input.value;

    if (!value.trim()) {
      input.setAttribute('dir', 'auto');
    } else {
      input.setAttribute('dir', isArabicText(value) ? 'rtl' : 'ltr');
    }
  });
}

window.addEventListener('languagechange', () => {
  if (inspectorEl && inspectorEl.classList.contains('open') && currentInspectorData) {
    switchInspectorTab(currentInspectorTab);
  }
  if (newChatBtn) {
    newChatBtn.setAttribute('aria-label', newChatTitle());
    newChatBtn.title = newChatTitle();
  }
  if (expandBtn) {
    expandBtn.setAttribute('aria-label', expandTitle());
    expandBtn.title = expandTitle();
  }
});

window.openHdGraphModal = function(passedData) {
  const isAr = getLang() === 'ar';
  let modal = document.getElementById('hd-graph-modal');
  if (modal) modal.remove();

  if (passedData && typeof passedData === 'object' && Object.keys(passedData).length > 0) {
    currentInspectorData = passedData;
  }

  // Ensure inspector drawer is closed
  closeInspector();

  // Pull workflow data from passed argument or current inspector context
  const data = (passedData && passedData.workflow)
    ? passedData
    : ((typeof currentInspectorData !== 'undefined' && currentInspectorData) ? currentInspectorData : (passedData || {}));
  const workflow = data.workflow || [];

  const executedIds = new Set(workflow.map(w => w.node));
  const seqMap = new Map();
  const stepMap = new Map();
  workflow.forEach((s, i) => { seqMap.set(s.node, i + 1); stepMap.set(s.node, s); });

  const totalLatency = data.latency_ms || workflow.reduce((sum, s) => sum + (s.latency_ms || 0), 0) || 0;

  // ── Node layout definitions (must match renderWorkflowView GRAPH_NODES) ──
  const GN = [
    { id:'input_guard',    icon:'🛡️', en:'1. Input Guardrail',       ar:'١. حارس المدخلات',        sub:'Prompt Injection Defense',          cx:400, cy:75,  w:240, h:46, color:'#EF4444' },
    { id:'intent',         icon:'🎯', en:'2. Intent Classifier',     ar:'٢. تصنيف النية',           sub:'<1ms Microsecond Resolver',          cx:400, cy:145, w:240, h:46, color:'#06B6D4' },
    { id:'greeting',       icon:'⚡', en:'Fast Greeting',            ar:'رد ترحيبي فوري',           sub:'Instant — No RAG',                  cx:130, cy:215, w:190, h:46, color:'#F59E0B' },
    { id:'safe_response',  icon:'🛑', en:'Safe Response / 111',      ar:'رد آمن / 111',             sub:'Out-of-Scope Deflection',           cx:670, cy:215, w:190, h:46, color:'#F43F5E' },
    { id:'understand',     icon:'🧠', en:'3. Query Profiling',       ar:'٣. تنميط الاستفسار',       sub:'Entity & Budget Extraction',        cx:400, cy:215, w:240, h:46, color:'#818CF8' },
    { id:'strategy_router',icon:'🧭', en:'4. Strategy Router',       ar:'٤. موجه الاستراتيجية',     sub:'TOOL_EXACT / REC / RAG_ONLY',        cx:400, cy:285, w:250, h:48, color:'#A855F7' },
    { id:'clarify',        icon:'❓', en:'Device Clarification',     ar:'توضيح نوع الجهاز',          sub:'Phone vs. Router/MiFi',             cx:130, cy:360, w:190, h:46, color:'#F59E0B' },
    { id:'mcp_tool',       icon:'🛠️', en:'5. Deterministic Tools',   ar:'٥. الأدوات الحتمية',       sub:'Catalog Facts · USSD · 2-Tier Rec',  cx:400, cy:360, w:250, h:48, color:'#FB923C' },
    { id:'query_rewrite',  icon:'🔄', en:'5b. Query Rewrite',        ar:'٥ب. صياغة الاستعلام',      sub:'AR/EN Bridge · Reference Resolve',   cx:400, cy:430, w:250, h:46, color:'#0EA5E9' },
    { id:'retrieve',       icon:'🔍', en:'6. Hybrid Retrieval',      ar:'٦. استرجاع هجين',          sub:'Dense + BM25 + RRF Fusion',         cx:400, cy:500, w:250, h:48, color:'#10B981' },
    { id:'generate',       icon:'✍️', en:'7. Grounded Generation',   ar:'٧. التوليد الصارم',        sub:'gpt-5-mini · Anti-Hallucination',   cx:400, cy:585, w:250, h:48, color:'#C084FC' },
    { id:'validate',       icon:'⚖️', en:'8. 3-Tier Fact Validator', ar:'٨. التحقق الثلاثي',        sub:'PASS | REPAIR (1x) | REFUSE',        cx:400, cy:675, w:250, h:48, color:'#2DD4BF' },
    { id:'output_guard',   icon:'🔒', en:'9. Output Guardrail',      ar:'٩. حارس المخرجات',         sub:'PII Scrub · Format Polish',          cx:400, cy:765, w:240, h:46, color:'#60A5FA' },
  ];

  const W = 800, H = 870;

  function fmtMs(ms) {
    if (ms == null) return '';
    return ms < 1000 ? `${ms}ms` : `${(ms/1000).toFixed(1)}s`;
  }

  // Build animated CSS for pipeline nodes, edges, and strip
  const orderedExecuted = workflow.map(s => s.node).filter(id => GN.some(n => n.id === id));
  const STEP_DURATION_MS = 650; // ms per step for clean visible step-by-step lighting

  let animCss = `
    /* Node group transitions */
    .hd-node-group {
      cursor: pointer;
      transform-origin: center;
      transition: transform 0.2s ease;
    }
    .hd-node-group:hover {
      transform: scale(1.02);
    }
    .hd-node-rect {
      transition: fill 0.35s ease, stroke 0.35s ease, stroke-width 0.35s ease, filter 0.35s ease;
    }
    .hd-node-icon, .hd-node-title, .hd-node-sub {
      transition: opacity 0.35s ease, fill 0.35s ease;
    }
    .hd-node-badge {
      transition: opacity 0.35s cubic-bezier(0.34,1.56,0.64,1), transform 0.35s cubic-bezier(0.34,1.56,0.64,1);
      transform-origin: center;
    }
    .hd-node-latency {
      transition: opacity 0.35s ease, transform 0.35s ease;
    }

    /* 1. Pending State: Dim, Unlit, Sleek Waiting */
    .hd-node-pending .hd-node-rect {
      fill: rgba(15, 23, 42, 0.45) !important;
      stroke: rgba(148, 163, 184, 0.16) !important;
      stroke-width: 1.2px !important;
      stroke-dasharray: 4 3 !important;
      filter: none !important;
    }
    .hd-node-pending .hd-node-icon {
      opacity: 0.25 !important;
    }
    .hd-node-pending .hd-node-title {
      fill: #64748B !important;
      opacity: 0.4 !important;
    }
    .hd-node-pending .hd-node-sub {
      fill: #475569 !important;
      opacity: 0.3 !important;
    }
    .hd-node-pending .hd-node-badge {
      opacity: 0 !important;
      transform: scale(0) !important;
    }
    .hd-node-pending .hd-node-latency {
      opacity: 0 !important;
      transform: translateY(-4px) !important;
    }

    /* 2. Active-Now State: Pulsing, Glowing Neon Ring (Current Processing Step) */
    @keyframes hdCurrentPulse {
      0% {
        filter: drop-shadow(0 0 4px var(--node-color)) drop-shadow(0 0 14px var(--node-color));
        stroke-width: 2.8px;
      }
      50% {
        filter: drop-shadow(0 0 10px var(--node-color)) drop-shadow(0 0 26px var(--node-color));
        stroke-width: 3.5px;
      }
      100% {
        filter: drop-shadow(0 0 4px var(--node-color)) drop-shadow(0 0 14px var(--node-color));
        stroke-width: 2.8px;
      }
    }
    .hd-node-active-now .hd-node-rect {
      fill: rgba(15, 23, 42, 0.96) !important;
      stroke: var(--node-color) !important;
      stroke-dasharray: none !important;
      animation: hdCurrentPulse 1.1s ease-in-out infinite !important;
    }
    .hd-node-active-now .hd-node-icon {
      opacity: 1 !important;
      filter: drop-shadow(0 0 8px var(--node-color));
    }
    .hd-node-active-now .hd-node-title {
      fill: #FFFFFF !important;
      opacity: 1 !important;
      font-weight: 900 !important;
    }
    .hd-node-active-now .hd-node-sub {
      fill: var(--node-color) !important;
      opacity: 1 !important;
      font-weight: 700 !important;
    }
    .hd-node-active-now .hd-node-badge {
      opacity: 1 !important;
      transform: scale(1.18) !important;
    }
    .hd-node-active-now .hd-node-latency {
      opacity: 1 !important;
      transform: translateY(0) !important;
    }

    /* 3. Completed State: Solid Vibrant Color & Stable Glow */
    .hd-node-completed .hd-node-rect {
      fill: rgba(15, 23, 42, 0.92) !important;
      stroke: var(--node-color) !important;
      stroke-width: 2.2px !important;
      stroke-dasharray: none !important;
      filter: drop-shadow(0 0 6px rgba(0,0,0,0.7)) drop-shadow(0 0 5px var(--node-color)) !important;
    }
    .hd-node-completed .hd-node-icon {
      opacity: 1 !important;
    }
    .hd-node-completed .hd-node-title {
      fill: #F8FAFC !important;
      opacity: 1 !important;
    }
    .hd-node-completed .hd-node-sub {
      fill: var(--node-color) !important;
      opacity: 0.95 !important;
    }
    .hd-node-completed .hd-node-badge {
      opacity: 1 !important;
      transform: scale(1) !important;
    }
    .hd-node-completed .hd-node-latency {
      opacity: 1 !important;
      transform: translateY(0) !important;
    }

    /* Edges */
    .hd-edge-base {
      transition: opacity 0.3s ease;
    }
    .hd-edge-lit {
      opacity: 0;
      transition: opacity 0.25s ease;
    }
    @keyframes hdDashDraw {
      from { stroke-dashoffset: 600; }
      to { stroke-dashoffset: 0; }
    }
    .hd-edge-active .hd-edge-lit {
      opacity: 1 !important;
      stroke-dasharray: 600;
      animation: hdDashDraw 0.4s ease-out forwards;
    }

    /* Top Strip Pills */
    .hd-strip-pill {
      transition: all 0.3s ease;
      cursor: pointer;
    }
    .hd-strip-pill:hover {
      transform: scale(1.04);
    }
    .hd-strip-pending {
      opacity: 0.3 !important;
      filter: grayscale(0.85) !important;
      background: rgba(30,41,59,0.25) !important;
      border-color: rgba(148,163,184,0.15) !important;
    }
    .hd-strip-active-now {
      opacity: 1 !important;
      filter: none !important;
      transform: scale(1.08) !important;
      box-shadow: 0 0 16px var(--pill-color) !important;
      border-color: var(--pill-color) !important;
      background: rgba(15, 23, 42, 0.95) !important;
    }
    .hd-strip-completed {
      opacity: 1 !important;
      filter: none !important;
      transform: scale(1) !important;
      box-shadow: none !important;
      border-color: var(--pill-color)80 !important;
      background: var(--pill-color)20 !important;
    }
  `;

  // Build inline SVG parts
  const parts = [];

  // Defs (markers, gradients, filters)
  parts.push(`<defs>
    <linearGradient id="hdRedGrad" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#FF2E4D"/><stop offset="100%" stop-color="#B8001F"/>
    </linearGradient>
    <filter id="hdNodeGlow" x="-25%" y="-25%" width="150%" height="150%">
      <feDropShadow dx="0" dy="4" stdDeviation="7" flood-color="#000" flood-opacity="0.6"/>
    </filter>
    <marker id="hdArrowGreen" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="#10B981"/>
    </marker>
    <marker id="hdArrowCyan" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="#06B6D4"/>
    </marker>
    <marker id="hdArrowPurple" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="#A855F7"/>
    </marker>
    <marker id="hdArrowAmber" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="#F59E0B"/>
    </marker>
    <marker id="hdArrowOrange" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="#FB923C"/>
    </marker>
    <marker id="hdArrowSky" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="#0EA5E9"/>
    </marker>
    <marker id="hdArrowTeal" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="#2DD4BF"/>
    </marker>
    <marker id="hdArrowBlue" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="#60A5FA"/>
    </marker>
    <marker id="hdArrowIndigo" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="#818CF8"/>
    </marker>
    <marker id="hdArrowRed" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="#EF4444"/>
    </marker>
    <marker id="hdArrowDim" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
      <path d="M 0 2 L 7 5 L 0 8 z" fill="rgba(148,163,184,0.3)"/>
    </marker>
  </defs>`);

  // Background
  parts.push(`<rect width="100%" height="100%" fill="#08101A" rx="16"/>
  <pattern id="hdGrid" width="28" height="28" patternUnits="userSpaceOnUse">
    <path d="M 28 0 L 0 0 0 28" fill="none" stroke="#ffffff" stroke-width="0.5" opacity="0.04"/>
  </pattern>
  <rect width="100%" height="100%" fill="url(#hdGrid)"/>`);

  function isEdgeExecuted(fromId, toId) {
    const fi = orderedExecuted.indexOf(fromId);
    const ti = orderedExecuted.indexOf(toId);
    if (fi < 0 || ti < 0) return false;
    return true;
  }

  // ── Edges ──
  function edge(d, fromId, toId, color, markerRef, forceActive = null) {
    let isExec = false;
    if (forceActive !== null) {
      isExec = forceActive;
    } else {
      isExec = isEdgeExecuted(fromId, toId);
    }
    if (isExec) {
      return `<g class="hd-edge-wrap" id="hd-edge-${fromId}-${toId}" data-from="${fromId}" data-to="${toId}">
        <path class="hd-edge-base" d="${d}" fill="none" stroke="rgba(148,163,184,0.18)" stroke-width="1.2" stroke-dasharray="4 4" marker-end="url(#hdArrowDim)"/>
        <path class="hd-edge-lit" d="${d}" fill="none" stroke="${color}" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round" marker-end="${markerRef}" style="opacity:0; stroke-dasharray:600; stroke-dashoffset:600;"/>
      </g>`;
    }
    return `<path d="${d}" fill="none" stroke="rgba(148,163,184,0.18)" stroke-width="1.2" stroke-dasharray="4 4" marker-end="url(#hdArrowDim)"/>`;
  }

  // Main flow edges
  const hasFirst = orderedExecuted.length > 0 && orderedExecuted[0] === 'input_guard';
  parts.push(edge('M 400 38 L 400 48', 'START_VIRTUAL', 'input_guard', '#10B981', 'url(#hdArrowGreen)', hasFirst));

  const hasIntent = executedIds.has('input_guard') && executedIds.has('intent');
  parts.push(edge('M 400 98 L 400 118', 'input_guard', 'intent', '#06B6D4', 'url(#hdArrowCyan)', hasIntent));

  // ── Input Guard -> Output Guard (Blocked prompt injection bypass arrow) ──
  const isInputBlocked = executedIds.has('input_guard') && !executedIds.has('intent') && executedIds.has('output_guard');
  parts.push(edge('M 520 73 H 765 V 765 H 520', 'input_guard', 'output_guard', '#EF4444', 'url(#hdArrowRed)', isInputBlocked));

  if (isInputBlocked) {
    parts.push(`
      <g id="hd-badge-blocked" class="hd-badge-pop" style="opacity:0; transition:opacity 0.4s ease;" transform="translate(765, 410)">
        <rect x="-65" y="-13" width="130" height="26" rx="6" fill="#1E1B4B" stroke="#EF4444" stroke-width="1.4" filter="url(#hdNodeGlow)"/>
        <text x="0" y="4" text-anchor="middle" font-family="'Cairo',sans-serif" font-size="9.5" font-weight="800" fill="#FCA5A5">
          🚫 ${isAr ? 'حظر وتخطي مباشر' : 'BLOCKED / BYPASS'}
        </text>
      </g>
    `);
  }

  // Fast greeting
  const greetPath = executedIds.has('intent') && executedIds.has('greeting');
  parts.push(edge('M 280 145 H 130 V 188', 'intent', 'greeting', '#F59E0B', 'url(#hdArrowAmber)', greetPath));
  parts.push(edge('M 130 238 V 765 H 280', 'greeting', 'output_guard', '#F59E0B', 'url(#hdArrowAmber)', greetPath && executedIds.has('output_guard')));

  // Safe response
  const safePath = executedIds.has('intent') && executedIds.has('safe_response');
  parts.push(edge('M 520 145 H 670 V 188', 'intent', 'safe_response', '#F43F5E', 'url(#hdArrowRed)', safePath));
  parts.push(edge('M 670 238 V 765 H 520', 'safe_response', 'output_guard', '#F43F5E', 'url(#hdArrowRed)', safePath && executedIds.has('output_guard')));

  // Main center path
  parts.push(edge('M 400 168 L 400 188', 'intent', 'understand', '#818CF8', 'url(#hdArrowIndigo)', executedIds.has('intent') && executedIds.has('understand')));
  parts.push(edge('M 400 238 L 400 258', 'understand', 'strategy_router', '#A855F7', 'url(#hdArrowPurple)', executedIds.has('understand') && executedIds.has('strategy_router')));
  
  const clarifyPath = executedIds.has('clarify');
  parts.push(edge('M 275 285 H 130 V 334', 'strategy_router', 'clarify', '#F59E0B', 'url(#hdArrowAmber)', clarifyPath));
  parts.push(edge('M 130 383 V 765 H 280', 'clarify', 'output_guard', '#F59E0B', 'url(#hdArrowAmber)', clarifyPath && executedIds.has('output_guard')));
  
  const hasTools = executedIds.has('mcp_tool');
  parts.push(edge('M 400 309 L 400 333', 'strategy_router', 'mcp_tool', '#FB923C', 'url(#hdArrowOrange)', hasTools));
  parts.push(edge('M 275 285 H 240 V 430 H 275', 'strategy_router', 'query_rewrite', '#0EA5E9', 'url(#hdArrowSky)', executedIds.has('strategy_router') && executedIds.has('query_rewrite') && !hasTools));
  parts.push(edge('M 400 384 L 400 407', 'mcp_tool', 'query_rewrite', '#0EA5E9', 'url(#hdArrowSky)', hasTools && executedIds.has('query_rewrite')));
  parts.push(edge('M 400 453 L 400 476', 'query_rewrite', 'retrieve', '#10B981', 'url(#hdArrowGreen)', executedIds.has('query_rewrite') && executedIds.has('retrieve')));
  parts.push(edge('M 400 524 L 400 561', 'retrieve', 'generate', '#C084FC', 'url(#hdArrowPurple)', executedIds.has('retrieve') && executedIds.has('generate')));
  parts.push(edge('M 400 609 L 400 651', 'generate', 'validate', '#2DD4BF', 'url(#hdArrowTeal)', executedIds.has('generate') && executedIds.has('validate')));
  
  const isRepair = executedIds.has('validate') && stepMap.get('validate')?.details?.validation_result === 'REPAIR';
  parts.push(edge('M 275 675 H 220 V 585 H 270', 'validate', 'generate', '#2DD4BF', 'url(#hdArrowTeal)', isRepair));
  parts.push(edge('M 400 699 L 400 742', 'validate', 'output_guard', '#60A5FA', 'url(#hdArrowBlue)', executedIds.has('validate') && executedIds.has('output_guard')));
  parts.push(edge('M 400 788 L 400 820', 'output_guard', 'END_VIRTUAL', '#FF2E4D', 'url(#hdArrowRed)', executedIds.has('output_guard')));

  // ── Terminals ──
  parts.push(`<g id="hd-term-start" style="filter:drop-shadow(0 0 8px rgba(16,185,129,0.5)); transition:all 0.3s ease;">
    <rect id="hd-term-start-rect" x="340" y="12" width="120" height="26" rx="13" fill="#1E293B" stroke="#10B981" stroke-width="1.5"/>
    <text x="400" y="30" text-anchor="middle" font-family="'Cairo',sans-serif" font-size="11" font-weight="800" fill="#F8FAFC">🚀 START</text>
  </g>`);
  
  parts.push(`<g id="hd-term-end" style="opacity:0.3; transition:all 0.5s ease;">
    <rect id="hd-term-end-rect" x="320" y="822" width="160" height="28" rx="14" fill="#1E293B" stroke="rgba(255,255,255,0.2)" stroke-width="1.3"/>
    <text id="hd-term-end-text" x="400" y="841" text-anchor="middle" font-family="'Cairo',sans-serif" font-size="11" font-weight="800" fill="#94A3B8">🏁 ${isAr ? 'الإجابة النهائية' : 'FINAL OUTPUT'}</text>
  </g>`);

  // ── Nodes ──
  // Idle nodes first
  GN.forEach(n => {
    if (!executedIds.has(n.id)) {
      const lx = n.cx - n.w / 2, ly = n.cy - n.h / 2;
      parts.push(`<g class="hd-node-idle" id="hd-node-${n.id}">
        <rect x="${lx}" y="${ly}" width="${n.w}" height="${n.h}" rx="12"
              fill="rgba(15,23,42,0.35)" stroke="rgba(148,163,184,0.18)" stroke-width="1.2" stroke-dasharray="4 3"/>
        <text x="${lx+24}" y="${n.cy+5}" font-size="16" text-anchor="middle" opacity="0.3">${n.icon}</text>
        <text x="${lx+46}" y="${n.cy-4}" font-family="'Cairo',sans-serif" font-size="11" font-weight="700" fill="rgba(148,163,184,0.4)">${isAr ? n.ar : n.en}</text>
        <text x="${lx+46}" y="${n.cy+12}" font-family="'Cairo',sans-serif" font-size="8.5" font-weight="500" fill="rgba(148,163,184,0.25)">${n.sub}</text>
      </g>`);
    }
  });

  // Executed nodes (rendered with classes for JS sequential control)
  GN.forEach(n => {
    if (!executedIds.has(n.id)) return;
    const seq = seqMap.get(n.id);
    const step = stepMap.get(n.id) || {};
    const latency = fmtMs(step.latency_ms);
    const lx = n.cx - n.w / 2, ly = n.cy - n.h / 2;

    parts.push(`<g class="hd-node-group hd-node-pending" id="hd-node-${n.id}" data-node-id="${n.id}" data-seq="${seq}" style="--node-color:${n.color};">
      <rect class="hd-node-rect" x="${lx}" y="${ly}" width="${n.w}" height="${n.h}" rx="12"/>
      <text class="hd-node-icon" x="${lx+24}" y="${n.cy+5}" font-size="16" text-anchor="middle">${n.icon}</text>
      <text class="hd-node-title" x="${lx+46}" y="${n.cy-4}" font-family="'Cairo',sans-serif" font-size="11.5" font-weight="800">${isAr ? n.ar : n.en}</text>
      <text class="hd-node-sub" x="${lx+46}" y="${n.cy+12}" font-family="'Cairo',sans-serif" font-size="8.5" font-weight="600">${n.sub}</text>
      ${seq != null ? `<g class="hd-node-badge" transform="translate(${n.cx+n.w/2-12},${n.cy-n.h/2+2})">
        <circle cx="0" cy="0" r="10" fill="${n.color}"/>
        <text x="0" y="3.5" text-anchor="middle" font-family="'Cairo',sans-serif" font-size="10" font-weight="900" fill="#FFF">${seq}</text>
      </g>` : ''}
      ${latency ? `<g class="hd-node-latency" transform="translate(${n.cx-n.w/2+16},${n.cy-n.h/2+2})">
        <rect x="-6" y="-8" width="${latency.length*7+14}" height="16" rx="8" fill="rgba(10,15,30,0.92)" stroke="${n.color}" stroke-width="1.1"/>
        <text x="${(latency.length*7)/2+1}" y="3.5" text-anchor="middle" font-family="monospace" font-size="8.5" font-weight="800" fill="${n.color}">⏱ ${latency}</text>
      </g>` : ''}
    </g>`);
  });

  // ── Build modal HTML ──
  const svgHtml = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W} ${H}" width="100%" style="display:block; max-height:82vh;"
      id="hd-animated-svg">
    ${parts.join('\n')}
  </svg>`;

  modal = document.createElement('div');
  modal.id = 'hd-graph-modal';
  modal.style.cssText = 'position:fixed; inset:0; z-index:99999; background:rgba(4,8,18,0.97); display:flex; flex-direction:column; backdrop-filter:blur(16px);';

  const totalMs = totalLatency > 0 ? fmtMs(totalLatency) : '';

  modal.innerHTML = `
    <style>${animCss}</style>
    <div style="display:flex; justify-content:space-between; align-items:center; padding:12px 24px; background:#0A1020; border-bottom:1px solid #1E293B; z-index:10; flex-wrap:wrap; gap:8px;">
      <div style="display:flex; align-items:center; gap:12px;">
        <span style="font-size:22px;">🧭</span>
        <div>
          <h3 style="margin:0; font-size:15px; font-weight:800; color:#F8FAFC; font-family:'Cairo',sans-serif;">
            ${isAr ? 'مخطط المعالجة المتحرك — الطلب الحالي' : 'Animated Execution Pipeline — This Request'}
          </h3>
          <span style="font-size:11px; color:#64748B;">
            ${workflow.length > 0
              ? `${workflow.length} ${isAr ? 'مراحل منفذة' : 'stages executed'}${totalMs ? ` · ⏱️ ${totalMs}` : ''}`
              : (isAr ? 'لا توجد بيانات workflow للطلب الحالي' : 'No workflow data for this request yet')}
          </span>
        </div>
      </div>
      <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
        ${workflow.length > 0 ? `
        <button id="hd-replay-btn" title="${isAr ? 'إعادة تشغيل خطوة بخطوة' : 'Replay Step-by-Step'}"
          style="background:#1E3A5F; border:1px solid #38BDF8; color:#38BDF8; padding:6px 14px; border-radius:8px; font-weight:800; font-size:12px; cursor:pointer; display:flex; align-items:center; gap:5px; transition:all 0.2s;">
          ▶ ${isAr ? 'إعادة تشغيل' : 'Replay'}
        </button>
        <button id="hd-showall-btn" title="${isAr ? 'إضاءة جميع الخطوات فوراً' : 'Show All Steps Instantly'}"
          style="background:#1E293B; border:1px solid #475569; color:#94A3B8; padding:6px 12px; border-radius:8px; font-weight:700; font-size:11.5px; cursor:pointer; display:flex; align-items:center; gap:4px; transition:all 0.2s;">
          ⚡ ${isAr ? 'عرض الكل' : 'Show All'}
        </button>` : ''}
        <div style="display:flex; align-items:center; background:#1E293B; border-radius:8px; padding:3px 6px; border:1px solid #334155;">
          <button id="hd-zoom-in" style="background:transparent; border:none; color:#F8FAFC; font-size:16px; width:30px; height:28px; cursor:pointer;">➕</button>
          <span id="hd-zoom-lv" style="font-size:12px; font-weight:700; color:#38BDF8; min-width:46px; text-align:center;">100%</span>
          <button id="hd-zoom-out" style="background:transparent; border:none; color:#F8FAFC; font-size:16px; width:30px; height:28px; cursor:pointer;">➖</button>
          <button id="hd-zoom-reset" style="background:transparent; border:none; color:#94A3B8; font-size:11px; padding:0 8px; height:28px; cursor:pointer;">🔄 ${isAr ? 'ضبط' : 'Reset'}</button>
        </div>
        <a href="/assets/agentic_rag_graph.svg" download="eand_egypt_architecture.svg"
          style="text-decoration:none; background:#0284C7; color:#FFFFFF; padding:6px 14px; border-radius:8px; font-weight:800; font-size:12px; display:flex; align-items:center; gap:5px;">
          ⬇️ ${isAr ? 'تحميل' : 'Download SVG'}
        </a>
        <button id="hd-close-btn" style="background:#EF4444; border:none; color:#FFFFFF; padding:6px 16px; border-radius:8px; font-weight:800; font-size:13px; cursor:pointer;">
          ✕ ${isAr ? 'إغلاق' : 'Close'}
        </button>
      </div>
    </div>

    ${workflow.length > 0 ? `
    <div id="hd-step-strip" style="display:flex; align-items:center; gap:6px; padding:8px 24px; background:#050D1A; border-bottom:1px solid #1E293B; overflow-x:auto; flex-shrink:0; scrollbar-width:thin;">
      ${workflow.map((s, i) => {
        const n = GN.find(g => g.id === s.node);
        const color = n ? n.color : '#10B981';
        const lbl = n ? (isAr ? n.ar : n.en) : s.node;
        const icon = n ? n.icon : '●';
        const lat = fmtMs(s.latency_ms);
        return `<span id="hd-strip-${i}" class="hd-strip-pill hd-strip-pending" data-step-idx="${i}" data-node-id="${s.node}" style="--pill-color:${color}; display:inline-flex; align-items:center; gap:4px; padding:3px 10px; border-radius:20px; border:1px solid ${color}40; background:${color}15; color:${color}; font-size:11px; font-weight:700; white-space:nowrap; flex-shrink:0;">
          <span style="background:${color}; color:#fff; border-radius:50%; width:17px; height:17px; display:inline-flex; align-items:center; justify-content:center; font-size:9px; font-weight:900;">${i+1}</span>
          ${icon} ${lbl}
          ${lat ? `<span style="font-family:monospace; font-size:9px; opacity:0.8;">⏱${lat}</span>` : ''}
        </span>
        ${i < workflow.length - 1 ? `<span style="color:#334155; flex-shrink:0;">→</span>` : ''}`;
      }).join('')}
    </div>` : ''}

    <div id="hd-viewport" style="flex:1; overflow:hidden; position:relative; display:flex; justify-content:center; align-items:flex-start; cursor:grab; background:#050D1A; padding-top:16px;">
      <div id="hd-container" style="transform-origin:top center; transition:transform 0.12s ease-out;">
        <div id="hd-svg-wrap" style="width:min(90vw, 760px); background:#08101A; border-radius:16px; border:1px solid #1E293B; box-shadow:0 20px 60px rgba(0,0,0,0.8); overflow:hidden; padding:0;">
          ${svgHtml}
        </div>
      </div>
    </div>
  `;

  document.body.appendChild(modal);

  // ── Step-by-Step Animation Engine ──
  let animTimer = null;
  let isPlaying = false;
  const replayBtn = document.getElementById('hd-replay-btn');
  const showAllBtn = document.getElementById('hd-showall-btn');

  function cleanupAnimation() {
    if (animTimer) {
      clearTimeout(animTimer);
      animTimer = null;
    }
    isPlaying = false;
  }

  function resetAllToPending() {
    cleanupAnimation();

    // Reset Terminals
    const termEnd = document.getElementById('hd-term-end');
    if (termEnd) {
      termEnd.style.opacity = '0.25';
      termEnd.style.filter = 'none';
      const endRect = document.getElementById('hd-term-end-rect');
      if (endRect) endRect.setAttribute('fill', '#1E293B');
      const endText = document.getElementById('hd-term-end-text');
      if (endText) endText.setAttribute('fill', '#94A3B8');
    }

    // Reset All Nodes
    orderedExecuted.forEach(id => {
      const g = document.getElementById(`hd-node-${id}`);
      if (g) {
        g.classList.remove('hd-node-active-now', 'hd-node-completed');
        g.classList.add('hd-node-pending');
      }
    });

    // Reset All Edges
    const edgeWraps = modal.querySelectorAll('.hd-edge-wrap');
    edgeWraps.forEach(ew => {
      ew.classList.remove('hd-edge-active');
      const lit = ew.querySelector('.hd-edge-lit');
      if (lit) {
        lit.style.opacity = '0';
        lit.style.strokeDashoffset = '600';
      }
    });

    // Reset Blocked Badge if exists
    const blockedBadge = document.getElementById('hd-badge-blocked');
    if (blockedBadge) blockedBadge.style.opacity = '0';

    // Reset Top Strip Pills
    const pills = modal.querySelectorAll('.hd-strip-pill');
    pills.forEach(p => {
      p.classList.remove('hd-strip-active-now', 'hd-strip-completed');
      p.classList.add('hd-strip-pending');
    });

    if (replayBtn) {
      replayBtn.innerHTML = `▶ ${isAr ? 'إعادة تشغيل' : 'Replay'}`;
    }
  }

  function activateStep(idx) {
    if (idx < 0 || idx >= orderedExecuted.length) return;
    const nodeId = orderedExecuted[idx];
    const prevNodeId = idx > 0 ? orderedExecuted[idx - 1] : 'START_VIRTUAL';

    // 1. Transition previous step to completed
    if (idx > 0) {
      const prevG = document.getElementById(`hd-node-${orderedExecuted[idx - 1]}`);
      if (prevG) {
        prevG.classList.remove('hd-node-active-now', 'hd-node-pending');
        prevG.classList.add('hd-node-completed');
      }
      const prevPill = document.getElementById(`hd-strip-${idx - 1}`);
      if (prevPill) {
        prevPill.classList.remove('hd-strip-active-now', 'hd-strip-pending');
        prevPill.classList.add('hd-strip-completed');
      }
    }

    // 2. Light up incoming edge leading to this node
    const edgeWrap = modal.querySelector(`.hd-edge-wrap[data-from="${prevNodeId}"][data-to="${nodeId}"]`);
    if (edgeWrap) {
      edgeWrap.classList.add('hd-edge-active');
      const lit = edgeWrap.querySelector('.hd-edge-lit');
      if (lit) lit.style.opacity = '1';
    }

    // Handle blocked prompt injection edge if applicable
    if (nodeId === 'output_guard' && isInputBlocked) {
      const blockedEdge = modal.querySelector(`.hd-edge-wrap[data-from="input_guard"][data-to="output_guard"]`);
      if (blockedEdge) blockedEdge.classList.add('hd-edge-active');
      const blockedBadge = document.getElementById('hd-badge-blocked');
      if (blockedBadge) blockedBadge.style.opacity = '1';
    }

    // 3. Light up current node in vibrant glowing active state
    const currentG = document.getElementById(`hd-node-${nodeId}`);
    if (currentG) {
      currentG.classList.remove('hd-node-pending', 'hd-node-completed');
      currentG.classList.add('hd-node-active-now');
    }

    // 4. Light up strip pill & auto-scroll strip
    const currentPill = document.getElementById(`hd-strip-${idx}`);
    if (currentPill) {
      currentPill.classList.remove('hd-strip-pending', 'hd-strip-completed');
      currentPill.classList.add('hd-strip-active-now');
      const strip = document.getElementById('hd-step-strip');
      if (strip) {
        const pLeft = currentPill.offsetLeft;
        const sWidth = strip.clientWidth;
        strip.scrollTo({ left: pLeft - sWidth / 2 + 50, behavior: 'smooth' });
      }
    }
  }

  function finishAnimation() {
    // Settle last node to completed
    if (orderedExecuted.length > 0) {
      const lastNodeId = orderedExecuted[orderedExecuted.length - 1];
      const lastG = document.getElementById(`hd-node-${lastNodeId}`);
      if (lastG) {
        lastG.classList.remove('hd-node-active-now', 'hd-node-pending');
        lastG.classList.add('hd-node-completed');
      }
      const lastPill = document.getElementById(`hd-strip-${orderedExecuted.length - 1}`);
      if (lastPill) {
        lastPill.classList.remove('hd-strip-active-now', 'hd-strip-pending');
        lastPill.classList.add('hd-strip-completed');
      }
      // Light up final edge to END_VIRTUAL
      const endEdge = modal.querySelector(`.hd-edge-wrap[data-from="${lastNodeId}"][data-to="END_VIRTUAL"]`);
      if (endEdge) {
        endEdge.classList.add('hd-edge-active');
        const lit = endEdge.querySelector('.hd-edge-lit');
        if (lit) lit.style.opacity = '1';
      }
    }

    // Light up END terminal
    const termEnd = document.getElementById('hd-term-end');
    if (termEnd) {
      termEnd.style.opacity = '1';
      termEnd.style.filter = 'drop-shadow(0 0 14px #FF2E4D)';
      const endRect = document.getElementById('hd-term-end-rect');
      if (endRect) endRect.setAttribute('fill', 'url(#hdRedGrad)');
      const endText = document.getElementById('hd-term-end-text');
      if (endText) endText.setAttribute('fill', '#FFFFFF');
    }

    isPlaying = false;
    if (replayBtn) {
      replayBtn.innerHTML = `▶ ${isAr ? 'إعادة تشغيل' : 'Replay'}`;
    }
  }

  function playSequential() {
    resetAllToPending();
    if (orderedExecuted.length === 0) return;

    isPlaying = true;
    if (replayBtn) {
      replayBtn.innerHTML = `⏳ ${isAr ? 'جاري العرض...' : 'Replaying...'}`;
    }

    let i = 0;
    function next() {
      if (!isPlaying) return;
      if (i < orderedExecuted.length) {
        activateStep(i);
        i++;
        animTimer = setTimeout(next, STEP_DURATION_MS);
      } else {
        finishAnimation();
      }
    }
    // Start after slight delay so user sees initial dimmed pending state
    animTimer = setTimeout(next, 160);
  }

  function showAllInstantly() {
    cleanupAnimation();
    orderedExecuted.forEach((id, idx) => {
      activateStep(idx);
      const g = document.getElementById(`hd-node-${id}`);
      if (g) {
        g.classList.remove('hd-node-active-now', 'hd-node-pending');
        g.classList.add('hd-node-completed');
      }
      const p = document.getElementById(`hd-strip-${idx}`);
      if (p) {
        p.classList.remove('hd-strip-active-now', 'hd-strip-pending');
        p.classList.add('hd-strip-completed');
      }
    });
    finishAnimation();
  }

  // Hook Replay and Show All buttons
  if (replayBtn) {
    replayBtn.onclick = () => playSequential();
  }
  if (showAllBtn) {
    showAllBtn.onclick = () => showAllInstantly();
  }

  // Interactive clicks on step pills in strip or nodes
  modal.querySelectorAll('.hd-strip-pill').forEach(pill => {
    pill.onclick = () => {
      const targetIdx = parseInt(pill.getAttribute('data-step-idx'), 10);
      if (isNaN(targetIdx)) return;
      cleanupAnimation();
      for (let s = 0; s <= targetIdx; s++) {
        activateStep(s);
        if (s < targetIdx) {
          const g = document.getElementById(`hd-node-${orderedExecuted[s]}`);
          if (g) {
            g.classList.remove('hd-node-active-now', 'hd-node-pending');
            g.classList.add('hd-node-completed');
          }
          const p = document.getElementById(`hd-strip-${s}`);
          if (p) {
            p.classList.remove('hd-strip-active-now', 'hd-strip-pending');
            p.classList.add('hd-strip-completed');
          }
        }
      }
    };
  });

  modal.querySelectorAll('.hd-node-group').forEach(nodeGroup => {
    nodeGroup.onclick = () => {
      const nid = nodeGroup.getAttribute('data-node-id');
      const idx = orderedExecuted.indexOf(nid);
      if (idx >= 0) {
        const pill = document.getElementById(`hd-strip-${idx}`);
        if (pill) pill.click();
      }
    };
  });

  // Start sequential step-by-step animation automatically on open!
  if (workflow.length > 0) {
    playSequential();
  }

  // ── Pan & Zoom Controls ──
  let zoom = 1, px = 0, py = 0, drag = false, sx = 0, sy = 0;
  const container = document.getElementById('hd-container');
  const viewport = document.getElementById('hd-viewport');
  const zoomLv = document.getElementById('hd-zoom-lv');

  function applyZoom() {
    container.style.transform = `translate(${px}px, ${py}px) scale(${zoom})`;
    if (zoomLv) zoomLv.textContent = `${Math.round(zoom * 100)}%`;
  }

  document.getElementById('hd-zoom-in').onclick = () => { zoom = Math.min(zoom + 0.25, 4); applyZoom(); };
  document.getElementById('hd-zoom-out').onclick = () => { zoom = Math.max(zoom - 0.25, 0.35); applyZoom(); };
  document.getElementById('hd-zoom-reset').onclick = () => { zoom = 1; px = 0; py = 0; applyZoom(); };
  
  function closeModal() {
    cleanupAnimation();
    modal.remove();
    window.removeEventListener('keydown', onKey);
  }

  document.getElementById('hd-close-btn').onclick = closeModal;

  viewport.addEventListener('wheel', e => {
    e.preventDefault();
    zoom = Math.max(0.35, Math.min(4, zoom + (e.deltaY < 0 ? 0.15 : -0.15)));
    applyZoom();
  }, { passive: false });

  viewport.addEventListener('mousedown', e => {
    if (e.target.closest('button, a')) return;
    drag = true; sx = e.clientX - px; sy = e.clientY - py;
    viewport.style.cursor = 'grabbing';
  });
  window.addEventListener('mousemove', e => {
    if (!drag) return;
    px = e.clientX - sx; py = e.clientY - sy; applyZoom();
  });
  window.addEventListener('mouseup', () => {
    if (drag) { drag = false; if (viewport) viewport.style.cursor = 'grab'; }
  });

  // ESC to close
  const onKey = e => { if (e.key === 'Escape') closeModal(); };
  window.addEventListener('keydown', onKey);
};

// Auto-initialize if on standalone chatbot page
if (typeof document !== 'undefined') {
  function checkChatbotPageInit() {
    if (document.body && document.body.classList.contains('chatbot-page')) {
      initHeaderActions();
      initModelSelector();
      if (panel) panel.classList.add('open');
      if (input) {
        try { input.focus({ preventScroll: true }); } catch (_) { input.focus(); }
      }
    }
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', checkChatbotPageInit);
  } else {
    checkChatbotPageInit();
  }
}



