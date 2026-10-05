# DEC-0007: Large web assets are release assets copied at build

> Baked files under 10 MB live in git (at most 100 MB in total); larger files, and small-file classes beyond that total,
> are GitHub Release assets under `assets-vX.YY.ZZZ` tags, pinned by SHA-256 and copied into the Pages artifact by
> `pages.yml`, so the browser only ever talks to its own origin. · Part of: [decisions](README.md) · Related:
> [deployment](../deployment.md) · [budgets](../../web/budgets.md) · [release and cite](../../guides/release-and-cite.md)

**Status:** Accepted, 2026-10-04

## Context

The site's budget allows up to 500 MB, including about 150 MB of video, 95 MB of tiles and glb files, 60 MB of replay
shards and point clouds, 25 MB of splats and 80 MB of ONNX models ([budgets](../../web/budgets.md)). Many of these files
are larger than 10 MB, and they are re-baked whenever a scene or a model changes.

- GitHub warns about files above 50 MiB and blocks files above 100 MiB [1]; every committed and later replaced binary
  stays in the history forever.
- Git LFS cannot be used with GitHub Pages sites [2].
- A Pages site may be at most 1 GB [3].
- A release asset may be up to 2 GiB, a release may hold up to 1,000 assets, and GitHub sets no limit on the total size
  of a release or its bandwidth [4].
- Hugging Face Hub is an option the maintainer already has an account for, but publishing needs a write token, and a
  second host adds a second set of terms.

## Decision

- **Split by size.** Git holds only baked files < 10 MB, at most 100 MB of baked assets in total. Everything larger
  (videos, splats, models > 10 MB) is a GitHub Release asset of the PitStudio repository. **Overflow rule:** small-file
  classes beyond the in-git cap (for example terrain tiles or replay shards) ship as release-asset archives unpacked at
  build.
- **Pinned and same-origin.** Every release asset is listed in the manifest with its SHA-256. `pages.yml` downloads the
  assets by tag at build time, verifies each checksum and copies them into the Pages artifact. The browser never fetches
  a release asset; the site serves everything from its own origin.
- **Release flow** (compatible with immutable releases): create `assets-vX.YY.ZZZ` as a draft, upload, verify every
  SHA-256 against the manifest, then publish with `--latest=false`. Every re-bake gets a new tag. The product release
  `vX.YY.ZZZ`, cut by `tools/release.py`, stays "Latest".
- **History policy.** Heavy assets are re-baked only at releases. CI checks every file size, the in-git total and the
  repository size. `tools/check_repo.py` already fails on any tracked file above 10 MB.
- **Alternative host for > 2 GiB.** A Hugging Face Hub repository under the maintainer's existing account, used only if a
  single asset exceeds the release-asset limit.

## Alternatives considered

| Option | Pros | Cons | Why rejected |
|---|---|---|---|
| Large files in git | One place for everything | 100 MiB hard limit; history grows with every re-bake [1] | History growth past 1 GB is a stated risk |
| Git LFS | Familiar workflow | Cannot be used with GitHub Pages sites [2]; bandwidth quotas | Does not serve the site |
| Browser fetches release assets directly | No copy step | Cross-origin downloads from another host; the site would depend on an external URL at run time | The site must stay same-origin and self-contained |
| Hugging Face Hub as the default host | Large-file friendly | Needs a write token; a second set of terms; a run-time dependency on another host | Kept for > 2 GiB only |

## Consequences

**Positive.** No extra account; no git history growth; every byte the browser loads is pinned by checksum and served
from Pages; asset releases are reproducible by tag.

**Negative, accepted.** A copy step in `pages.yml` and a release procedure with a verification step; asset tags
accumulate over time.

**Watch.** GitHub's release and Pages limits; the in-git total as tiles and shards grow; repository size.

**Status.** The copy step and the first asset release arrive in the build phase; today's `pages.yml` deploys the web
shell only.

## References

1. GitHub Docs. About large files on GitHub.
   https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github
2. GitHub Docs. About Git Large File Storage.
   https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-git-large-file-storage
3. GitHub Docs. GitHub Pages limits. https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits
4. GitHub Docs. About releases. https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases
