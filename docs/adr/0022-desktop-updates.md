# 0022 – Updates of the installation without Docker

- Status: proposed
- Date: 2026-10-14

## Context
The installation without Docker (ADR 0021) is a setup that bundles everything. If every release
needed a new setup, offices without IT would download and run installers several times a month,
or stop updating. Docker users run `docker compose pull`; the desktop needs the same: one click in
the program. A new setup must only be needed when the foundation changes.

## Decision
**Two parts with their own life cycle.**

| | Runtime (setup) | App package (update in the program) |
|---|---|---|
| Content | CPython, PostgreSQL, `rhinvoice_boot`, icons | Rhinvoice with all Python libraries (`site-packages/`), the web interface (`static/`), `manifest.json` |
| Changes | new Python or PostgreSQL major version, a fix for a new Windows or macOS | every release |
| Comes | as `Rhinvoice-Setup-x.y.z.exe` / `.dmg` | as `rhinvoice-app-x.y.z-<platform>.zip` on the GitHub release |

- **`rhinvoice_boot`** (in the runtime, kept small and stable) picks the app package to run: the
  active one from the data folder (`<data>/app/versions/x.y.z`), else the one the setup brought
  (`<install>/app`). It only takes a package whose `manifest.json` names a runtime generation that
  the installed runtime provides (`runtime.json`). Packages live in the data folder, not in the
  program folder: a signed macOS app must not change, and on Windows the user owns it either way.
- **Update check:** the program reads `desktop-manifest.json` from the latest GitHub release at its
  start and once a day. It lists version, required runtime generation, and per platform the URL,
  size and SHA-256 of the package. The manifest is **signed (Ed25519)**; the public key is part of
  the program, the private key is a secret of the release workflow. A manifest whose signature does
  not verify is ignored; a package whose SHA-256 differs is deleted.
- **Applying** (one click in the program): download and check the package, unpack it next to the
  others (`x.y.z.partial`, renamed when complete), mark it as pending and restart. Before the first
  start of a pending version, the boot **copies the stopped database folder** to
  `<data>/backups/` (an exact copy, no dump and restore). The migrations run at the start as today.
- **Rollback:** the new version confirms itself once its web interface answers. A pending version
  that ends before that is marked as failed; the boot puts the copied database folder back (the
  failed one is kept aside for analysis) and starts the previous version, which then says that the
  update did not work.
- **Runtime too old:** a package that needs a newer runtime is not offered as update; the program
  shows "this version needs a new setup" with the download link instead.
- **Docker is unchanged.** The update endpoints exist only in the desktop layer.
- **The last three versions are kept** (for rollback), older ones are removed after a confirmed
  start. Database copies older than the last three updates are removed as well.

## Consequences
- The release workflow builds one app package per platform, writes and signs the manifest and
  attaches both to the release; the private key is stored as a GitHub secret.
- The setup ships the app package of its release, so a fresh installation works without internet.
- A new runtime generation (e.g. PostgreSQL 18) needs a setup that also upgrades the database
  (`pg_upgrade` or dump and restore); that is decided with the first such change.
