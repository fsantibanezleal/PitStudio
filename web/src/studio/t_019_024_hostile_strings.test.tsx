// T-019-024 [red] · FR-019-40: a string of a manifest, run card or registry with markup, script, control characters or more than 200 characters is rendered by the studio pages as escaped text,
// truncated after 200 characters with an expander, and executes nothing. E2E half: web/e2e/t_019_024_hostile_strings.spec.ts.
//
// Expected API: `~/studio/SafeText` (web/src/studio/SafeText.tsx): named export SafeText({ value: string }) rendering `<span data-testid="safe-text" data-truncated="true|false">` that holds
//   `[data-testid="safe-text-value"]`: the string as TEXT (never parsed as HTML), with every control character replaced (C0 and C1 controls, DEL, bidirectional override and isolate characters
//     U+202A..U+202E and U+2066..U+2069; a line feed and a tab are kept) by U+FFFD, and, when the string has more than 200 characters (code points), its first 200 code points followed by "…";
//   and, only when truncated, `button[data-testid="expand"][aria-expanded]` (accessible name "Show full text" while collapsed, "Show less" while expanded) that toggles the full (still escaped) string.
// Every studio block that prints a manifest, run card or registry string uses it (checked here on the blocks of T-019-021: Role, Alternatives, Identity probe error).
// Oracles: hand-built strings (markup, script, control characters, 200 / 201 / 20,000 characters, an emoji crossing the 200th character); the contract is the EARS text.
import { fireEvent, screen, within } from "@testing-library/react";
import { createElement } from "react";
import { describe, expect, it } from "vitest";
import { AlternativesBlock } from "~/studio/blocks/Alternatives";
import { IdentityBlock } from "~/studio/blocks/Identity";
import { RoleBlock } from "~/studio/blocks/Role";
import { SafeText } from "~/studio/SafeText";
import { loadCaseRegistry } from "~/test-support/fixtures";
import { renderApp } from "~/test-support/render";
import { indexTool, makeTool } from "~/test-support/studio-fixtures";

const render = (value: string) => renderApp(createElement(SafeText, { value }));
const root = () => screen.getByTestId("safe-text");
const shown = () => within(root()).getByTestId("safe-text-value").textContent ?? "";
const hasControl = (s: string): boolean =>
  [...s].some((ch) => {
    const c = ch.codePointAt(0) ?? 0;
    const control = (c < 0x20 && c !== 0x09 && c !== 0x0a) || (c >= 0x7f && c <= 0x9f);
    return control || (c >= 0x202a && c <= 0x202e) || (c >= 0x2066 && c <= 0x2069);
  });

describe("escaped text (FR-019-40)", () => {
  for (const [what, value] of [
    ["an image with an event handler", `<img src=x onerror="window.__pwned=1">`],
    ["a script element", "<script>window.__pwned=1</script>"],
    ["an svg onload", `"><svg onload=window.__pwned=1>`],
    ["an anchor with a javascript address", `<a href="javascript:window.__pwned=1">x</a>`],
    ["an HTML entity", "&lt;b&gt; &amp; &#60;i&#62;"],
    ["a template literal", ["$", "{window.__pwned=1} {{constructor.constructor('1')()}}"].join("")],
  ] as const) {
    it(`FR-019-40 · ${what} is shown as the literal text and creates no element`, async () => {
      const { container } = await render(value);
      expect(shown()).toBe(value);
      expect(container.querySelector("img, script, svg, a, b, i")).toBeNull();
      expect((window as unknown as { __pwned?: number }).__pwned).toBeUndefined();
    });
  }

  it("FR-019-40 · control characters are replaced and none survives, the text around them is intact", async () => {
    const ch = (code: number) => String.fromCharCode(code);
    const value = `a${ch(0)}b${ch(7)}c${ch(0x1b)}d${ch(0x7f)}e${ch(0x85)}f${ch(0x202e)}g${ch(0x2066)}h${ch(0x200b)}i`;
    await render(value);
    expect(hasControl(shown())).toBe(false);
    expect(shown()).toContain("�");
    for (const kept of ["a", "b", "c", "d", "e", "f", "g", "h"]) expect(shown()).toContain(kept);
  });

  it("FR-019-40 · a line feed and a tab are kept", async () => {
    await render("one\ntwo\tthree");
    expect(shown()).toBe("one\ntwo\tthree");
  });

  it("FR-019-40 · the empty string renders nothing harmful and no expander", async () => {
    await render("");
    expect(shown()).toBe("");
    expect(screen.queryByTestId("expand")).toBeNull();
  });
});

