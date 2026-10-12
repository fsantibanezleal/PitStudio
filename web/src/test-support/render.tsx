// Shared, locked render helper for the P6 web-structure unit tests. Not a test file.
// Renders a component inside the app's i18n instance (the shell's singleton, `~/shell/i18n`) and a MemoryRouter
// without a basename, so a link to `/cases/A1/` has the href "/cases/A1/". The language is set on every call
// (default "en"), so no state leaks between tests.
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { I18nextProvider } from "react-i18next";
import { MemoryRouter } from "react-router";
import { i18n } from "~/shell/i18n";

export async function renderApp(ui: ReactElement, opts: { lang?: "en" | "es"; route?: string } = {}) {
  await i18n.changeLanguage(opts.lang ?? "en");
  return render(
    <I18nextProvider i18n={i18n}>
      <MemoryRouter initialEntries={[opts.route ?? "/"]}>{ui}</MemoryRouter>
    </I18nextProvider>,
  );
}

/** Props the tests pass are plain JSON shaped by the data contracts; the component's own types may be stricter. */
export function props<T>(value: unknown): T {
  return value as T;
}
