// Language and theme preferences. Keys are shared by every app on the fsantibanezleal.github.io origin.

export const LANGUAGES = ["en", "es"] as const;
export type Language = (typeof LANGUAGES)[number];
export const DEFAULT_LANGUAGE: Language = "en";
export const LANG_KEY = "fsl:lang";

export const THEME_PREFS = ["system", "light", "dark"] as const;
export type ThemePref = (typeof THEME_PREFS)[number];
export type Theme = "light" | "dark";
export const THEME_KEY = "fsl:theme";

export function isLanguage(value: unknown): value is Language {
  return typeof value === "string" && (LANGUAGES as readonly string[]).includes(value);
}

/** Priority: `?lang=` > stored choice > English. Invalid values are ignored; the browser language is never used. */
export function resolveLanguage(search: string, stored: string | null): Language {
  const fromQuery = new URLSearchParams(search).get("lang");
  if (isLanguage(fromQuery)) return fromQuery;
  if (isLanguage(stored)) return stored;
  return DEFAULT_LANGUAGE;
}

export function isThemePref(value: unknown): value is ThemePref {
  return typeof value === "string" && (THEME_PREFS as readonly string[]).includes(value);
}

export function resolveTheme(pref: ThemePref, systemDark: boolean): Theme {
  if (pref === "system") return systemDark ? "dark" : "light";
  return pref;
}

/** The toggle cycles system → light → dark → system. */
export function nextThemePref(pref: ThemePref): ThemePref {
  const i = THEME_PREFS.indexOf(pref);
  return THEME_PREFS[(i + 1) % THEME_PREFS.length] ?? "system";
}

/**
 * Runs before first paint (inlined in <head>) so the page never flashes the wrong theme.
 * Keep it in sync with resolveTheme; it must not throw (storage can be blocked).
 */
export const THEME_BOOT_SCRIPT = `(function(){try{var p=localStorage.getItem("${THEME_KEY}");var d=p==="dark"||(p!=="light"&&matchMedia("(prefers-color-scheme: dark)").matches);var r=document.documentElement;r.dataset.theme=d?"dark":"light";r.style.colorScheme=d?"dark":"light";}catch(e){}})();`;
