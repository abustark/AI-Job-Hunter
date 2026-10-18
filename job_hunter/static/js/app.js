(() => {
  const storageKey = "job-hunter-theme";
  const root = document.documentElement;
  let stored = null;
  try { stored = window.localStorage.getItem(storageKey); } catch (_) { /* Use the system preference when storage is unavailable. */ }
  const systemTheme = window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";

  function applyTheme(theme) {
    root.dataset.theme = theme;
    const button = document.querySelector(".theme-toggle");
    if (button) {
      const nextTheme = theme === "dark" ? "light" : "dark";
      button.textContent = `Use ${nextTheme} theme`;
      button.setAttribute("aria-label", `Use ${nextTheme} theme`);
      button.setAttribute("aria-pressed", String(theme === "light"));
    }
  }

  applyTheme(stored === "light" || stored === "dark" ? stored : systemTheme);
  document.querySelector(".theme-toggle")?.addEventListener("click", () => {
    const theme = root.dataset.theme === "dark" ? "light" : "dark";
    try { window.localStorage.setItem(storageKey, theme); } catch (_) { /* The selected theme still applies for this page. */ }
    applyTheme(theme);
  });
})();
