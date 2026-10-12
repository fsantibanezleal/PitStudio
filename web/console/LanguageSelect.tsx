import { Languages } from "lucide-react";
import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { isLanguage, LANG_KEY, LANGUAGES, type Language, resolveLanguage } from "~/shell/prefs";
import styles from "~/shell/shell.module.css";

function stored(): string | null {
  try {
    return localStorage.getItem(LANG_KEY);
  } catch {
    return null;
  }
}

/** `?lang=` wins over the stored choice, which wins over English; `<html lang>` follows the language. */
export function useLanguageSync(): void {
  const { i18n } = useTranslation();
  useEffect(() => {
    const lang = resolveLanguage(window.location.search, stored());
    if (i18n.language !== lang) void i18n.changeLanguage(lang);
    const apply = (lng: string) => {
      document.documentElement.lang = lng;
    };
    apply(lang);
    i18n.on("languageChanged", apply);
    return () => i18n.off("languageChanged", apply);
  }, [i18n]);
}

export function LanguageSelect() {
  const { t, i18n } = useTranslation("shell");
  const choose = (lang: Language) => {
    try {
      localStorage.setItem(LANG_KEY, lang);
    } catch {
      // storage blocked: the choice lasts for this page only
    }
    const url = new URL(window.location.href);
    if (url.searchParams.has("lang")) {
      url.searchParams.set("lang", lang);
      window.history.replaceState(null, "", url);
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
