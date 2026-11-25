// WCAG 2.2 contrast (FR-020-46): relative luminance and contrast ratio of #rrggbb colours, and the token maps the
// check in t_020_061_contrast.test.ts applies to web/src/shell/tokens.css.
// https://www.w3.org/TR/WCAG22/#dfn-relative-luminance and #dfn-contrast-ratio

const HEX = /^#[0-9a-fA-F]{6}$/;

function channel(c: number): number {
  const s = c / 255;
  return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
}

export function relativeLuminance(hex: string): number {
  if (typeof hex !== "string" || !HEX.test(hex)) throw new RangeError(`not a #rrggbb colour: ${String(hex)}`);
  const r = Number.parseInt(hex.slice(1, 3), 16);
  const g = Number.parseInt(hex.slice(3, 5), 16);
  const b = Number.parseInt(hex.slice(5, 7), 16);
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

export function contrastRatio(foreground: string, background: string): number {
  const a = relativeLuminance(foreground);
  const b = relativeLuminance(background);
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
}

/** The colour tokens (`--name: #rrggbb`) of the light and dark blocks, without the `--` prefix. */
export function parseTokens(css: string): { light: Record<string, string>; dark: Record<string, string> } {
  const stripped = css.replace(/\/\*[\s\S]*?\*\//g, "");
  const out = { light: {} as Record<string, string>, dark: {} as Record<string, string> };
  const blocks: Array<["light" | "dark", RegExp]> = [
    ["light", /:root\s*,\s*\[data-theme="light"\]\s*\{([^}]*)\}/],
    ["dark", /\[data-theme="dark"\]\s*\{([^}]*)\}/],
  ];
  for (const [theme, re] of blocks) {
    const body = re.exec(stripped)?.[1] ?? "";
    for (const m of body.matchAll(/--([a-z0-9-]+)\s*:\s*(#[0-9a-fA-F]{6})\s*;/g)) {
      out[theme][m[1] as string] = m[2] as string;
    }
  }
  return out;
}

const SURFACES = ["bg", "surface", "surface-2"];

export const TEXT_ON: Record<string, string[]> = {
  fg: SURFACES,
  "fg-muted": SURFACES,
  "fg-subtle": SURFACES,
  link: SURFACES,
  code: SURFACES,
  danger: SURFACES,
  success: SURFACES,
  warning: SURFACES,
  info: SURFACES,
  "primary-soft-fg": ["primary-soft"],
  "primary-fg": ["primary"],
};

export const MARKS_ON: Record<string, string[]> = Object.fromEntries(
  ["border-strong", "ring", "accent", "chart-1", "chart-2", "chart-3", "chart-4", "chart-5", "chart-6"].map(
    (m) => [m, SURFACES],
  ),
);
