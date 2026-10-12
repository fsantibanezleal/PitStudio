// T-020-061 [red] · FR-020-46: for every text colour token and every surface token it can sit on, in both themes, the contrast ratio computed with the WCAG 2.2 relative-luminance formula is at least 4.5:1 for normal text and at least 3:1 for
// large text and non-text marks.
//
// Expected API: `~/shell/contrast` (web/src/shell/contrast.ts):
//   relativeLuminance(hex: string): number     WCAG 2.2 relative luminance of a #rrggbb colour (sRGB transfer with the 0.03928 / 12.92 and 0.055 / 1.055 ^ 2.4 constants, weights 0.2126, 0.7152, 0.0722);
//   contrastRatio(foreground: string, background: string): number   (lighter + 0.05) / (darker + 0.05), symmetric, in [1, 21]; RangeError for a colour that is not #rrggbb;
//   parseTokens(css: string): { light: Record<string, string>; dark: Record<string, string> }   the colour tokens (`--name: #rrggbb`) of the `:root, [data-theme="light"]` and `[data-theme="dark"]` blocks, without the `--` prefix;
//   TEXT_ON: Record<string, string[]>   for each text token the surface tokens it can sit on: fg, fg-muted, fg-subtle, link, code, danger, success, warning, info on bg, surface, surface-2; primary-soft-fg on primary-soft; primary-fg on primary;
//                                        (`primary` as body text is not in the map: tokens.css says it is never body text in dark mode);
//   MARKS_ON: Record<string, string[]>  for each non-text mark token (border-strong, ring, accent, chart-1 .. chart-6) the surfaces on bg, surface, surface-2.
// The token check below uses its own implementation of the formula (the published WCAG definition) and web/src/shell/tokens.css; the module under test must agree with the published values on the hand cases.
// Oracles: WCAG 2.2 relative luminance and contrast ratio definitions (W3C, https://www.w3.org/TR/WCAG22/#dfn-relative-luminance and #dfn-contrast-ratio): black on white 21:1, a colour on itself 1:1, #767676 on white 4.54:1 (the lightest
// grey that passes 4.5 on white), #777777 on white 4.48:1 (just below), #808080 on white 3.95:1.
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import fc from "fast-check";
import { describe, expect, it } from "vitest";
import { contrastRatio, MARKS_ON, parseTokens, relativeLuminance, TEXT_ON } from "~/shell/contrast";

const css = readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), "tokens.css"), "utf8");

// the published definition, written out independently of the module under test
const channel = (c: number) => (c / 255 <= 0.03928 ? c / 255 / 12.92 : ((c / 255 + 0.055) / 1.055) ** 2.4);
const lum = (hex: string) =>
  0.2126 * channel(Number.parseInt(hex.slice(1, 3), 16)) +
  0.7152 * channel(Number.parseInt(hex.slice(3, 5), 16)) +
  0.0722 * channel(Number.parseInt(hex.slice(5, 7), 16));
const ratio = (a: string, b: string) => (Math.max(lum(a), lum(b)) + 0.05) / (Math.min(lum(a), lum(b)) + 0.05);

describe("the WCAG formula (FR-020-46)", () => {
  it("FR-020-46 · relative luminance: black 0, white 1, mid grey #808080 about 0.2158", () => {
    expect(relativeLuminance("#000000")).toBe(0);
    expect(relativeLuminance("#ffffff")).toBeCloseTo(1, 12);
    expect(relativeLuminance("#808080")).toBeCloseTo(0.21586, 4);
  });

  it("FR-020-46 · primaries: pure red 0.2126, green 0.7152, blue 0.0722", () => {
    expect(relativeLuminance("#ff0000")).toBeCloseTo(0.2126, 12);
    expect(relativeLuminance("#00ff00")).toBeCloseTo(0.7152, 12);
    expect(relativeLuminance("#0000ff")).toBeCloseTo(0.0722, 12);
  });

  it("FR-020-46 · published ratios: black on white 21, a colour on itself 1, #767676 on white 4.54, #777777 on white 4.48, #808080 on white 3.95", () => {
    expect(contrastRatio("#000000", "#ffffff")).toBeCloseTo(21, 9);
    expect(contrastRatio("#abcdef", "#abcdef")).toBeCloseTo(1, 12);
    expect(contrastRatio("#767676", "#ffffff")).toBeCloseTo(4.54, 2);
    expect(contrastRatio("#777777", "#ffffff")).toBeCloseTo(4.48, 2);
    expect(contrastRatio("#808080", "#ffffff")).toBeCloseTo(3.95, 2);
  });

  it("FR-020-46 · the ratio is symmetric and within [1, 21] for any two colours, and agrees with the independent formula", () => {
    const hex = fc
      .array(fc.integer({ min: 0, max: 255 }), { minLength: 3, maxLength: 3 })
      .map(([r, g, b]) => `#${[r, g, b].map((x) => (x as number).toString(16).padStart(2, "0")).join("")}`);
    fc.assert(
      fc.property(hex, hex, (a, b) => {
        const r = contrastRatio(a, b);
        expect(r).toBeGreaterThanOrEqual(1);
        expect(r).toBeLessThanOrEqual(21 + 1e-9);
        expect(contrastRatio(b, a)).toBeCloseTo(r, 12);
        expect(r).toBeCloseTo(ratio(a, b), 9);
      }),
      { numRuns: 200 },
    );
  });

  it("FR-020-46 · a colour that is not #rrggbb is a RangeError, not NaN", () => {
    for (const bad of ["", "fff", "#fff", "#ggg000", "#12345", "#1234567", "red", "rgb(0,0,0)", " #ffffff"]) {
      expect(() => contrastRatio(bad, "#ffffff"), bad).toThrow(RangeError);
      expect(() => relativeLuminance(bad), bad).toThrow(RangeError);
    }
  });
});

