# Access gate — threat note

> The site's demo gate compares a typed passphrase with a SHA-256 digest baked in at build time and remembers success
> in `sessionStorage`; it is a UX convention that keeps casual visitors on the landing view, **not security**. · Part
> of: [Web](README.md) · Related: [structure](structure.md) · [user flow](user-flow.md) ·
> [configuration](../reference/configuration.md) · [deployment](../architecture/deployment.md)

## What and why

PitStudio is a public research project whose web app is a work in progress. The gate exists so that a casual visitor
who lands on the site sees a "demo access" screen that says what the site is, rather than half-built pages. It is
**soft by design**: there is no server, so there is nothing that could enforce access, and the gate says on screen that
it is not a security boundary. This page states exactly what it does, what it does not protect, and how it is
configured, so that nobody mistakes it for a control.

![Access gate threat note](../assets/diagrams/access-gate-threat.svg)

*The passphrase becomes a public digest at build time; the browser compares against it and remembers success for the
tab. The right-hand column is the threat note.*

## How it works

### Build time

`web/vite.config.ts` calls `accessDigest(process.env.ACCESS_PASSPHRASE)` from `web/build-info.ts` and inlines the
result as the constant `__ACCESS_DIGEST__`:

```ts
// web/build-info.ts (excerpt)
export function accessDigest(passphrase: string | undefined): string {
  const phrase = passphrase?.trim();
  return phrase ? createHash("sha256").update(phrase, "utf8").digest("hex") : "";
}
```

- The phrase is trimmed, encoded as UTF-8 and hashed with SHA-256 (Node's `crypto`); only the 64-character hex digest
  reaches the bundle.
- No `ACCESS_PASSPHRASE` → empty digest → **the gate is off** (local development).
- The deploy workflow (`.github/workflows/pages.yml`) passes the repository secret `ACCESS_PASSPHRASE` to the build and
  to the e2e run. The CI workflow (`.github/workflows/ci.yml`) uses the public test phrase `ci-demo-gate`; that build
  is never deployed.

### Run time

`web/src/shell/AccessGate.tsx` wraps every route (it sits in the root layout around `<Outlet />`):

1. With an empty digest it renders the page directly.
2. Otherwise it reads `sessionStorage["PitStudio:access"]`. If the stored value equals the digest, the page opens.
3. Otherwise it shows the gate: a title, the notice "Demo access gate — not a security boundary. All content of this
   site is public; the gate only keeps casual visitors on the landing view.", a password field and a button.
4. On submit, `matchesDigest()` in `web/src/shell/digest.ts` hashes the trimmed input with the Web Crypto API
   (`crypto.subtle.digest("SHA-256", …)`) and compares the lowercase hex with the digest. On a match it stores the
   digest under `PitStudio:access` and opens; otherwise it shows "That passphrase does not match." and stays locked.
5. If storage is blocked, the gate opens for the current page only and asks again on the next load.

Details that matter:

- The storage key is namespaced by repository (`accessKey(repo)` → `PitStudio:access`) because every project published
  under the same `github.io` origin shares that origin's storage.
- `sessionStorage` is partitioned by origin **and** tab, survives reloads, and is cleared when the tab closes [1]. A new
  tab asks again.
- `crypto.subtle.digest` is available only in secure contexts (HTTPS, or `localhost` in development) [2]. Pages serves
  HTTPS.
- In a gated build the prerendered HTML contains the shell and a "Loading…" status, not the page body; the body is
  rendered by JavaScript after the check.
- When the gate is on, the footer adds: "The access gate is a demo gate, not a security boundary: all content of this
  site is public."

## Threat model

| Asset or concern | Threat | Protected? | Why |
|---|---|---|---|
| Page content, data, models, media | Direct download of any file URL | **No** | Every file in the Pages artifact is public; the JS chunks contain the page text |
| The gate itself | Bypass by writing the digest into `sessionStorage`, or editing the JS in devtools | **No** | The digest ships in the public bundle; the check runs on the client |
| The passphrase | Offline guessing from the public digest | **Weak** | SHA-256 is a fast, unsalted hash; OWASP: fast hashes "allow attackers to perform large numbers of guesses quickly" [3]. A short or common phrase falls to a dictionary |
| The passphrase | Read from the bundle or the repository | Yes | Only the digest is shipped; the phrase is a repository secret, never committed |
| Source code and docs | Read on GitHub | **No** | The repository is public by design |
| Visitor privacy | Tracking by the gate | Yes | The phrase is compared in the browser and never sent; no cookies; nothing is stored beyond the tab session |
| Identity and authorisation | Per-user access, revocation, audit | **No** | There are no accounts and no server |
| Transport | Tampering in transit | Pages' HTTPS only | The gate adds nothing |

**Rule that follows:** never publish anything that needs protection. Everything on the site is public; the gate only
changes what a casual visitor sees first. Real access control needs a server or a private host, which this project
deliberately does not have.

## Operating the gate

| Task | How |
|---|---|
| Turn the gate on for the deployed site | Set the repository secret `ACCESS_PASSPHRASE` (maintainer); the next `pages.yml` run builds with it |
| Turn it off | Delete the secret; the build gets an empty digest |
| Change the phrase | Change the secret and redeploy; open tabs keep their session until closed, new tabs need the new phrase |
| Build locally with the gate | `ACCESS_PASSPHRASE` in the environment of `pnpm build` ([configuration](../reference/configuration.md)) |
| Build locally without it | Leave `ACCESS_PASSPHRASE` unset |

Choose a phrase that is long and not a dictionary phrase, knowing that this only slows guessing and protects nothing.

```bash run
cd web && pnpm install && pnpm build
```

Without `ACCESS_PASSPHRASE` in the environment this build has no gate.

## Tests

| Test | What it pins |
|---|---|
| `web/src/shell/digest.test.ts` | SHA-256 against the FIPS 180-2 vectors ("abc", empty string); UTF-8 input; trimming; digest case ignored; an empty digest never matches; the session key is `PitStudio:access` |
| `web/src/shell/AccessGate.test.tsx` | No digest → content shown; with a digest → locked, states it is not a security boundary, rejects a wrong phrase, opens on the right one |
| `web/e2e/shell.spec.ts` ("access gate") | On the production build: locks the workbench, shows the notice, unlocks for the session across routes; hostile inputs (markup, SQL-like text, 20,000 characters, control characters) keep it locked without breaking it |

```bash run
cd web && pnpm run test
```

## Assumptions and limits

- The gate assumes nothing confidential is ever in the Pages artifact. The repository checks (`tools/check_repo.py`)
  scan tracked files for secrets and machine paths; they do not and cannot make a public site private.
- The gate is not an accessibility barrier: it is a labelled form, keyboard-operable, announced to screen readers, and
  covered by the axe checks.

## In PitStudio

- Foundation requirement FR-000-04 ("When a visitor opens the site, the web app shall require the access gate before
  showing the workbench") in `specs/000-foundation/spec.md`.
- Status: implemented and tested in the shell; the deployed site is built with the repository secret.

## References

1. MDN, `Window.sessionStorage` — partitioned by origin and tab; cleared when the tab closes. https://developer.mozilla.org/en-US/docs/Web/API/Window/sessionStorage
2. MDN, `SubtleCrypto.digest()` — available only in secure contexts (HTTPS). https://developer.mozilla.org/en-US/docs/Web/API/SubtleCrypto/digest
3. OWASP, "Password Storage Cheat Sheet" — fast hashes such as SHA-256 are unsuitable for password storage. https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html
