# 0033 – Hardened release signing and pinned dependencies of the build

- Status: accepted
- Date: 2026-10-18

## Context
Every installation trusts a `release.json` signed with `RELEASE_SIGNING_KEY`
([ADR 0022](0022-desktop-updates.md)): whoever can sign can ship code to every desktop
installation. A security audit of the workflows found:
- the signing step ran `uv run --project backend`, which installed all 136 backend packages
  (the dev group too) into the process that held the key;
- the promotion ([ADR 0025](0025-tested-releases.md)) signed the files it downloaded from the
  candidate again without checking that they were the files the candidate had signed;
- all 61 actions were referenced by a movable tag, the base images by tag, `terser` without a
  version;
- `packages: write`, `pages: write` and `id-token: write` were granted to whole workflows,
  every checkout kept its token in `.git/config`, and a few `run:` blocks expanded `${{ }}`
  values directly into the shell;
- rhinvoice.com/docs had no Content-Security-Policy, unlike the landing page.

## Decision
- **The key meets nothing but `cryptography`.** `desktop/release_manifest.py` needs only the
  standard library and `cryptography`; `desktop/signing/` is a project of its own with exactly
  that dependency, locked with hashes in its `uv.lock`. The signing steps run
  `uv run --project desktop/signing --frozen`, the key is in the environment of that single
  step, and the jobs that hold it use no cache. The script carries the program's public key;
  a unit test checks that it equals the one in `rhinvoice.infrastructure.updates.feed` and that
  the program reads what the script writes.
- **The promotion checks before it signs.** It downloads the candidate's `release.json` and
  `release.json.sig` and runs `release_manifest.py --verify`: the signature must match the
  program's public key, the manifest must be for the version, and every file to be released
  must be listed under the candidate's tag with the same size and SHA-256. Any difference
  stops the promotion before the key is read. A candidate tagged before this decision has no
  `desktop/signing` and cannot be promoted; tag a new one.
- **Everything the build runs is pinned.** Actions by commit SHA with the version as a comment
  (Renovate: `helpers:pinGitHubActionDigests`), base images by the digest of their multi-arch
  index (`docker:pinDigests`), `terser` by its exact version, zizmor and gitleaks in the
  Makefile (a Renovate regex manager).
- **Least privilege per job.** Workflows grant `contents: read`; only the jobs that push images
  get `packages: write`, only the Pages deploy job `pages: write` and `id-token: write`. Every
  checkout sets `persist-credentials: false`, except the promotion's: its last step pushes the
  release branch with `git push`. Values from inputs, outputs and the matrix reach `run:` only
  through `env:`.
- **CI checks the workflows and the history.** The job "Workflows and secrets" runs
  `make security`: zizmor over `.github/workflows` (findings of medium and above fail; online
  checks with the job's token) and gitleaks over every commit. `.github/zizmor.yml` and
  `.gitleaks.toml` list only findings checked to be false positives, each with its reason.
  `make qa` includes the zizmor check (it needs no Docker); gitleaks runs in Docker and only in
  `make security` and CI.
- **The docs get a Content-Security-Policy** through Astro's `security.csp`: `default-src
  'self'`, scripts from the site and by hash, `'wasm-unsafe-eval'` for the search (Pagefind),
  styles with `'unsafe-inline'` (the code blocks colour tokens with style attributes), images
  also as `data:`. `make docs-qa` checks that every inline script of every page has its hash.

## Follow-up for the maintainer
The key is still a repository secret: a workflow run on any branch of the repository could read it. To bind it to
releases, in the repository settings:
1. **Environments → New environment** `release`; deployment branches and tags: **Selected**,
   the tag rule `v*`; **Required reviewers**: the maintainer.
2. Add `RELEASE_SIGNING_KEY` as a secret of that environment, then delete the repository
   secret.
3. Add `environment: release` to the jobs `github-release` (release.yml) and `promote`
   (promote.yml) in a pull request.

The workflows do not reference the environment yet: GitHub would create it on the first run
without protection and without the secret, and the release would fail.

## Consequences
- A compromised backend dependency, test tool or cache can no longer read the signing key; a
  swapped file between candidate and release is not signed.
- Updates of actions, images and the scanners come as Renovate pull requests with the new
  digest, reviewed like any other change.
- A new inline script on the docs that Astro does not hash fails `make docs-qa` and needs its
  hash in `astro.config.mjs`.
