# 0025 – Nothing reaches users untested

- Status: accepted
- Date: 2026-10-16

## Context
Until 0.7.3 a version tag built the Docker images and the setups and published them at once:
GitHub's "latest", the update check of every installation, rhinvoice.com and the demos all
followed within minutes. The setups for Windows and Mac were released before the maintainer
had installed them once. Changes went straight to `main`, without a pull request.

## Decision
A change passes three stages; only the last one reaches users.

1. **Pull request.** Every change, the maintainer's and the assistant's too, comes to `main`
   through a pull request. `main` is protected: the CI checks must be green, nobody pushes to
   it directly, and only the maintainer merges (contributions of others need the maintainer's approval). A
   pull request that touches the program builds the Windows setup and the macOS disk image as
   a preview (workflow *Desktop*).
2. **Release candidate.** A tag `vX.Y.Z-rc.N` on `main` runs *Release*: it checks that the
   program carries version X.Y.Z and that vX.Y.Z is not released, builds the images (each
   platform on a runner of its own kind) tagged `X.Y.Z-rc.N` only, builds the setups and app
   packages, and publishes them with a signed release.json as a public **pre-release**. GitHub
   never counts a pre-release as "latest": the update check (`releases/latest`), the download
   links on rhinvoice.com and the demos stay on the last release. The maintainer tests the
   candidate on Windows, macOS and Docker. Installations with `update_channel: test`
   (`RHINVOICE_UPDATE_CHANNEL=test`) are offered candidates as updates, to test the update
   path. A fix leads to the next candidate (`-rc.N+1`); a candidate is never changed.
3. **Promotion.** The maintainer starts *Promote release* with the tested candidate. It
   creates `vX.Y.Z` at the candidate's commit with **the candidate's files**: nothing is built
   again. Only release.json is written anew (its links lead to the release) and signed with
   the same key. The candidate's images get the tags `X.Y.Z`, `X.Y` and `latest`. Then
   rhinvoice.com is rebuilt and the demos are deployed.

The program inside a candidate already carries the final version X.Y.Z; `-rc.N` only names
the candidate. That is why its files can be released unchanged.

## Consequences
- Users only get what the maintainer installed and tried, byte for byte.
- A release takes one extra click and the time to test; a hurried fix goes through the same
  stages, only faster.
- Two candidates of one version carry the same version number: on a test machine the second
  is installed with its setup (over the first, the data stays); the update in the program is
  tested from the last release.
- To take a release back, it is marked as a pre-release again: the update check and the
  download links fall back to the release before. `latest` of the images is tagged back by
  hand (`docker buildx imagetools create`).
- The Release workflow can only be tried with a candidate tag; a failed candidate run
  publishes nothing and is repeated with the next `-rc.N`.
