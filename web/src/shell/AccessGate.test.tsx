import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { I18nextProvider } from "react-i18next";
import { beforeEach, describe, expect, it } from "vitest";
import { AccessGate } from "./AccessGate";
import { type ShellConfig, ShellConfigContext } from "./config";
import { i18n } from "./i18n";

const ABC = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"; // sha256("abc")

function config(digest: string): ShellConfig {
  return {
    product: "PitStudio",
    repo: "TestRepo",
    author: "a",
    version: "0",
    gitSha: "0",
    buildDate: "2026-01-01",
    repoUrl: "https://example.org",
    routes: [],
    links: [],
    footer: { licenceKey: "footer.licence", provenance: [] },
    architectureTabs: [],
    access: { digest },
  };
}

function renderGate(digest: string) {
  return render(
    <I18nextProvider i18n={i18n}>
      <ShellConfigContext.Provider value={config(digest)}>
        <AccessGate>
          <p>workbench</p>
        </AccessGate>
      </ShellConfigContext.Provider>
    </I18nextProvider>,
  );
}

describe("AccessGate", () => {
  beforeEach(() => sessionStorage.clear());

  it("FR-000-04 · shows the content directly when no digest is configured", () => {
    renderGate("");
    expect(screen.getByText("workbench")).toBeTruthy();
  });

  it("FR-000-04 · locks, states it is not a security boundary, rejects a wrong phrase and opens on the right one", async () => {
    const user = userEvent.setup();
    renderGate(ABC);
    const input = await screen.findByLabelText("Passphrase");
    expect(screen.getByText(/not a security boundary/)).toBeTruthy();
    expect(screen.queryByText("workbench")).toBeNull();

    await user.type(input, "wrong");
    await user.click(screen.getByRole("button", { name: "Enter" }));
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.queryByText("workbench")).toBeNull();

    await user.clear(input);
    await user.type(input, "abc");
    await user.click(screen.getByRole("button", { name: "Enter" }));
    expect(await screen.findByText("workbench")).toBeTruthy();
    expect(sessionStorage.getItem("TestRepo:access")).toBe(ABC);
  });

  it("FR-000-04 · stays open for the session once unlocked", async () => {
    sessionStorage.setItem("TestRepo:access", ABC);
    renderGate(ABC);
    expect(await screen.findByText("workbench")).toBeTruthy();
  });

  it("FR-000-04 · does not accept a stored value that is not the digest", async () => {
    sessionStorage.setItem("TestRepo:access", "open");
    renderGate(ABC);
    expect(await screen.findByLabelText("Passphrase")).toBeTruthy();
    expect(screen.queryByText("workbench")).toBeNull();
  });
});
