import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderApp } from "~/test-support/render";
import { executive } from "./content";
import { IntroductionView } from "./IntroductionView";

const PUBLIC = resolve(__dirname, "../../public");

class QuietObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

beforeEach(() => {
  vi.stubGlobal("ResizeObserver", QuietObserver);
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const file = String(url).replace(/^.*\/(executive\/[a-z]+\.svg)$/, "$1");
      return new Response(readFileSync(resolve(PUBLIC, file), "utf8"), { status: 200 });
    }),
  );
});

const SECTIONS = {
  en: ["The pain", "The context", "The current situation", "The trends", "The proposal"],
  es: ["El problema", "El contexto", "La situación actual", "Las tendencias", "La propuesta"],
} as const;

describe("the Introduction opens on the executive view, ahead of the technical view", () => {
  for (const lang of ["en", "es"] as const) {
    it(`${lang}: shows the page title, the problem title from the content file and the five sub-tabs`, async () => {
      await renderApp(<IntroductionView data={executive} />, { lang });
      expect(screen.getByRole("heading", { level: 1 })).toBeTruthy(); // in the first scripts, before the view chunk
      await screen.findByRole("tab", { name: /Executive view|Vista ejecutiva/ });
      expect(screen.getByRole("heading", { level: 1 })).toBeTruthy();
      expect(screen.getByRole("heading", { level: 2, name: executive.title[lang] })).toBeTruthy();
      for (const name of SECTIONS[lang]) expect(screen.getByRole("tab", { name })).toBeTruthy();
      const executiveTab = screen.getByRole("tab", {
        name: lang === "en" ? "Executive view" : "Vista ejecutiva",
      });
      expect(executiveTab.getAttribute("aria-selected")).toBe("true");
    });
  }

  it("renders its text from the content file (the key statement and a source link come from the data)", async () => {
    await renderApp(<IntroductionView data={executive} />);
    await screen.findByRole("tab", { name: /Executive view|Vista ejecutiva/ });
    expect(screen.getByText(executive.key_statement.en)).toBeTruthy();
    const first = executive.sources[0];
    const link = await screen.findByRole("link", { name: first?.title.en ?? "" });
    expect(link.getAttribute("href")).toBe(first?.url);
  });

  it("loads the pain illustration inline (an svg in the page, not an img)", async () => {
    const { container } = await renderApp(<IntroductionView data={executive} />);
    await screen.findByRole("tab", { name: /Executive view|Vista ejecutiva/ });
    await waitFor(() =>
      expect(container.querySelector('[data-exec-illustration="pain"] svg')).not.toBeNull(),
    );
    expect(container.querySelector("img")).toBeNull();
  });

  it("opens the sub-tab named by ?section= when entered by link", async () => {
    await renderApp(<IntroductionView data={executive} />, { route: "/?section=trends" });
    await screen.findByRole("tab", { name: /Executive view|Vista ejecutiva/ });
    await waitFor(() =>
      expect(screen.getByRole("tab", { name: "The trends" }).getAttribute("aria-selected")).toBe("true"),
    );
  });

  it("offers the technical view as a second tab, and the onward link opens it", async () => {
    await renderApp(<IntroductionView data={executive} />);
    await screen.findByRole("tab", { name: /Executive view|Vista ejecutiva/ });
    fireEvent.click(screen.getByRole("link", { name: "How the work explores this problem" }));
    await waitFor(() =>
      expect(screen.getByRole("tab", { name: "Technical view" }).getAttribute("aria-selected")).toBe("true"),
    );
    expect(screen.getByRole("link", { name: "Open the App" }).getAttribute("href")).toBe("/app");
  });

  it("links the executive view own 'Open the App' to /app", async () => {
    await renderApp(<IntroductionView data={executive} />);
    await screen.findByRole("tab", { name: /Executive view|Vista ejecutiva/ });
    const links = screen.getAllByRole("link", { name: "Open the App" });
    for (const a of links) expect(a.getAttribute("href")).toBe("/app");
  });
});
