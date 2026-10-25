# 0036 – Signed programs for Windows and Mac

- Status: accepted
- Date: 2026-10-25

## Context
The macOS apps were signed ad hoc ([ADR 0021](0021-native-install-without-docker.md)): Apple
silicon runs no unsigned code, but Gatekeeper blocked the first start, and the docs led through
*System Settings → Privacy & Security → Open Anyway*. The maintainer now has an Apple Developer
ID certificate (team T3P59F52F4). Three things in Rhinvoice shape how it is used:
- The app packages of updates lie in the data folder, outside the bundle
  ([ADR 0022](0022-desktop-updates.md)), and their Python modules are not signed with the team's
  certificate. Notarization requires the hardened runtime, whose library validation refuses
  exactly such modules.
- The bundle holds Python, PostgreSQL, Chromium and restic: hundreds of programs and libraries,
  each of which must carry the Developer ID signature, a secure timestamp and the hardened
  runtime.
- `release.json` lists every file with its SHA-256 ([ADR 0033](0033-hardened-release-signing.md)),
  and the promotion releases the candidate's files unchanged. Signing must therefore happen
  before the candidate's `release.json` is written.

## Decision
- **A job of its own holds the certificate.** `macos-signing` in `desktop.yml` runs after the
  build, in the environment `desktop-signing`, which admits only `v*` tags (and, while the job is
  built, its branch). It builds nothing and uses no cache: it unpacks the apps the build job left,
  imports the certificate into a keychain of the run (deleted at the end), and runs only Apple's
  tools and `desktop/macos.py` (standard library, the system's Python). The secrets are
  `APPLE_CERTIFICATE` (the .p12, base64), `APPLE_CERTIFICATE_PASSWORD`,
  `APPLE_SIGNING_IDENTITY`, `APPLE_ID`, `APPLE_PASSWORD` (an app-specific password for
  notarytool) and `APPLE_TEAM_ID`, each in the environment of the step that needs it.
- **Inside out, with the hardened runtime.** `macos.py sign` finds every Mach-O file by its
  header, signs the libraries, then the programs, then nested bundles, then the app. Only the
  parts that need them get entitlements: the interpreters (`Contents/MacOS/<Name> Helper`,
  `Resources/python`) `disable-library-validation` (the update packages) and
  `allow-unsigned-executable-memory` (ctypes and cffi callbacks), Chromium `allow-jit` and
  `allow-unsigned-executable-memory`; PostgreSQL and restic run with library validation and none.
- **Notarized twice.** Each app is notarized and stapled, then packed into its disk image, which
  is signed, notarized and stapled too: the app carries its ticket after it was dragged out of the
  image, and the image passes Gatekeeper when it is opened offline.
- **Checked as a user gets it.** `macos-signed` installs both apps from the signed disk images
  into `/Applications`, requires Gatekeeper's verdict "Notarized Developer ID", and runs
  `desktop/smoke_test.py`, now also on a Mac, with the release's app package as the update: PDFs
  through Chromium, the backup with restic, an update and a broken one, a restore.
- **The interpreter carries the app's name.** The copy of Python in `Contents/MacOS` was called
  `python3`, so the Activity Monitor and firewalls such as Little Snitch named every request of
  Rhinvoice "python3". It is now `Rhinvoice Helper` (`Rhinvoice Beta Helper`); the start script
  `Contents/MacOS/Rhinvoice`, which the docs use on the command line, stays.
- **Pull requests stay unsigned.** Without a candidate's version (or the *sign* input of "Run
  workflow") the build job publishes its ad-hoc signed images as before.
- **The Windows setups through Azure Artifact Signing.** `windows-signing` runs in the same
  environment with `id-token: write` only: `azure/login` exchanges GitHub's token through the
  federated credential `repo:rhinvoice/rhinvoice:environment:desktop-signing` of the app
  registration `webberz-github-signing` (no client secret), and `azure/artifact-signing-action`
  signs both setups with the certificate profile `webberz` (account `webberzsigning`, Switzerland
  North), SHA-256 with Microsoft's timestamp. The values are environment variables, not secrets:
  `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `ARTIFACT_SIGNING_ENDPOINT`, `ARTIFACT_SIGNING_ACCOUNT`,
  `ARTIFACT_SIGNING_PROFILE`. `windows-signed` installs the signed setups, requires a valid
  Authenticode signature and runs the smoke test. The programs inside the setup
  (`Rhinvoice.exe`, PostgreSQL) stay as they come; the update packages are protected by
  `release.json`.

## Consequences
- macOS opens Rhinvoice and Rhinvoice Beta from the first start without a warning; the docs no
  longer lead through *Open Anyway*. Windows shows the publisher; SmartScreen may still ask
  while the certificate has little reputation.
- A candidate needs Apple's notary service: four submissions, a few minutes each. If it is down,
  the candidate's run fails and is started again.
- The hardened runtime with library validation switched off for the interpreter still protects
  against injected code at run time (no `DYLD_` variables, no debugger without the user's
  consent). The signed `release.json` protects an app package when it is downloaded; at a start
  the boot runs what lies in the data folder. A program of the same user that writes there, or
  runs the helper with `-c`, runs under the notarized identity. That was possible with the
  ad-hoc signature too; it is a limit of a Python app with updates outside the bundle.
- The signing job runs on GitHub's hosted runners only, which are discarded after each job; the
  decoded certificate is removed when its step ends, the keychain at the end of the job.
- The certificate expires in 2031; a renewed one changes only the secrets.
