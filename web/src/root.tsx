import "@fontsource-variable/inter";
import "@fontsource-variable/jetbrains-mono";
import "./shell/tokens.css";
import type { ReactNode } from "react";
import { I18nextProvider, useTranslation } from "react-i18next";
import { isRouteErrorResponse, Links, Meta, Outlet, Scripts, ScrollRestoration } from "react-router";
import type { Route } from "./+types/root";
import { shellConfig } from "./app/config";
import { AccessGate } from "./shell/AccessGate";
import { ShellConfigContext } from "./shell/config";
import { Footer } from "./shell/Footer";
import { Header } from "./shell/Header";
import { i18n } from "./shell/i18n";
import { useLanguageSync } from "./shell/LanguageSwitcher";
import { NotFound } from "./shell/NotFound";
import { THEME_BOOT_SCRIPT } from "./shell/prefs";
import styles from "./shell/shell.module.css";

export const meta: Route.MetaFunction = () => [
  { title: "PitStudio" },
  {
    name: "description",
    content:
      "Physical-AI simulation studio for open-pit mining: OpenUSD scenes, GPU physics, RTX sensors, synthetic data, trained models and an interactive web explorer.",
  },
];

export function Layout({ children }: { children: ReactNode }) {
  return (
    // The boot script sets data-theme before hydration, so <html> attributes legitimately differ.
    <html lang="en" suppressHydrationWarning>
      <head>
        <meta charSet="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <link rel="icon" type="image/svg+xml" href={`${import.meta.env.BASE_URL}favicon.svg`} />
        {/* biome-ignore lint/security/noDangerouslySetInnerHtml: static pre-paint theme script, no user input */}
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOT_SCRIPT }} />
        <Meta />
        <Links />
      </head>
      <body>
        <I18nextProvider i18n={i18n}>
          <ShellConfigContext.Provider value={shellConfig}>{children}</ShellConfigContext.Provider>
        </I18nextProvider>
        <ScrollRestoration />
        <Scripts />
      </body>
    </html>
  );
}

function Frame({ children }: { children: ReactNode }) {
  const { t } = useTranslation("shell");
  useLanguageSync();
  return (
    <>
      <a href="#main" className={styles.skip}>
        {t("skip")}
      </a>
      <Header />
      <main id="main" className={styles.main} tabIndex={-1}>
        {children}
      </main>
      <Footer />
    </>
  );
}

export default function App() {
  return (
    <Frame>
      <AccessGate>
        <Outlet />
      </AccessGate>
    </Frame>
  );
}

export function HydrateFallback() {
  return (
    <Frame>
      <AccessGate>{null}</AccessGate>
    </Frame>
  );
}

export function ErrorBoundary({ error }: Route.ErrorBoundaryProps) {
  if (isRouteErrorResponse(error) && error.status === 404) {
    return (
      <Frame>
        <NotFound />
      </Frame>
    );
  }
  return (
    <Frame>
      <ErrorView />
    </Frame>
  );
}

function ErrorView() {
  const { t } = useTranslation("shell");
  return (
    <article className={styles.page}>
      <h1>{t("error.title")}</h1>
      <p className={styles.lead}>{t("error.body")}</p>
    </article>
  );
}
