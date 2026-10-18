# 0030 – Rhinvoice Beta: release candidates as a separate installation

- Status: accepted
- Date: 2026-10-18

## Context
A release candidate's setups ([ADR 0025](0025-tested-releases.md)) installed the very same
program as the release: "Rhinvoice", macOS bundle id `com.webberz.rhinvoice`, the same Windows
AppId, program folder and data folder (`%LOCALAPPDATA%\Rhinvoice`,
`~/Library/Application Support/Rhinvoice`). Installed on a computer with Rhinvoice, a candidate
replaced the program and migrated its database. Going back to the released setup then failed:
the released program refuses a database with a newer schema. The update channel `test`
(`"update_channel": "test"` in `rhinvoice.json`) had the same effect through an update.

## Decision
- **Two editions, fixed when the setup is built.** `runtime.json` of the runtime says
  `"edition": "beta"` for **Rhinvoice Beta**; without it (all setups before) the runtime is
  Rhinvoice. Any other value counts as Rhinvoice. The app packages and `release.json` are the
  same for both editions; only the runtime differs.
- **Nothing is shared.** Rhinvoice Beta has its own name everywhere the system shows one and its
  own folders, named "Rhinvoice Beta" (Linux: `rhinvoice-beta`):
  - data (database, configuration with its own port and password, window state, logs on
    Windows, update packages and database copies): `%LOCALAPPDATA%\Rhinvoice Beta`,
    `~/Library/Application Support/Rhinvoice Beta`;
  - compiled Python files: `%LOCALAPPDATA%\Rhinvoice Beta\cache`,
    `~/Library/Caches/Rhinvoice Beta`; logs on macOS: `~/Library/Logs/Rhinvoice Beta`;
  - suggested backup folder: `Rhinvoice-Beta-Backup` in the cloud folder;
  - Windows: its own AppId `{33C691D7-C73A-4302-83F7-0BCA80193E27}`, program folder
    `%LOCALAPPDATA%\Programs\Rhinvoice Beta`, Start menu and desktop shortcuts and uninstall
    entry "Rhinvoice Beta"; the program file stays `Rhinvoice.exe`, its description says
    "Rhinvoice Beta";
  - macOS: `Rhinvoice Beta.app`, bundle id `ch.webberz.rhinvoice.beta` (the web view's storage
    and the system's preferences follow it), disk image volume "Rhinvoice Beta X.Y.Z";
  - its windows and start card are titled "Rhinvoice Beta". The icon is the same.
- **Bundle ids under webberz.ch.** The maker's domain is `webberz.ch`, so the ids are
  `ch.webberz.rhinvoice` and `ch.webberz.rhinvoice.beta`; the earlier `com.webberz.rhinvoice`
  was a mistake. An in-app update keeps the installed bundle; a Mac installs the new id only
  with a new setup. Its web view then starts with empty storage once: signing in again.
- **Who reads the edition.** The boot (`rhinvoice_boot.edition`) picks the data and cache
  folders and passes the data folder to the app package as before. The app package reads
  `runtime.json` itself (`rhinvoice.desktop.edition`), never through a new function of the boot:
  an update runs on the runtime of an earlier setup, whose boot has none (ADR 0022). It uses the
  edition for the log folder on macOS, the window titles, the backup folder suggestion, the
  update channel and the setup link.
- **Updates follow the edition.** Rhinvoice Beta checks the newest release including
  pre-releases (channel `test`); Rhinvoice only the latest release (channel `stable`). The
  desktop no longer reads `update_channel` from `rhinvoice.json`: Rhinvoice can never be offered
  a candidate. The Docker installation keeps `RHINVOICE_UPDATE_CHANNEL`.
- **Setups in release.json.** A candidate's `release.json` lists Rhinvoice Beta's setups under
  `<platform>-beta` (`windows-x64-beta`, `macos-arm64-beta`). An update that needs a new runtime
  leads Rhinvoice Beta to its own setup only, never to Rhinvoice's (which would install a
  candidate as Rhinvoice). Readers of earlier versions ignore the extra keys.
- **Building it costs little.** `desktop/build.py windows-beta` and `macos-beta` copy the
  assembled program, write the edition into `runtime.json`, rename it and, on macOS, sign it
  again; `rhinvoice.iss` takes `/DEdition=beta`. Every run of the *Desktop* workflow builds
  both editions: on Windows it installs Rhinvoice Beta beside Rhinvoice and runs the smoke test
  on it, which also checks that Rhinvoice's data stayed as it was; on macOS it starts both apps
  one after the other.
- **The candidate carries both, the release only Rhinvoice's.** The candidate's pre-release has
  `Rhinvoice-Setup-Windows.exe` and `Rhinvoice-macOS.dmg` (released unchanged by *Promote
  release*) and `Rhinvoice-Beta-Setup-Windows.exe` and `Rhinvoice-Beta-macOS.dmg` for testing.
  *Promote release* downloads Rhinvoice's setups and the app packages by name and fails if a
  file of Rhinvoice Beta would be released.

## Consequences
- A candidate can be tested on the computer with the real Rhinvoice; the two never share data,
  ports, logs or backups. Rhinvoice Beta starts with an empty database of its own.
- The setups that are released are still exactly the ones of the candidate, byte for byte, but
  the maintainer tests the candidate through Rhinvoice Beta, which differs from them only in
  its name, its identity and `runtime.json`. The update path of Rhinvoice itself is tested from
  the last release, as before.
- Candidates of one version carry the same version number (ADR 0025): Rhinvoice Beta updates
  itself to the next version's candidate, but `-rc.2` of the same version is installed with its
  setup over `-rc.1` (the data stays).
- A candidate's run of the *Desktop* workflow and every pull request that touches the programs
  take a few minutes longer (a second setup and disk image, the second smoke test on Windows).
- Test installations that relied on `"update_channel": "test"` in `rhinvoice.json` install
  Rhinvoice Beta instead.