describe("the tokens of tokens.css (FR-020-46)", () => {
  const tokens = parseTokens(css);

  it("FR-020-46 · parseTokens reads both themes: light --bg #ffffff and dark --bg #0f0b14, --fg #1b1523 and #f4f0f8", () => {
    expect(tokens.light.bg).toBe("#ffffff");
    expect(tokens.dark.bg).toBe("#0f0b14");
    expect(tokens.light.fg).toBe("#1b1523");
    expect(tokens.dark.fg).toBe("#f4f0f8");
    expect(Object.keys(tokens.light).sort()).toEqual(Object.keys(tokens.dark).sort());
  });

  it("FR-020-46 · the map of text tokens covers every text colour of the file and the surfaces it can sit on", () => {
    for (const t of [
      "fg",
      "fg-muted",
      "fg-subtle",
      "link",
      "code",
      "danger",
      "success",
      "warning",
      "info",
      "primary-soft-fg",
      "primary-fg",
    ])
      expect(TEXT_ON[t], t).toBeDefined();
    for (const t of ["fg", "fg-muted", "fg-subtle", "link", "code", "danger", "success", "warning", "info"])
      expect([...(TEXT_ON[t] ?? [])].sort(), t).toEqual(["bg", "surface", "surface-2"]);
    expect(TEXT_ON["primary-soft-fg"]).toEqual(["primary-soft"]);
    expect(TEXT_ON["primary-fg"]).toEqual(["primary"]);
    expect(TEXT_ON.primary).toBeUndefined();
  });

  for (const theme of ["light", "dark"] as const) {
    it(`FR-020-46 · ${theme}: every text token on every surface it can sit on has a ratio of at least 4.5:1`, () => {
      const t = tokens[theme];
      const failures: string[] = [];
      for (const [text, surfaces] of Object.entries(TEXT_ON)) {
        for (const surface of surfaces) {
          const fg = t[text] as string;
          const bg = t[surface] as string;
          expect(fg, `${theme} --${text}`).toMatch(/^#[0-9a-f]{6}$/i);
          expect(bg, `${theme} --${surface}`).toMatch(/^#[0-9a-f]{6}$/i);
          const r = ratio(fg, bg);
          if (r < 4.5) failures.push(`${theme}: --${text} on --${surface} is ${r.toFixed(2)}:1`);
          expect(contrastRatio(fg, bg), `${theme} ${text} on ${surface}`).toBeCloseTo(r, 9);
        }
      }
      expect(failures).toEqual([]);
    });

    it(`FR-020-46 · ${theme}: every non-text mark (border-strong, ring, accent, the six chart colours) on every surface has a ratio of at least 3:1`, () => {
      const t = tokens[theme];
      expect(Object.keys(MARKS_ON).sort()).toEqual([
        "accent",
        "border-strong",
        "chart-1",
        "chart-2",
        "chart-3",
        "chart-4",
        "chart-5",
        "chart-6",
        "ring",
      ]);
      const failures: string[] = [];
      for (const [mark, surfaces] of Object.entries(MARKS_ON)) {
        expect([...surfaces].sort(), mark).toEqual(["bg", "surface", "surface-2"]);
        for (const surface of surfaces) {
          const r = ratio(t[mark] as string, t[surface] as string);
          if (r < 3) failures.push(`${theme}: --${mark} on --${surface} is ${r.toFixed(2)}:1`);
        }
      }
      expect(failures).toEqual([]);
    });
  }

  it("FR-020-46 · a planted low-contrast token is caught: #777777 text on a white surface fails the 4.5 bound that the check applies", () => {
    expect(contrastRatio("#777777", "#ffffff")).toBeLessThan(4.5);
    const planted = parseTokens(css.replace("--fg-muted: #5c5468", "--fg-muted: #777777"));
    expect(ratio(planted.light["fg-muted"] as string, planted.light.bg as string)).toBeLessThan(4.5);
  });

  it("FR-020-46 · parseTokens ignores comments, non-colour custom properties and rgb() values", () => {
    const parsed = parseTokens(
      ':root,\n[data-theme="light"] { --a: #112233; /* --b: #445566; */ --c: 4px; --d: rgb(1,2,3); }\n[data-theme="dark"] { --a: #ffffff; }',
    );
    expect(parsed.light).toEqual({ a: "#112233" });
    expect(parsed.dark).toEqual({ a: "#ffffff" });
  });
});
