import { Monitor, Moon, Sun } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { isThemePref, nextThemePref, resolveTheme, THEME_KEY, type ThemePref } from "./prefs";
import styles from "./shell.module.css";

const ICONS = { system: Monitor, light: Sun, dark: Moon } as const;

function readPref(): ThemePref {
  try {
    const stored = localStorage.getItem(THEME_KEY);
    return isThemePref(stored) ? stored : "system";
  } catch {
    return "system";
  }
}

function apply(pref: ThemePref): void {
  const theme = resolveTheme(pref, matchMedia("(prefers-color-scheme: dark)").matches);
  const root = document.documentElement;
  root.dataset.theme = theme;
  root.style.colorScheme = theme;
}

export function ThemeToggle() {
  const { t } = useTranslation("shell");
  // Unknown during prerender and the first client render (the boot script already set the theme); the stored
  // choice is read after hydration.
  const [stored, setStored] = useState<ThemePref | null>(null);

  useEffect(() => setStored(readPref()), []);

  useEffect(() => {
    if (stored === null) return;
    apply(stored);
    if (stored !== "system") return;
    const media = matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => apply("system");
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, [stored]);

  const pref = stored ?? "system";
  const next = nextThemePref(pref);
  const Icon = ICONS[pref];
  const onClick = () => {
    try {
      localStorage.setItem(THEME_KEY, next);
    } catch {
      // storage blocked: the choice lasts for this page only
    }
    setStored(next);
  };

  return (
    <button
      type="button"
      className={styles.iconButton}
      onClick={onClick}
      aria-label={t("theme.label", { current: t(`theme.${pref}`), next: t(`theme.${next}`) })}
      data-theme-pref={pref}
    >
      <Icon aria-hidden="true" size={18} />
    </button>
  );
}
