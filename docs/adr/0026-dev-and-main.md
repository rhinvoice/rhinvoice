# 0026 – Work on dev, main holds what was released

- Status: accepted
- Date: 2026-10-16

## Context
With [ADR 0025](0025-tested-releases.md) every change came to `main` through a pull request and
a release candidate was tagged on `main`. But `main` is also what people see: rhinvoice.com is
built from it and the README on GitHub shows it. Merging 0.7.4 put its changelog and install
commands for `v0.7.4` on the website while 0.7.4 was still a candidate; the commands pointed at
a tag that did not exist yet.

## Decision
Two long-lived branches, both protected (pull requests only, CI green, no force pushes):

- **`dev`** is the default branch. Every pull request goes there, candidates `vX.Y.Z-rc.N`
  are tagged there (the Release workflow refuses a candidate that is not on `dev`).
- **`main`** holds what was released. *Promote release* pushes the branch `release/vX.Y.Z` at
  the released commit, not at `dev`'s newest one, and the maintainer merges its pull request
  into `main`. Only then are rhinvoice.com and the README rebuilt.

Self-hosted projects such as paperless-ngx and Home Assistant work the same way.

## Consequences
- What users read on GitHub and rhinvoice.com always matches the newest release.
- A release takes one more pull request.
- A fix to the website alone also goes through `dev` and waits for the next release. If it
  cannot wait, a pull request into `main` is fine; `main` is merged back into `dev` afterwards.
- Desktop preview builds run on pushes to `dev`, the website builds on pushes to `main`.
