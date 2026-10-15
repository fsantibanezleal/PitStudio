// Sets data-theme before first paint (same logic as THEME_BOOT_SCRIPT in src/shell/prefs.ts; keep them in sync).
(() => {
  try {
    const p = localStorage.getItem("fsl:theme");
    const dark = p === "dark" || (p !== "light" && matchMedia("(prefers-color-scheme: dark)").matches);
    const root = document.documentElement;
    root.dataset.theme = dark ? "dark" : "light";
    root.style.colorScheme = dark ? "dark" : "light";
  } catch {
    // storage blocked: the stylesheet default applies
  }
})();
