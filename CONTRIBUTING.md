# Contributing to Rhinvoice

Thank you for helping. Rhinvoice is a small project, so a short note before a large change saves
everybody time: open an issue first and describe what you want to do.

By taking part you agree to the [Code of Conduct](CODE_OF_CONDUCT.md).

## Ways to help

- **Report a bug** with the bug form. Never paste real customer, invoice or bank data; make up
  names and use the example IBANs from SIX or the EPC.
- **Report a tax or legal rule** that Rhinvoice gets wrong, with the official source (ESTV,
  Steuerverwaltung FL, BMF DE, BMF AT, a law text). Rhinvoice gives no tax advice, but its rules
  should match the law.
- **Add a country**: one country profile, guided by tests, see
  [docs/adding-a-country.md](docs/adding-a-country.md).
- **Suggest a feature.** Rhinvoice stays deliberately small; explain the problem, not only the
  solution.
- **Translate** or improve texts.
- **Send a pull request.**

Security issues go through a private report, never a public issue: see [SECURITY.md](SECURITY.md).

## Contributor License Agreement

Before we can merge your first pull request, you accept the
[Contributor License Agreement](CLA.md) by ticking its box in the pull request. You keep the
copyright of your work; the agreement lets the maintainer offer Rhinvoice under additional terms
later (for example as a hosted service) without asking every contributor again. Rhinvoice itself
stays under the GNU Affero General Public License.

## Development

Requirements: Python 3.13 with [uv](https://docs.astral.sh/uv/), Node.js 22 with pnpm, Docker.

```bash
make install        # dependencies
make dev-backend    # database on :5433 + API on :8000 (auto-reload)
make dev-frontend   # Vite on :5173, proxies /api to the backend
make demo           # demo customers, articles and documents
make qa             # the full quality gate (also what CI runs)
make help           # all targets
```

The architecture and its reasons are in [`docs/adr`](docs/adr), the design system in
[`docs/design/principles.md`](docs/design/principles.md). Read the ADR of the area you change.

## Rules for pull requests

- **`make qa` is green.** It is what CI runs; a pull request with a red gate is not reviewed.
- **Tests come with the change.** Backend and frontend logic keep 100 % line and branch coverage;
  the mutation score of `domain` and `application` stays at 90 % or more. New screens get a
  Playwright test with the axe check.
- **Layers hold.** `api → infrastructure → application → domain`; the domain imports no
  framework, the country packages do not know each other (import-linter and dependency-cruiser
  check this).
- **Money is never a float**, time comes from the `Clock`.
- **Issued documents stay immutable.** Nothing may change an issued invoice; corrections are
  cancellations.
- **Everything in code is English**: names, comments, commit messages. User-facing texts live in
  the message catalogues (`frontend/src/lib/i18n`) in German, English, French and Italian;
  new texts need all four (the type check and the tests insist).
- **Tax rules name their source** in a comment (law, article, official page).
- **Commit messages** follow [Conventional Commits](https://www.conventionalcommits.org/)
  (`feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`).
- **Add a line to `CHANGELOG.md`** under "Unreleased" when users notice the change.
- **Decisions** that others will ask about get an ADR in `docs/adr`.
- **UI changes** come with screenshots (light and dark, desktop and mobile) in the pull request.

## How a change is released

Nothing reaches users untested ([ADR 0025](docs/adr/0025-tested-releases.md), [ADR 0026](docs/adr/0026-dev-and-main.md),
[ADR 0029](docs/adr/0029-version-from-the-tag-and-quick-pull-requests.md)). Work happens on
`dev`; `main` only holds what was released.

1. **Pull request** into `dev`. CI runs the quick checks: mutation testing for the modules you
   changed, all browser tests split over four runners. A pull request that is the next release
   also adds the section `## [X.Y.Z]` to `CHANGELOG.md` and its German twin; the version number
   itself is never changed by hand.
2. **Release candidate.** The maintainer tags `vX.Y.Z-rc.N` on `dev`. CI runs everything (every
   mutant), the builds take the version from the tag, and once both passed a public
   pre-release appears: setups, Docker images tagged `X.Y.Z-rc.N`, nothing users get by
   themselves. You are welcome to test it. On Windows and macOS, install the candidate as
   **Rhinvoice Beta** (`Rhinvoice-Beta-Setup-Windows.exe`, `Rhinvoice-Beta-macOS.dmg`): a separate
   program with its own data, beside Rhinvoice, which it never touches; it is offered later
   candidates as updates ([ADR 0030](docs/adr/0030-rhinvoice-beta-for-release-candidates.md)).
3. **Promotion.** Once tested, the maintainer starts *Promote release*; the candidate's files
   (without Rhinvoice Beta's setups) become release `vX.Y.Z`, the released commit goes to `main`, and rhinvoice.com and the
   README follow.

## Licence

Rhinvoice is licensed under the [GNU Affero General Public License v3.0 or later](LICENSE).
