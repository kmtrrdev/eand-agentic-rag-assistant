// e& Egypt — Packages page: renders the live catalog from GET /api/packages.
// Same data source the chatbot's deterministic tools use, so this page and
// the assistant's answers can never disagree.
(function () {
  const API_BASE = (typeof window !== 'undefined' && window.location && window.location.protocol.startsWith('http'))
    ? ''
    : 'http://127.0.0.1:8000';

  const grid = document.getElementById('pkg-grid');
  const tabsWrap = document.getElementById('pkg-family-tabs');
  const searchInput = document.getElementById('pkg-search');
  const countEl = document.getElementById('pkg-count');
  const emptyEl = document.getElementById('pkg-empty');

  if (!grid || !tabsWrap) return;

  let families = [];
  let activeFamily = 'all';
  let searchTerm = '';

  function getLang() {
    return document.documentElement.getAttribute('lang') || 'en';
  }

  function t(key, fallback) {
    const lang = getLang();
    if (typeof translations !== 'undefined' && translations[lang] && translations[lang][key] !== undefined) {
      return translations[lang][key];
    }
    return fallback;
  }

  function formatMoney(n) {
    if (n === null || n === undefined) return '';
    return Number(n).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 2 });
  }

  function renderTabs() {
    const isAr = getLang() === 'ar';
    const allLabel = t('packages.allFamilies', 'All Packages');
    let html = `<button type="button" class="pkg-tab ${activeFamily === 'all' ? 'active' : ''}" data-family="all">
      ${allLabel} <span class="pkg-tab-count">${families.reduce((s, f) => s + f.tier_count, 0)}</span>
    </button>`;
    families.forEach((f) => {
      const name = isAr ? (f.name_ar || f.name_en) : f.name_en;
      html += `<button type="button" class="pkg-tab ${activeFamily === f.id ? 'active' : ''}" data-family="${f.id}">
        ${name} <span class="pkg-tab-count">${f.tier_count}</span>
      </button>`;
    });
    tabsWrap.innerHTML = html;
    tabsWrap.querySelectorAll('.pkg-tab').forEach((btn) => {
      btn.addEventListener('click', () => {
        activeFamily = btn.getAttribute('data-family');
        renderTabs();
        renderGrid();
      });
    });
  }

  function matchesSearch(tier, family) {
    if (!searchTerm) return true;
    const haystack = [
      tier.name_en, tier.name_ar, tier.ussd_code, tier.quota_label_en, tier.quota_label_ar,
      family.name_en, family.name_ar, String(tier.price_egp),
    ].filter(Boolean).join(' ').toLowerCase();
    return haystack.includes(searchTerm.toLowerCase());
  }

  function renderCard(tier, family) {
    const isAr = getLang() === 'ar';
    const name = isAr ? (tier.name_ar || tier.name_en) : tier.name_en;
    const familyName = isAr ? (family.name_ar || family.name_en) : family.name_en;
    const desc = isAr ? (tier.description_ar || tier.description_en) : (tier.description_en || tier.description_ar);
    const perks = isAr ? (tier.perks_ar || tier.perks_en) : (tier.perks_en || tier.perks_ar);
    const quota = isAr ? (tier.quota_label_ar || tier.quota_label_en) : (tier.quota_label_en || tier.quota_label_ar);
    const currency = isAr ? 'جنيه' : 'EGP';
    const preTaxLabel = t('packages.preTax', 'pre-tax');
    const totalLabel = t('packages.total', 'total w/ tax');
    const validityLabel = t('packages.validity', 'Validity');
    const daysLabel = isAr ? 'يوم' : 'days';
    const ussdLabel = t('packages.ussd', 'Activation');

    const showTotal = tier.total_egp !== null && tier.total_egp !== undefined && Math.abs(tier.total_egp - tier.price_egp) > 0.01;

    return `
      <div class="pkg-card" data-family="${family.id}">
        <div class="pkg-card-top">
          <span class="pkg-family-badge">${familyName}</span>
        </div>
        <h3 class="pkg-name" dir="${isAr ? 'rtl' : 'ltr'}">${name || ''}</h3>
        <div class="pkg-price-row">
          <span class="pkg-price">${formatMoney(tier.price_egp)} <small>${currency}</small></span>
          <span class="pkg-price-note">${preTaxLabel}</span>
        </div>
        ${showTotal ? `<div class="pkg-total-note">≈ ${formatMoney(tier.total_egp)} ${currency} ${totalLabel}</div>` : ''}
        ${quota ? `<div class="pkg-fact"><b>${quota}</b></div>` : ''}
        <div class="pkg-meta-row">
          ${tier.validity_days ? `<span class="pkg-meta-chip">📅 ${validityLabel}: ${tier.validity_days} ${daysLabel}</span>` : ''}
          ${tier.ussd_code ? `<span class="pkg-meta-chip">📟 ${ussdLabel}: ${tier.ussd_code}</span>` : ''}
        </div>
        ${desc ? `<p class="pkg-desc" dir="${isAr ? 'rtl' : 'ltr'}">${desc}</p>` : ''}
        ${perks ? `<div class="pkg-perks" dir="${isAr ? 'rtl' : 'ltr'}">✓ ${perks}</div>` : ''}
      </div>
    `;
  }

  function renderGrid() {
    const isAr = getLang() === 'ar';
    let cards = [];
    let visibleCount = 0;

    families.forEach((family) => {
      if (activeFamily !== 'all' && activeFamily !== family.id) return;
      const sortedTiers = [...family.tiers].sort((a, b) => (a.price_egp || 0) - (b.price_egp || 0));
      sortedTiers.forEach((tier) => {
        if (!matchesSearch(tier, family)) return;
        visibleCount += 1;
        cards.push(renderCard(tier, family));
      });
    });

    grid.innerHTML = cards.join('');
    if (countEl) {
      const template = t('packages.countLabel', '{n} packages shown');
      countEl.textContent = template.replace('{n}', visibleCount);
    }
    if (emptyEl) emptyEl.style.display = visibleCount === 0 ? 'block' : 'none';
    grid.style.display = visibleCount === 0 ? 'none' : 'grid';
  }

  function loadCatalog() {
    fetch(`${API_BASE}/api/packages`)
      .then((res) => {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
      })
      .then((data) => {
        families = data.families || [];
        renderTabs();
        renderGrid();
      })
      .catch(() => {
        grid.innerHTML = `<div class="pkg-loading pkg-error">${t('packages.error', "Couldn't load the catalog. Make sure the server is running, then reload this page.")}</div>`;
      });
  }

  if (searchInput) {
    searchInput.addEventListener('input', () => {
      searchTerm = searchInput.value.trim();
      renderGrid();
    });
  }

  window.addEventListener('languagechange', () => {
    renderTabs();
    renderGrid();
  });

  loadCatalog();
})();
