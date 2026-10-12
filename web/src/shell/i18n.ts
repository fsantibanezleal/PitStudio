import i18next from "i18next";
import { initReactI18next } from "react-i18next";
import appEn from "~/locales/en/app.json";
import casesEn from "~/locales/en/cases.json";
import chartsEn from "~/locales/en/charts.json";
import resultsEn from "~/locales/en/results.json";
import shellEn from "~/locales/en/shell.json";
import studioEn from "~/locales/en/studio.json";
import appEs from "~/locales/es/app.json";
import casesEs from "~/locales/es/cases.json";
import chartsEs from "~/locales/es/charts.json";
import resultsEs from "~/locales/es/results.json";
import shellEs from "~/locales/es/shell.json";
import studioEs from "~/locales/es/studio.json";
import { DEFAULT_LANGUAGE, LANGUAGES } from "./prefs";

// Resources are bundled (both languages are small). Prerendered HTML is always English; the stored or ?lang=
// choice is applied after hydration (see useLanguageSync) so server and client markup match.
export const i18n = i18next.createInstance();

void i18n.use(initReactI18next).init({
  lng: DEFAULT_LANGUAGE,
  fallbackLng: DEFAULT_LANGUAGE,
  supportedLngs: [...LANGUAGES],
  ns: ["shell", "app", "cases", "results", "charts", "studio"],
  defaultNS: "app",
  resources: {
    en: { shell: shellEn, app: appEn, cases: casesEn, results: resultsEn, charts: chartsEn, studio: studioEn },
    es: { shell: shellEs, app: appEs, cases: casesEs, results: resultsEs, charts: chartsEs, studio: studioEs },
  },
  interpolation: { escapeValue: false },
  initAsync: false,
});
