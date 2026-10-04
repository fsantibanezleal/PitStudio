import { Languages } from "lucide-react";
import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router";
import { isLanguage, LANG_KEY, LANGUAGES, type Language, resolveLanguage } from "./prefs";
import styles from "./shell.module.css";

function readStored(): string | null {
  try {
    return localStorage.getItem(LANG_KEY);
  } catch {
    return null;
  }
}

/** Applies `?lang=` or the stored language after hydration and keeps `<html lang>` in sync. */
export function useLanguageSync(): void {
  const { i18n } = useTranslation();
  const [params] = useSearchParams();
  const query = params.get("lang");

  useEffect(() => {
    const lang = resolveLanguage(query ? `?lang=${query}` : "", readStored());
    if (i18n.language !== lang) void i18n.changeLanguage(lang);
  }, [i18n, query]);

  useEffect(() => {
    const apply = (lng: string) => {
      document.documentElement.lang = lng;
    };
    apply(i18n.language);
    i18n.on("languageChanged", apply);
    return () => i18n.off("languageChanged", apply);
  }, [i18n]);
}

export function LanguageSwitcher() {
  const { t, i18n } = useTranslation("shell");
  const [params, setParams] = useSearchParams();

  const choose = (lang: Language) => {
    try {
      localStorage.setItem(LANG_KEY, lang);
    } catch {
      // storage blocked: the choice lasts for this page only
    }
    if (params.has("lang")) {
      const next = new URLSearchParams(params);
      next.set("lang", lang);
      setParams(next, { replace: true, preventScrollReset: true });
    }
    void i18n.changeLanguage(lang);
  };

  const current = isLanguage(i18n.language) ? i18n.language : "en";
  return (
    <label className={styles.lang}>
      <Languages aria-hidden="true" size={18} />
      <span className={styles.srOnly}>{t("lang.label")}</span>
      <select value={current} onChange={(e) => isLanguage(e.target.value) && choose(e.target.value)}>
        {LANGUAGES.map((lng) => (
          <option key={lng} value={lng} lang={lng}>
            {t(`lang.${lng}`)}
          </option>
        ))}
      </select>
    </label>
  );
}
