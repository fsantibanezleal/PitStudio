import i18next from "i18next";
import { initReactI18next } from "react-i18next";
import shellEn from "~/locales/en/shell.json";
import shellEs from "~/locales/es/shell.json";
import { DEFAULT_LANGUAGE, LANGUAGES } from "~/shell/prefs";
import consoleEn from "./locales/en/console.json";
import consoleEs from "./locales/es/console.json";

// The console reuses the shell's namespace (theme and language labels) and adds its own; both languages are bundled.
export const i18n = i18next.createInstance();

void i18n.use(initReactI18next).init({
  lng: DEFAULT_LANGUAGE,
  fallbackLng: DEFAULT_LANGUAGE,
  supportedLngs: [...LANGUAGES],
  ns: ["shell", "console"],
  defaultNS: "console",
  resources: {
    en: { shell: shellEn, console: consoleEn },
    es: { shell: shellEs, console: consoleEs },
  },
  interpolation: { escapeValue: false },
  initAsync: false,
});
