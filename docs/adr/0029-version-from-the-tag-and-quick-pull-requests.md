# 0029 – The version comes from the tag, pull requests get the quick checks

- Status: accepted
- Date: 2026-10-17

## Context
Releasing 0.8.0 took three full CI runs of about 17 minutes each: the pull request with the
features, a second pull request that only changed the version number in nine files, and the
same checks again after each merge into `dev`. Each run repeated what the run before had
already shown. Most of the time went to the browser tests (about 15 minutes on one runner) and
to mutation testing every module (about 10 minutes), also for changes that touched neither.

## Decision
- **The version comes from the tag.** The release builds run `desktop/set_version.py` with the
  candidate's version before they build images and setups. The files keep the version of an
  earlier release in between; no commit only changes the number. A release needs the section
  `## [X.Y.Z]` in `CHANGELOG.md` (and its German twin), written in the pull request with the
  changes; the Release workflow refuses a candidate without it.
- **Install commands carry no version.** They load `compose.yml` and `.env.example` from `main`,
  which holds what was released ([ADR 0026](0026-dev-and-main.md)), as the homepage did already.
- **Pull requests get the quick run.** Mutation testing covers the domain and application
  modules the pull request changes, with the same threshold of 90 %. A pull request that only
  changes docs, the website or Markdown skips the checks; skipped checks count as passed and
  the Website workflow checks the docs. The same holds for changes to the workflows no pull
  request runs (release, promote, website, demo): the tests cannot try them, zizmor checks them. The Windows and macOS builds run for changes to what
  the programs consist of beyond the web application.
- **The candidate gets the full run.** The tag `vX.Y.Z-rc.N` starts CI with every mutant and
  every browser test. The Release workflow publishes the candidate only after that run passed,
  and its results on the released commit are the checks `main` asks for.
- **The browser tests always run completely**, split over four runners (`make e2e SHARD=2/4`).
- **No runs after a merge.** CI and the desktop builds no longer run on pushes to `dev` or
  `main`; the pull request was checked, the candidate is checked completely.
- **Promotion finishes the release.** Without a name *Promote release* takes the newest
  candidate. It brings the released commit to `main` itself through a pull request it merges at
  once, and starts the website. Without the repository setting "Allow GitHub Actions to create
  and approve pull requests" it links the pull request instead.
- A mutation run that stops before it checked every mutant is resumed once.

## Consequences
- A pull request waits about 8 minutes instead of 17, and a release needs one pull request.
- A defect that only every mutant or a module outside the pull request reveals shows up at the
  candidate at the latest, before anyone can install it; it then needs a fix and a new candidate.
- Between releases the program on `dev` names the last released version.
- The version examples in the docs ("e.g. 0.8.0") age; they are examples, not instructions.
- The workflow token may not create a tag or branch at a commit whose workflows differ from
  `dev`'s. When `dev` changed its workflows after the candidate, Promote stops before publishing
  anything and names the one `git push` the maintainer runs before starting it again.
