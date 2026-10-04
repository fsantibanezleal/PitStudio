# web/

The PitStudio web companion: React 19 + Vite 8 + React Router 8 (framework mode, `ssr: false`, every static route
prerendered to HTML), deployed to GitHub Pages at `/PitStudio/`.

## Run it

```bash
cd web
pnpm install                 # pnpm version comes from "packageManager" (Corepack)
pnpm dev                     # http://localhost:5173/
pnpm run check               # Biome + route typegen + tsc + Vitest
```

Production build served the way GitHub Pages serves it:

```bash
BASE_PATH=/PitStudio/ ACCESS_PASSPHRASE=<demo phrase> pnpm build
BASE_PATH=/PitStudio/ pnpm serve                       # http://localhost:4173/PitStudio/
BASE_PATH=/PitStudio/ ACCESS_PASSPHRASE=<demo phrase> pnpm test:e2e
```

- `BASE_PATH` sets both the Vite `base` and the router `basename`. In CI it comes from `actions/configure-pages`.
- `scripts/postbuild.mjs` shapes `build/client/` into the Pages artifact (the prerendered tree at the root, the SPA
  fallback as `404.html`) and fails the build if the start page loads more than 200 KB of gzip JavaScript.
- `scripts/serve-static.mjs` mimics Pages: real files, `dir/` → `dir/index.html`, unknown paths → `404.html` with
  status 404.

## Layout

| Path | What |
|---|---|
| `src/shell/` | The shared shell: header, footer, access gate, theme, language, ⓘ architecture view, tokens |
| `src/app/` | This app's shell configuration and ⓘ tab content |
| `src/routes/` | One module per page |
| `src/locales/{en,es}/` | All user-visible text (`shell` and `app` namespaces) |
| `e2e/` | Playwright tests against the production build; `e2e/live/` runs against the deployed site |

## Access gate

The site shows a **demo access gate**. It is not a security boundary and says so on screen: everything published here
is public. The build receives the phrase as `ACCESS_PASSPHRASE` and only its SHA-256 digest reaches the bundle.
Without `ACCESS_PASSPHRASE` the gate is off (local development).

## Language and theme

English is the default; Spanish is available everywhere. Priority: `?lang=` in the URL, then the stored choice, then
English. The browser language is never used. Theme: system, light or dark, applied before first paint.
