import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";
import es from "~/locales/es-bundle";
import { i18n } from "~/shell/i18n";

// Vitest runs without globals, so Testing Library cannot register its own cleanup.
afterEach(cleanup);

// The app reads the Spanish resources from a chunk when the language is first switched to Spanish (shell/i18n.ts); the tests have them in
// place from the start, so a test that switches the language never waits for a chunk (and never times out under load).
for (const [namespace, resources] of Object.entries(es))
  i18n.addResourceBundle("es", namespace, resources, true, true);
