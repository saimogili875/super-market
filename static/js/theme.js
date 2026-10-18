/**
 * Universal FreshMart Theme Engine
 * Automatically aligns with OS prefers-color-scheme, persists preference in localStorage,
 * and eliminates theme flicker before paint.
 */
function getFreshMartTheme() {
  try {
    var stored = localStorage.getItem('freshmart_theme');
    if (stored === 'dark' || stored === 'light') return stored;
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  } catch (e) {
    return 'light';
  }
}

function updateThemeToggleButtons(theme) {
  var btns = document.querySelectorAll('.freshmart-theme-toggle, #themeToggleBtn, .theme-toggle-btn');
  btns.forEach(function(btn) {
    var icon = btn.querySelector('.theme-icon, #themeToggleIcon');
    var label = btn.querySelector('.theme-label, #themeToggleLabel');
    if (theme === 'dark') {
      if (icon) icon.innerHTML = '&#9728;';
      if (label) label.textContent = 'Light';
      btn.setAttribute('title', 'Switch to Light Mode');
    } else {
      if (icon) icon.innerHTML = '&#127769;';
      if (label) label.textContent = 'Dark';
      btn.setAttribute('title', 'Switch to Dark Mode');
    }
  });
}

function toggleFreshMartTheme() {
  var current = document.documentElement.getAttribute('data-theme') || 'light';
  var next = current === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  try {
    localStorage.setItem('freshmart_theme', next);
  } catch (e) {}
  updateThemeToggleButtons(next);
}

// Immediate execution & DOM listener
(function() {
  try {
    var theme = getFreshMartTheme();
    document.documentElement.setAttribute('data-theme', theme);
  } catch (e) {}
})();

document.addEventListener('DOMContentLoaded', function() {
  var theme = document.documentElement.getAttribute('data-theme') || getFreshMartTheme();
  updateThemeToggleButtons(theme);
});
