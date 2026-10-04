import i18next from "i18next";
import { initReactI18next } from "react-i18next";
import appEn from "~/locales/en/app.json";
import shellEn from "~/locales/en/shell.json";
import appEs from "~/locales/es/app.json";
import shellEs from "~/locales/es/shell.json";
import { DEFAULT_LANGUAGE, LANGUAGES } from "./prefs";

// Resources are bundled (both languages are small). Prerendered HTML is always English; the stored or ?lang=
// choice is applied after hydration (see useLanguageSync) so server and client markup match.
export const i18n = i18next.createInstance();

void i18n.use(initReactI18next).init({
  lng: DEFAULT_LANGUAGE,
  fallbackLng: DEFAULT_LANGUAGE,
  supportedLngs: [...LANGUAGES],
  ns: ["shell", "app"],
  defaultNS: "app",
  resources: {
    en: { shell: shellEn, app: appEn },
    es: { shell: shellEs, app: appEs },
  },
  interpolation: { escapeValue: false },
  initAsync: false,
});