describe("truncation after 200 characters with an expander (FR-019-40)", () => {
  it("FR-019-40 · a string of exactly 200 characters is shown whole and has no expander", async () => {
    await render("x".repeat(200));
    expect(shown()).toBe("x".repeat(200));
    expect(root().getAttribute("data-truncated")).toBe("false");
    expect(screen.queryByTestId("expand")).toBeNull();
  });

  it("FR-019-40 · a string of 201 characters is cut to its first 200 followed by an ellipsis, and an expander appears", async () => {
    const value = `${"a".repeat(100)}${"b".repeat(100)}c`;
    await render(value);
    expect(shown()).toBe(`${"a".repeat(100)}${"b".repeat(100)}…`);
    expect(root().getAttribute("data-truncated")).toBe("true");
    const button = screen.getByTestId("expand");
    expect(button.getAttribute("aria-expanded")).toBe("false");
    expect(button.textContent).toContain("Show full text");
  });

  it("FR-019-40 · the expander shows the full string (still as text) and collapses again", async () => {
    const value = `<b>${"z".repeat(20_000)}</b>`;
    const { container } = await render(value);
    expect(shown().length).toBe(201);
    fireEvent.click(screen.getByTestId("expand"));
    expect(shown()).toBe(value);
    expect(screen.getByTestId("expand").getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByTestId("expand").textContent).toContain("Show less");
    expect(container.querySelector("b")).toBeNull();
    fireEvent.click(screen.getByTestId("expand"));
    expect(shown().length).toBe(201);
    expect(screen.getByTestId("expand").getAttribute("aria-expanded")).toBe("false");
  });

  it("FR-019-40 · the expander is a real button reachable by keyboard", async () => {
    await render("k".repeat(500));
    const button = screen.getByTestId("expand");
    expect(button.tagName).toBe("BUTTON");
    expect(button.getAttribute("type")).toBe("button");
    button.focus();
    expect(document.activeElement).toBe(button);
  });

  it("FR-019-40 · the cut counts characters, not UTF-16 units: an emoji across the 200th place is not split", async () => {
    const value = `${"e".repeat(199)}\u{1f600}${"f".repeat(10)}`; // 210 code points, the emoji is the 200th
    await render(value);
    expect(shown()).toBe(`${"e".repeat(199)}\u{1f600}…`);
    expect(/[\ud800-\udbff](?![\udc00-\udfff])|(?<![\ud800-\udbff])[\udc00-\udfff]/.test(shown())).toBe(
      false,
    );
  });

  it("FR-019-40 · control characters are removed before counting, and a hostile string over 200 characters is both escaped and cut", async () => {
    await render(`\u0000<script>window.__pwned=1</script>${"s".repeat(300)}`);
    expect(hasControl(shown())).toBe(false);
    expect(root().getAttribute("data-truncated")).toBe("true");
    expect(document.querySelector("script")).toBeNull();
  });

  it("FR-019-40 · the visible text is never longer than 201 code points before expansion, whatever the input length (20,000, 1,000,000)", async () => {
    for (const n of [20_000, 1_000_000]) {
      const { unmount } = await render("q".repeat(n));
      expect([...shown()].length).toBe(201);
      unmount();
    }
  });
});

describe("the studio blocks use it (FR-019-40)", () => {
  it("FR-019-40 · the role of a tool with markup and 5,000 characters is escaped and truncated with an expander", async () => {
    await renderApp(
      createElement(RoleBlock, {
        tool: makeTool("warp", { role: `<img src=x onerror=alert(1)>${"r".repeat(5000)}` }) as never,
        cases: loadCaseRegistry() as never,
      }),
    );
    const block = document.querySelector('section[data-block="role"]') as HTMLElement;
    expect(block.querySelector("img")).toBeNull();
    expect(within(block).getByTestId("expand")).toBeTruthy();
    expect(block.textContent?.length ?? 0).toBeLessThan(1000);
  });

  it("FR-019-40 · a rejected-alternative reason and a probe error are cut the same way", async () => {
    await renderApp(
      createElement(AlternativesBlock, {
        tool: makeTool("warp", { alternatives_rejected: [{ name: "n", reason: "x".repeat(300) }] }) as never,
      }),
    );
    expect(
      within(document.querySelector('section[data-block="alternatives"]') as HTMLElement).getByTestId(
        "expand",
      ),
    ).toBeTruthy();
    document.body.innerHTML = "";
    await renderApp(
      createElement(IdentityBlock, {
        tool: makeTool("warp") as never,
        info: indexTool("warp", {
          probe: {
            status: "fail",
            name: "p",
            date: "2026-10-03",
            gpu: "G",
            driver: "1",
            error: "E".repeat(400),
          },
        }) as never,
      }),
    );
    expect(
      within(document.querySelector('section[data-block="identity"]') as HTMLElement).getByTestId("expand"),
    ).toBeTruthy();
  });
});
