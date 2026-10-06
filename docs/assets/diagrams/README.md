# Diagrams

Every diagram in the wiki is a hand-written, theme-aware SVG in this folder. The SVG file is its own source; there is
no separate export step. Small flows may instead be Mermaid code blocks inside a page; GitHub renders those natively
in both themes.

## Rules

- **SVG only**, never a raster screenshot. The canvas is 880–1200 px wide (`viewBox`), with no fixed `width`/`height`
  so it scales with the page.
- **No colour literal in any drawing element.** Every fill and stroke is a palette token (`var(--…)`). The token
  values are declared once, in the `<style>` block at the top of the file. They are the web app's tokens
  (`web/src/shell/tokens.css`): light by default, dark under `@media (prefers-color-scheme: dark)`.
- **Density.** Every box has a title, a real code or file path, 1–3 item lines and, where it matters, a caveat. Every
  meaningful arrow is labelled with what moves along it. Use bands or lanes and nested boxes; keep about 7 top-level
  nodes or fewer. Text is ≥ 13 px.
- **Semantics.**
  - `--accent` marks the highlighted path.
  - `--success` / `--warning` / `--danger` mark states.
  - `--chart-1…6` mark categories.
  - Lanes use the same colours everywhere:

    | Lane | Colour |
    |---|---|
    | live | `--chart-2` |
    | precompute / replay | `--chart-4` |
    | local-only | `--warning` |
- **Contrast.** Text is ≥ 4.5:1 against every surface it sits on, in both themes. Code paths use `--code`
  (6.8:1 light, 5.8:1 dark at worst); never fill small text with `--primary` (3.0:1 in dark mode).
- **Accessible.** Each SVG has `role="img"`, a `<title>` and a `<desc>` that says in one sentence what the diagram
  shows.
- **Verify in both themes.** Open the file in a browser with the OS in light mode and again in dark mode. Never use
  decorative 3D, drop shadows or rainbow palettes.
- **Names.** Lowercase kebab-case, e.g. `runner-architecture.svg`. Pages embed a diagram as
  `![Short alt text](../assets/diagrams/runner-architecture.svg)` with a one-line caption under it.

## Template

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 560" role="img" aria-labelledby="t d" class="psd">
  <title id="t">Diagram title</title>
  <desc id="d">One sentence on what the diagram shows.</desc>
  <style>
    .psd{--bg:#ffffff;--surface:#f7f4fb;--surface-2:#eee8f5;--fg:#1b1523;--fg-muted:#5c5468;--border:#ddd6e6;
      --border-strong:#7d7589;--primary:#7500c0;--code:#7500c0;--accent:#a100ff;--primary-soft:#f1e3ff;--danger:#b42318;
      --success:#067647;--warning:#93370d;--info:#175cd3;--chart-1:#7500c0;--chart-2:#0e7c86;--chart-3:#c2410c;
      --chart-4:#1d4ed8;--chart-5:#be185d;--chart-6:#4d7c0f}
    @media (prefers-color-scheme: dark){.psd{--bg:#0f0b14;--surface:#1a1521;--surface-2:#251e2e;--fg:#f4f0f8;
      --fg-muted:#b7aec3;--border:#352c40;--border-strong:#8c829b;--primary:#a100ff;--code:#be82ff;--accent:#be82ff;
      --primary-soft:#2e1a47;--danger:#fda29b;--success:#75e0a7;--warning:#fec84b;--info:#84adff;--chart-1:#be82ff;
      --chart-2:#2dd4bf;--chart-3:#fb923c;--chart-4:#60a5fa;--chart-5:#f472b6;--chart-6:#a3e635}}
    .bg{fill:var(--bg)}
    .band{fill:var(--surface);stroke:var(--border);stroke-width:1}
    .box{fill:var(--surface-2);stroke:var(--border-strong);stroke-width:1.5}
    .box-accent{fill:var(--primary-soft);stroke:var(--accent);stroke-width:2}
    .title{font:600 15px Inter,system-ui,sans-serif;fill:var(--fg)}
    .path{font:13px "JetBrains Mono",ui-monospace,monospace;fill:var(--code)}
    .item{font:13px Inter,system-ui,sans-serif;fill:var(--fg-muted)}
    .caveat{font:italic 13px Inter,system-ui,sans-serif;fill:var(--warning)}
    .label{font:13px Inter,system-ui,sans-serif;fill:var(--fg)}
    .edge{stroke:var(--fg-muted);stroke-width:1.5;fill:none}
    .edge-accent{stroke:var(--accent);stroke-width:2.2;fill:none}
    .arrowhead{fill:var(--fg-muted)}
  </style>
  <defs>
    <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">
      <path d="M0,0 L10,5 L0,10 z" class="arrowhead"/>
    </marker>
  </defs>
  <rect class="bg" width="1000" height="560"/>
  <!-- bands, boxes (title + path + items + caveat), labelled edges with marker-end="url(#arrow)" -->
</svg>
```

The web app inlines these files and overrides the `.psd` token block with its own `data-theme` tokens, so a diagram
follows the app's theme switch rather than the operating system's.
