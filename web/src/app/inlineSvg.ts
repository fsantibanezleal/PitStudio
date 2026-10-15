// Prepares a docs diagram (docs/assets/diagrams/*.svg) for inlining in the information modal (FR-020-43).
//
// The files carry their own token block (`.psd{--bg:#fff;...}` and its dark-mode copy) so that they render alone. Inlined in
// the app, that block is removed so every colour comes from the app's own theme tokens (`--bg`, `--fg`, ... of tokens.css),
// which repaint on a theme change without a reload; the remaining rules are scoped to the diagram (`.psd .box`, ...) so
// their generic class names cannot reach the rest of the page. The guard of the files themselves is
// tools/check_inline_svg.py (FR-020-51).

const TOKEN_MEDIA = /@media\s*\(prefers-color-scheme:\s*dark\)\s*\{\s*\.psd\s*\{[^{}]*\}\s*\}/g;
const TOKEN_RULE = /\.psd\s*\{[^{}]*--[a-z0-9-]+\s*:[^{}]*\}/g;
const RULE = /([^{}]+)\{([^{}]*)\}/g;

function scope(css: string): string {
  return css.replace(RULE, (_all, selectors: string, body: string) => {
    const scoped = selectors
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean)
      .map((s) => (s.startsWith(".psd") ? s : `.psd ${s}`))
      .join(", ");
    return scoped ? `${scoped}{${body}}` : "";
  });
}

/** The diagram markup with its token block removed and its remaining style rules scoped to `.psd`. */
export function inlineDiagram(svg: string): string {
  return svg.replace(
    /(<style[^>]*>)([\s\S]*?)(<\/style>)/g,
    (_all, open: string, css: string, close: string) => {
      const withoutTokens = css
        .replace(/\/\*[\s\S]*?\*\//g, "")
        .replace(TOKEN_MEDIA, "")
        .replace(TOKEN_RULE, "");
      return `${open}${scope(withoutTokens)}${close}`;
    },
  );
}
