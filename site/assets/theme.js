// Dark / light mode toggle — remembers the user's choice across pages.
(function(){
  const root = document.documentElement;
  const stored = localStorage.getItem('e-and-theme');
  const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
  const initial = stored || (prefersDark ? 'dark' : 'light');
  root.setAttribute('data-theme', initial);

  window.addEventListener('DOMContentLoaded', () => {
    const btn = document.getElementById('theme-toggle');
    if(!btn) return;
    btn.addEventListener('click', () => {
      const current = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
      root.setAttribute('data-theme', current);
      localStorage.setItem('e-and-theme', current);
    });
  });
})();
