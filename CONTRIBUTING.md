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
  the message catalogues (`frontend/src/lib/i18n`) in German and English.
- **Tax rules name their source** in a comment (law, article, official page).
- **Commit messages** follow [Conventional Commits](https://www.conventionalcommits.org/)
  (`feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`).
- **Add a line to `CHANGELOG.md`** under "Unreleased" when users notice the change.
- **Decisions** that others will ask about get an ADR in `docs/adr`.
- **UI changes** come with screenshots (light and dark, desktop and mobile) in the pull request.

## How a change is released

Nothing reaches users untested ([ADR 0025](docs/adr/0025-tested-releases.md)):

1. **Pull request** into `main`. CI must be green; changes to the program also build the
   Windows setup and the macOS disk image as a preview, attached to the run.
2. **Release candidate.** The maintainer tags `vX.Y.Z-rc.N`. That builds a public
   pre-release: setups, Docker images tagged `X.Y.Z-rc.N`, nothing users get by themselves.
   You are welcome to test it.
3. **Promotion.** Once tested, the maintainer starts *Promote release*; the candidate's files
   become release `vX.Y.Z`.

## Licence

Rhinvoice is licensed under the [GNU Affero General Public License v3.0 or later](LICENSE).
