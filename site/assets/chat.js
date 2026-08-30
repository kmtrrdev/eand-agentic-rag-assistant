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

function isArabicText(str) {
  if (!str) return false;

  const arabicMatches = str.match(/[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]/g);
  const arabicCount = arabicMatches ? arabicMatches.length : 0;
  const latinMatches = str.match(/[a-zA-Z]/g);
  const latinCount = latinMatches ? latinMatches.length : 0;

  return arabicCount > 0 && arabicCount >= latinCount * 0.2;
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
      switchInspectorTab(tab);
    });
  });
}

function openInspector(tab, data) {
  initInspector();
  if (!inspectorEl) return;

  currentInspectorData = data || {};
  switchInspectorTab(tab || 'workflow');
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

  /* ── 2. Full 13-Node Pipeline Definition (Topological Graph Layout) ───── */
  const GRAPH_NODES = [
    // Top Row
    { id: 'input_guard',     icon: '🛡️', labelEn: '1. Input Guardrail',      labelAr: '١. حارس المدخلات والأمان',    subEn: 'Prompt Injection Defense',      subAr: 'كشف وحجب هجمات الحقن',       cx: 400, cy: 75,  w: 240, h: 48, color: '#EF4444' },
    { id: 'intent',          icon: '🎯', labelEn: '2. Intent Classifier',    labelAr: '٢. تصنيف النية والتوجيه',     subEn: 'Greeting / Scope / Inquiry',    subAr: 'تحية / استفسار / خروج نطاق',  cx: 400, cy: 145, w: 240, h: 48, color: '#06B6D4' },
    
    // Fast & Safe Branches (Left & Right)
    { id: 'greeting',        icon: '⚡', labelEn: '3. Fast Greeting',        labelAr: '٣. رد ترحيبي فوري',           subEn: 'Instant Warm Reply',            subAr: 'رد فوري دون استرجاع',        cx: 130, cy: 215, w: 190, h: 46, color: '#F59E0B' },
    { id: 'safe_response',   icon: '🛑', labelEn: 'Safe Response',           labelAr: 'المسار والرد الآمن',          subEn: 'Out-of-Scope & 111 Support',    subAr: 'خدمات غير مدعومة / تحويل',   cx: 670, cy: 215, w: 190, h: 46, color: '#F43F5E' },
    
    // Core Pipeline
    { id: 'understand',      icon: '🧠', labelEn: '3. Query Understanding',  labelAr: '٣. تحليل وتنميط الاستفسار',   subEn: 'Entity & Budget Profiling',     subAr: 'استخراج الباقة والميزانية',  cx: 400, cy: 215, w: 240, h: 48, color: '#818CF8' },
    { id: 'strategy_router', icon: '🧭', labelEn: '4. Strategy Router',      labelAr: '٤. موجه استراتيجية الرد',     subEn: 'MCP_EXACT / CALC / RAG_ONLY',   subAr: 'توجيه المسار الحتمي',        cx: 400, cy: 285, w: 250, h: 50, color: '#A855F7' },
    
    // Split Rails: Left = MCP Ground Truth, Right = Parallel Hybrid RAG
    { id: 'mcp_tool',        icon: '🛠️', labelEn: '5. MCP Ground Truth',     labelAr: '٥. الحقيقة المؤكدة MCP',      subEn: 'Deterministic Fact Engine',     subAr: 'الأسعار الرسمية وأكواد USSD',cx: 230, cy: 365, w: 220, h: 50, color: '#FB923C' },
    { id: 'retrieve',        icon: '🔍', labelEn: '6. Parallel Hybrid RAG',  labelAr: '٦. استرجاع هجين متوازي',      subEn: 'Chroma Dense + BM25 Sparse',    subAr: 'فكتور + كلمات مفتاحية',      cx: 570, cy: 365, w: 230, h: 50, color: '#10B981' },
    
    // RAG Evaluator & Targeted Rewrite Loop
    { id: 'evaluate',        icon: '📊', labelEn: '7. Retrieval Evaluator',  labelAr: '٧. تقييم جودة الاسترجاع',     subEn: 'Multi-Factor Quality Score',    subAr: 'فحص التطابق والتقدم',        cx: 570, cy: 440, w: 230, h: 48, color: '#38BDF8' },
    { id: 'rewrite',         icon: '🔄', labelEn: '8. Targeted Rewrite',     labelAr: '٨. إعادة الصياغة الذاتية',    subEn: 'Max 1 Rewrite • Entity Guard',  subAr: 'محاولة واحدة مع حفظ الكيانات',cx: 370, cy: 440, w: 170, h: 46, color: '#EC4899' },
    
    // Generation -> 3-Tier Fact Validation -> Output Guard (Sanitization)
    { id: 'generate',        icon: '✍️', labelEn: '8. Grounded Generation',  labelAr: '٨. توليد الإجابة الصارمة',    subEn: 'MCP Supremacy & Targeted Repair',subAr: 'أولوية MCP وإصلاح مستهدف',  cx: 400, cy: 520, w: 250, h: 50, color: '#C084FC' },
    { id: 'validate',        icon: '⚖️', labelEn: '9. 3-Tier Fact Validator',labelAr: '٩. فحص وتدقيق الحقائق',    subEn: 'PASS | REPAIR (Max 1) | REFUSE',subAr: 'مطابقة الأرقام والأسعار 100%',cx: 400, cy: 595, w: 250, h: 50, color: '#34D399' },
    { id: 'output_guard',    icon: '🔒', labelEn: '10. Output Guardrail',    labelAr: '١٠. حارس المخرجات والتنقيح',   subEn: 'Secret Scrubbing & Pre-Flight Gate',subAr: 'تنظيف الوسوم والسرية',       cx: 400, cy: 670, w: 240, h: 48, color: '#60A5FA' },
  ];

  const nodeById = {};
  GRAPH_NODES.forEach(n => { nodeById[n.id] = n; });

  const SVG_W = 800;
  const SVG_H = 780;

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
        <rect x="-6" y="-8" width="${latency.length * 7 + 12}" height="15" rx="7.5" fill="rgba(0,0,0,0.7)" stroke="${n.color}" stroke-width="1"/>
        <text x="${(latency.length * 7) / 2}" y="3" text-anchor="middle" font-family="monospace" font-size="9" font-weight="700" fill="${n.color}">${latency}</text>
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

  function renderEdge(d, isTraversed, color = '#10B981') {
    const stroke = isTraversed ? color : 'rgba(148, 163, 184, 0.2)';
    const sw = isTraversed ? 2.5 : 1.2;
    const dash = isTraversed ? 'none' : '4 4';
    const marker = isTraversed ? `url(#arrowActive)` : `url(#arrowDim)`;
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
      <marker id="arrowActive" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
        <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="#10B981"/>
      </marker>
      <marker id="arrowDim" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
        <path d="M 0 2 L 7 5 L 0 8 z" fill="rgba(148, 163, 184, 0.3)"/>
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
  svgParts.push(renderEdge('M 400 38 L 400 51', executedIds.has('input_guard'), '#10B981'));

  // Input Guard -> Intent (Allowed)
  svgParts.push(renderEdge('M 400 99 L 400 121', executedIds.has('input_guard') && executedIds.has('intent'), '#10B981'));

  // Input Guard -> Output Guard (Blocked attack bypass)
  const isInputBlocked = executedIds.has('input_guard') && !executedIds.has('intent') && executedIds.has('output_guard');
  svgParts.push(renderEdge('M 520 75 H 770 V 595 H 520', isInputBlocked, '#EF4444'));

  // Intent -> Greeting (Branch Left)
  const isGreetingPath = executedIds.has('intent') && executedIds.has('greeting');
  svgParts.push(renderEdge('M 280 145 H 130 V 192', isGreetingPath, '#F59E0B'));

  // Intent -> Safe Response (Branch Right)
  const isSafePath = executedIds.has('intent') && executedIds.has('safe_response');
  svgParts.push(renderEdge('M 520 145 H 670 V 192', isSafePath, '#F43F5E'));

  // Intent -> Understand (Center Path)
  const isUnderstandPath = executedIds.has('intent') && executedIds.has('understand');
  svgParts.push(renderEdge('M 400 169 L 400 191', isUnderstandPath, '#06B6D4'));

  // Greeting -> Output Guard (Direct to finish)
  svgParts.push(renderEdge('M 130 238 V 595 H 280', isGreetingPath && executedIds.has('output_guard'), '#F59E0B'));

  // Safe Response -> Output Guard (Direct to finish)
  svgParts.push(renderEdge('M 670 238 V 595 H 520', isSafePath && executedIds.has('output_guard'), '#F43F5E'));

  // Understand -> Strategy Router
  const isStrategyPath = executedIds.has('understand') && executedIds.has('strategy_router');
  svgParts.push(renderEdge('M 400 239 L 400 260', isStrategyPath, '#A855F7'));

  // Strategy Router -> MCP Tool (Left Rail)
  const isMcpPath = executedIds.has('strategy_router') && executedIds.has('mcp_tool');
  svgParts.push(renderEdge('M 275 285 H 230 V 340', isMcpPath, '#FB923C'));

  // Strategy Router -> Retrieve (Right Rail)
  const isRagPath = executedIds.has('strategy_router') && executedIds.has('retrieve');
  svgParts.push(renderEdge('M 525 285 H 570 V 340', isRagPath, '#10B981'));

  // MCP Tool -> Direct to Generate (Short Circuit)
  const isMcpDirectToGen = executedIds.has('mcp_tool') && !executedIds.has('retrieve') && executedIds.has('generate');
  svgParts.push(renderEdge('M 230 390 V 520 H 275', isMcpDirectToGen, '#FB923C'));

  // MCP Tool -> Retrieve (MCP_PLUS_RAG)
  const isMcpPlusRag = executedIds.has('mcp_tool') && executedIds.has('retrieve');
  svgParts.push(renderEdge('M 340 365 H 455', isMcpPlusRag, '#FB923C'));

  // Retrieve -> Evaluate
  const isEvalPath = executedIds.has('retrieve') && executedIds.has('evaluate');
  svgParts.push(renderEdge('M 570 390 L 570 416', isEvalPath, '#0EA5E9'));

  // Evaluate -> Rewrite (Weak retrieval loop)
  const isRewritePath = executedIds.has('evaluate') && executedIds.has('rewrite');
  svgParts.push(renderEdge('M 455 440 H 455', isRewritePath, '#EC4899'));

  // Rewrite -> Retrieve (Loop back)
  svgParts.push(renderEdge('M 370 417 V 365 H 455', isRewritePath, '#EC4899'));

  // Evaluate -> Generate (Good retrieval path)
  const isGenPath = executedIds.has('evaluate') && executedIds.has('generate');
  svgParts.push(renderEdge('M 570 464 V 520 H 525', isGenPath, '#A855F7'));

  // Generate -> Validate
  const isGenToVal = executedIds.has('generate') && executedIds.has('validate');
  svgParts.push(renderEdge('M 400 545 L 400 570', isGenToVal, '#C084FC'));

  // Validate -> Targeted Repair (Loop back to Generate)
  const isRepairPath = executedIds.has('validate') && stepMap.get('validate')?.details?.validation_result === 'REPAIR';
  svgParts.push(renderEdge('M 275 595 H 90 V 520 H 275', isRepairPath, '#A855F7'));

  // Validate -> Output Guard (PASS)
  const isValToOut = executedIds.has('validate') && executedIds.has('output_guard');
  svgParts.push(renderEdge('M 400 620 L 400 646', isValToOut, '#10B981'));

  // Output Guard -> END
  const isOutToEnd = executedIds.has('output_guard');
  svgParts.push(renderEdge('M 400 694 L 400 721', isOutToEnd, '#38BDF8'));

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
  svgParts.push(renderTerminal(400, 735, 150, 28, '🏁 FINAL OUTPUT', 'url(#eandRedGrad)', executedIds.has('validate') || executedIds.has('output_guard')));

  const svgGraph = `
    <div class="wf-svg-toolbar" style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
      <span style="font-size:11.5px; font-weight:700; color:#94A3B8;">${isAr ? 'مخطط سير العمل المباشر للطلب الحالي:' : 'Real-time Request Execution Pipeline:'}</span>
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
      return `<span class="wf-path-chip" style="border-color:${color}40; background:${color}15; color:${color};">
                <span class="wf-path-chip-num" style="background:${color}; color:#fff;">${i+1}</span>
                <span>${icon} ${label}</span>
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

      const details = step.details || {};
      let chipsHtml = '';
      const chipEntries = [];
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
            <span class="wf-step-badge ${badgeClass}">${badgeText}</span>
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
      <span style="font-size:11px;color:var(--slate);font-weight:600;">${workflow.length} ${isAr ? 'عقد منفذة' : 'executed nodes'}</span>
    </div>
    ${svgGraph}
    ${pathStrip}
    <div class="wf-section-title" style="margin-top:8px;">
      <span>${isAr ? 'تفاصيل خطوات التنفيذ' : 'Step-by-Step Execution Details'}</span>
    </div>
    ${stepsHtml}`;
}


/* ---------- Render Sources View ---------- */
function renderSourcesView(container, data) {
  const dict = currentDict();
  const isAr = getLang() === 'ar';
  const sources = data.sources || [];

  if (sources.length === 0) {
    container.innerHTML = `
      <div class="empty-state-card">
        <span class="empty-state-ic">📄</span>
        <p>${dict['chat.noSources'] || (isAr ? 'لم يتم استخدام وثائق خارجية (تمت معالجة الاستفسار مباشرة عبر قواعد التوجيه المباشر والأمان).' : 'No external document retrieval was required for this response.')}</p>
      </div>
    `;
    return;
  }

  let html = '<div class="sources-container">';
  sources.forEach((src) => {
    const filename = src.source || (isAr ? 'مستند غير معروف' : 'Knowledge Base Document');
    const page = src.page !== undefined && src.page !== '' ? `${dict['chat.page'] || (isAr ? 'صفحة' : 'Page')} ${src.page}` : '';
    const category = src.category || '';
    const product = src.product || '';
    const snippet = src.snippet || '';

    html += `
      <div class="source-card">
        <div class="source-head">
          <div class="source-title-wrap">
            <span class="source-ic">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                <polyline points="14 2 14 8 20 8"></polyline>
              </svg>
            </span>
            <span class="source-filename">${filename}</span>
          </div>
          ${page ? `<span class="source-page-badge">${page}</span>` : ''}
        </div>
        ${(category || product) ? `
          <div class="source-tags">
            ${category ? `<span class="source-tag">${category}</span>` : ''}
            ${product ? `<span class="source-tag">${product}</span>` : ''}
          </div>
        ` : ''}
        ${snippet ? `
          <div class="source-snippet-box">
            ${snippet}
          </div>
        ` : ''}
      </div>
    `;
  });
  html += '</div>';

  container.innerHTML = html;
}

/* ---------- Add Bot Message with Action Buttons ---------- */
function addBotResponse(data) {
  const dict = currentDict();
  const rawAnswer = data.answer || dict['chat.noAnswer'];
  const botAnswer = cleanBotText(rawAnswer);
  const isRTL = isArabicText(botAnswer);
  const isAr = getLang() === 'ar';

  const groupDiv = document.createElement('div');
  groupDiv.className = 'bot-msg-group';

  // 1. Bot message bubble
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
  textNode.className = 'msg-content-text';
  textNode.textContent = botAnswer;
  msgDiv.appendChild(textNode);

  groupDiv.appendChild(msgDiv);

  // 2. Action buttons toolbar
  const actionsDiv = document.createElement('div');
  actionsDiv.className = 'msg-actions';

  // Workflow button
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
  wfBtn.addEventListener('click', () => openInspector('workflow', data));
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
  body.scrollTop = body.scrollHeight;

  chatHistory.push({ role: 'assistant', content: botAnswer });
}


function showTyping() {
  const typing = document.createElement('div');
  typing.className = 'typing';
  typing.id = 'typing-indicator';

  for (let i = 0; i < 3; i += 1) {
    typing.appendChild(document.createElement('span'));
  }

  body.appendChild(typing);
  body.scrollTop = body.scrollHeight;
}

function hideTyping() {
  const typing = document.getElementById('typing-indicator');
  if (typing) typing.remove();
}

function openChat() {
  if (!panel) return;
  panel.classList.add('open');
  initModelSelector();
  if (input) input.focus();
}

function closeChat() {
  if (panel) {
    panel.classList.remove('open');
    closeInspector();
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

  if (
    target.classList.contains('open-chat')
    || href === '#chat'
    || i18n.includes('ctaSecondary')
    || text.includes('ask the chatbot')
    || text.includes('ask the e&')
    || text.includes('smart assistant')
  ) {
    event.preventDefault();
    openChat();
  }
});

if (form && input) {
  form.addEventListener('submit', async (event) => {
    event.preventDefault();

    const question = input.value.trim();
    if (!question) return;

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
      addBotResponse(data);
    } catch (_) {
      clearTimeout(timeoutId);
      hideTyping();
      addMsg(dict['chat.offline'], 'error');
    } finally {
      input.disabled = false;
      input.focus();
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
});

window.openHdGraphModal = function() {
  const isAr = getLang() === 'ar';
  let modal = document.getElementById('hd-graph-modal');
  if (modal) {
    modal.remove();
  }
  modal = document.createElement('div');
  modal.id = 'hd-graph-modal';
  modal.style.cssText = 'position:fixed; inset:0; z-index:99999; background:rgba(9, 13, 22, 0.96); display:flex; flex-direction:column; backdrop-filter:blur(10px);';
  modal.innerHTML = `
    <div style="display:flex; justify-content:space-between; align-items:center; padding:12px 20px; background:#0F172A; border-bottom:1px solid #1E293B;">
      <div style="display:flex; align-items:center; gap:10px;">
        <span style="font-size:20px;">🧭</span>
        <h3 style="margin:0; font-size:15px; font-weight:800; color:#F8FAFC; font-family:'Cairo',sans-serif;">
          ${isAr ? 'مخطط بنية النظام الكاملة (e& Egypt Production State Machine)' : 'e& Egypt Production State Machine HD Diagram'}
        </h3>
      </div>
      <button onclick="document.getElementById('hd-graph-modal').remove()" style="background:#EF4444; border:none; color:#FFFFFF; padding:6px 16px; border-radius:6px; font-weight:800; font-size:13px; cursor:pointer; box-shadow:0 2px 10px rgba(239,68,68,0.3);">
        ✕ ${isAr ? 'إغلاق' : 'Close'}
      </button>
    </div>
    <div style="flex:1; overflow:auto; padding:20px; display:flex; justify-content:center; align-items:center;">
      <img src="/assets/agentic_rag_graph.svg?v=${Date.now()}" alt="e& Egypt State Machine HD Architecture" style="max-width:98%; max-height:88vh; object-fit:contain; border-radius:12px; box-shadow:0 10px 40px rgba(0,0,0,0.8); border:1px solid #1E293B;">
    </div>
  `;
  document.body.appendChild(modal);
};


