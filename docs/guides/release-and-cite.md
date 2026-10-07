# Release and cite

> How PitStudio versions (`X.YY.ZZZ`), cuts a release with `tools/release.py`, keeps asset releases separate, and how to
> cite PitStudio, `minephys` and the data behind a result. · Part of: [Guides](README.md) · Related:
> [budgets](../web/budgets.md) · [deployment](../architecture/deployment.md) ·
> [sources and licences](../data-contract/sources-and-licences.md) · [minephys](../frameworks/minephys.md)

## What and why

**Goal:** every published state of PitStudio has one version number that appears identically in the footer of the
site, the git tag, the changelog and the citation file, so that a result can be cited and found again. Releases are
cut by a script, not by hand, from the commit history.

## Versioning

| Where | Form | Example |
|---|---|---|
| `VERSION`, git tag, `CHANGELOG.md`, `CITATION.cff`, site footer | zero-padded `X.YY.ZZZ`, tag `vX.YY.ZZZ` | `0.01.000`, `v0.01.000` |
| `pyproject.toml`, `web/package.json` | normalised `X.Y.Z` | `0.1.0` |
| Asset releases (large web assets) | tag `assets-vX.YY.ZZZ` | `assets-v0.01.000` |

Package managers get the normalised form because Semantic Versioning forbids leading zeroes ("X, Y, and Z are
non-negative integers, and MUST NOT contain leading zeroes") [1] and Python versions are compared as integers [2].

**Bump rules** (Conventional Commits since the last `v*` tag):

| Commits since the last tag contain | Next version |
|---|---|
| `BREAKING CHANGE`, or a type with `!` (e.g. `feat!:`) | `X+1.00.000` |
| at least one `feat:` | `X.YY+1.000` |
| anything else | `X.YY.ZZZ+1` |

The current version is `0.00.000` (`VERSION`). The first product release planned is `v0.01.000`, together with the
first PyPI release of `minephys`.

## Steps

1. **Dry run.** Prints the computed next version, its normalised form and the release notes grouped by type (Added,
   Fixed, Changed, Documentation, Tests, Maintenance). It changes nothing.

   ```bash run
   uv run python tools/release.py
   ```

2. **Apply** (maintainer, on the release branch). Writes `VERSION`, the `pyproject.toml` and `web/package.json`
   versions, `CITATION.cff` (`version`, `date-released`), inserts the notes under `## [Unreleased]` in `CHANGELOG.md`,
   writes `release-notes.md`, commits `chore(release): vX.YY.ZZZ` and creates the annotated tag. `--version X.YY.ZZZ`
   forces a version.

   ```bash
   uv run python tools/release.py --apply
   git push --follow-tags
   gh release create vX.YY.ZZZ --notes-file release-notes.md
   ```

   Changes flow `task/<slug>` → `develop` → a release pull request into `main`; Pages deploys from `main`, and the
   deployed SHA must equal the validated one.

3. **Asset release, if heavy web assets changed.** A separate `assets-vX.YY.ZZZ` release, created as a draft, verified
   file by file against the manifest's SHA-256, then published with `--latest=false` so the product release stays
   "Latest" ([budgets](../web/budgets.md#asset-release-flow)).

   ```bash run deferred=P6
   gh release edit assets-v0.01.000 --draft=false --latest=false
   ```

4. **`minephys`.** The companion library is a git dependency (pinned to a commit in `uv.lock`) until its first release,
   which goes to TestPyPI and then PyPI through trusted publishing; the maintainer registers the two pending publishers
   once.

## Expected output

- Dry run: a line of the form `release <current> -> <next> (<normalised> for package managers)`, then the notes; or
  `nothing to release` when there are no commits since the last tag.
- Apply: `tagged vX.YY.ZZZ. Next: git push --follow-tags && gh release create vX.YY.ZZZ --notes-file release-notes.md`.
- After deploy: the site footer shows the new version, the short commit SHA and the build date.

## How to cite

GitHub reads `CITATION.cff` from the default branch and offers "Cite this repository" in APA and BibTeX [3]. The
current file:

```yaml
cff-version: 1.2.0
title: "PitStudio"
authors:
  - family-names: "Santibanez-Leal"
    given-names: "Felipe A."
repository-code: "https://github.com/fsantibanezleal/PitStudio"
url: "https://fsantibanezleal.github.io/PitStudio/"
license: Apache-2.0
version: "0.00.000"
```

A BibTeX entry has this shape (fill in the version and date of the release you used):

```bibtex
@software{pitstudio,
  author  = {Santibanez-Leal, Felipe A.},
  title   = {PitStudio: physical-AI simulation studio for open-pit mining},
  version = {X.YY.ZZZ},
  year    = {YYYY},
  url     = {https://github.com/fsantibanezleal/PitStudio},
  license = {Apache-2.0}
}
```

When you cite a **result**, cite the version and the run id shown on its artefact card. Also cite:

- **`minephys`** (its own `CITATION.cff`) when you use its models or parameter tables, and the primary source of each
  parameter row, which the tables carry with page numbers;
- **the datasets** behind the result, with the attribution their licence requires (CC BY 4.0 sources such as the
  Mendeley rock-fragment set, the de Wit slope-failure series or the McKinley lidar need attribution; the USGS 3DEP data
  are public domain) — see the [dataset cards](../data-contract/dataset-cards/README.md);
- **Cosmos outputs** with "Built on NVIDIA Cosmos" ([showcase rules](../web/showcase-rules.md)).

## Licences of what you cite

| Part | Licence |
|---|---|
| Code | Apache-2.0 |
| Docs, figures, PitStudio's own USD and synthetic data | CC-BY-4.0 |
| Layers derived from share-alike sources (MineLib, Maus polygons) | CC-BY-SA, kept in separate entries |
| Trained weights | Apache-2.0 with attribution when every input permits it; otherwise the most restrictive input terms, stated in the model card |
| NVIDIA software, assets, engines and caches | never redistributed; reference-only |

`REUSE.toml` maps every path to its licence; the full texts are in `LICENSES/`.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `invalid version '1.2.3': use X.YY.ZZZ` | `--version` given in normalised form | pass the padded form, e.g. `1.02.003` |
| `nothing to release` | no commits since the last `v*` tag | expected |
| The footer shows an old version after release | the site was built before `VERSION` changed, or `main` was not deployed | merge the release PR to `main`; Pages rebuilds from it |
| An asset release became "Latest" | published without `--latest=false` | edit it with `--latest=false`; mark the product release as latest |

## Assumptions and limits

- A version identifies code, docs and baked assets together; heavy assets are re-baked only at releases.
- Citing a version cites a simulation-grade, educational result with stated validity ranges, not a design.

## In PitStudio

- `tools/release.py` (exists), `CITATION.cff`, `CHANGELOG.md`, `VERSION`, `REUSE.toml`; release milestone
  `v0.01.000` with `minephys` on PyPI.

## References

1. "Semantic Versioning 2.0.0", item 2. https://semver.org/
2. Python Packaging Authority, PEP 440 "Version Identification and Dependency Specification" — integer normalisation of release segments. https://peps.python.org/pep-0440/
3. GitHub Docs, "About CITATION files" — "Cite this repository", APA and BibTeX. https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-citation-files
