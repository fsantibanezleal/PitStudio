import "@fontsource-variable/inter";
import "@fontsource-variable/jetbrains-mono";
import "~/shell/tokens.css";
import "./console.css";
import { createRoot } from "react-dom/client";
import { I18nextProvider } from "react-i18next";
import { App } from "./App";
import { i18n } from "./i18n";

const root = document.getElementById("root");
if (!root) throw new Error("the console page has no #root element");
createRoot(root).render(
  <I18nextProvider i18n={i18n}>
    <App />
  </I18nextProvider>,
);
