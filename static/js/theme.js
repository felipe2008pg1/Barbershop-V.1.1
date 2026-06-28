/**
 * Light/dark mode control, shared across the 3 pages.
 * Saves the preference to localStorage to persist across visits.
 */

const THEME_STORAGE_KEY = "barbershop_theme";

function getCurrentTheme() {
  return localStorage.getItem(THEME_STORAGE_KEY) || "light";
}

function applyTheme(theme) {
  if (theme === "dark") {
    document.documentElement.setAttribute("data-theme", "dark");
  } else {
    document.documentElement.removeAttribute("data-theme");
  }
  updateThemeIcon(theme);
}

function setTheme(theme) {
  localStorage.setItem(THEME_STORAGE_KEY, theme);
  applyTheme(theme);
}

function toggleTheme() {
  setTheme(getCurrentTheme() === "dark" ? "light" : "dark");
}

function updateThemeIcon(theme) {
  document.querySelectorAll("[data-theme-icon]").forEach((el) => {
    el.innerHTML =
      theme === "dark"
        ? `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.2" y1="4.2" x2="5.6" y2="5.6"/><line x1="18.4" y1="18.4" x2="19.8" y2="19.8"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.2" y1="19.8" x2="5.6" y2="18.4"/><line x1="18.4" y1="5.6" x2="19.8" y2="4.2"/></svg>`
        : `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>`;
  });
}

document.addEventListener("DOMContentLoaded", () => {
  applyTheme(getCurrentTheme());
});
