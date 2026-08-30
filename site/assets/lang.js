// e& Egypt — language toggle (English / Arabic). Persists choice + sets dir.
(function(){
  const root = document.documentElement;
  const stored = localStorage.getItem('e-and-lang');
  const initial = stored || 'en';

  function applyLang(lang){
    const dict = translations[lang] || translations.en;
    root.setAttribute('lang', lang);
    root.setAttribute('dir', lang === 'ar' ? 'rtl' : 'ltr');

    document.querySelectorAll('[data-i18n]').forEach(el => {
      const key = el.getAttribute('data-i18n');
      if(dict[key] !== undefined) el.textContent = dict[key];
    });
    document.querySelectorAll('[data-i18n-html]').forEach(el => {
      const key = el.getAttribute('data-i18n-html');
      if(dict[key] !== undefined) el.innerHTML = dict[key];
    });
    document.querySelectorAll('[data-i18n-ph]').forEach(el => {
      const key = el.getAttribute('data-i18n-ph');
      if(dict[key] !== undefined) el.setAttribute('placeholder', dict[key]);
    });

    const label = document.getElementById('lang-toggle-label');
    if(label) label.textContent = lang === 'ar' ? 'EN' : 'AR';

    window.dispatchEvent(new CustomEvent('languagechange', { detail: { lang } }));
  }

  // Apply immediately (before paint) using cached preference to avoid flash.
  root.setAttribute('lang', initial);
  root.setAttribute('dir', initial === 'ar' ? 'rtl' : 'ltr');

  window.addEventListener('DOMContentLoaded', () => {
    applyLang(initial);
    const btn = document.getElementById('lang-toggle');
    if(!btn) return;
    btn.addEventListener('click', () => {
      const current = root.getAttribute('lang') === 'ar' ? 'en' : 'ar';
      localStorage.setItem('e-and-lang', current);
      applyLang(current);
    });
  });
})();

