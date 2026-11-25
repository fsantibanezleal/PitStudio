import i18next from "i18next";
import { initReactI18next } from "react-i18next";
import appEn from "~/locales/en/app.json";
import casesEn from "~/locales/en/cases.json";
import chartsEn from "~/locales/en/charts.json";
import resultsEn from "~/locales/en/results.json";
import shellEn from "~/locales/en/shell.json";
import studioEn from "~/locales/en/studio.json";
import surrogatesEn from "~/locales/en/surrogates.json";
import terrain3dEn from "~/locales/en/terrain3d.json";
import { DEFAULT_LANGUAGE, LANGUAGES } from "./prefs";

// English is bundled (the prerendered HTML is always English); Spanish is one chunk read when the language is first switched to it
// (NFR-018-02: it is about 13 KB gzip that no English visit needs). The stored or ?lang= choice is applied after hydration (see
// useLanguageSync) so server and client markup match; `changeLanguage` settles once the Spanish resources are in.
export const i18n = i18next.createInstance();

type Bundle = Record<string, Record<string, unknown>>;
const spanish = () => import("~/locales/es-bundle").then((m) => m.default as Bundle);
let spanishLoad: Promise<Bundle> | null = null;
const lazyLocales = {
  type: "backend" as const,
  init() {},
  read(language: string, namespace: string, callback: (error: Error | null, data: unknown) => void) {
    if (language !== "es") return callback(null, {});
    spanishLoad ??= spanish();
    spanishLoad.then(
      (bundle) => callback(null, bundle[namespace] ?? {}),
      (error: Error) => {
        spanishLoad = null;
        callback(error, null);
      },
    );
  },
};

void i18n
  .use(lazyLocales)
  .use(initReactI18next)
  .init({
    partialBundledLanguages: true,
    lng: DEFAULT_LANGUAGE,
    fallbackLng: DEFAULT_LANGUAGE,
    supportedLngs: [...LANGUAGES],
    ns: ["shell", "app", "cases", "results", "charts", "studio", "surrogates", "terrain3d"],
    defaultNS: "app",
    resources: {
      en: {
        shell: shellEn,
        app: appEn,
        cases: casesEn,
        results: resultsEn,
        charts: chartsEn,
        surrogates: surrogatesEn,
        studio: studioEn,
        terrain3d: terrain3dEn,
      },
    },
    interpolation: { escapeValue: false },
    initAsync: false,
  });
