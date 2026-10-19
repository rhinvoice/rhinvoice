# 0035 – Rhinvoice Beta updates between candidates of one version

- Status: accepted
- Date: 2026-10-19

## Context
All candidates of a version carry its version number (ADR 0025, 0029): `v0.8.3-rc.2` and
`v0.8.3-rc.3` are both 0.8.3 inside the program. The update check compared version numbers
only, so Rhinvoice Beta on rc.2 was never offered rc.3; it had to be installed with its setup
(ADR 0030, consequences). Simply offering it would not have been enough. The boot knows an app
package by the version in its `manifest.json` and keeps update folders, database copies and
taken-back versions under that name (ADR 0022). With two packages of 0.8.3 it could not tell
which one is newer, which one runs or which one failed. The app packages are the same for both
editions, and *Promote release* releases the candidate's packages byte for byte (ADR 0033), so
the number cannot go into the version itself.

## Decision
- **The package names its candidate.** The release workflow builds the app packages with
  `desktop/build.py … --candidate N` (from the tag `vX.Y.Z-rc.N`, input `candidate` of the
  *Desktop* workflow). `manifest.json` then says `{"version": "0.8.4", "runtime": 1,
  "candidate": 3}`. Builds without a candidate (pull requests, earlier releases) have none.
  The released 0.8.4 consists of the files of the candidate it was promoted from, so it says the
  same.
- **`release.json` repeats it.** `desktop/release_manifest.py` writes `"candidate": N` from the
  packages, for the candidate and for the release promoted from it. It refuses packages that
  name different candidates, and a candidate's packages built as another candidate than its tag.
  The signature covers the field like any other. Programs before this decision ignore the
  unknown key. Programs from now on read it strictly: a positive whole number or absent.
- **A build is the version with its candidate.** The boot names a package `0.8.4-rc.3`
  (version, `-rc.`, candidate), or `0.8.4` without a candidate. It orders builds by version and
  then by candidate, with a version without a candidate after its candidates. `state.json`,
  the update folders and the database copies use that name, so `active`, `trying` and `failed`
  tell two candidates of one version apart. Pruning keeps the running build also in a folder
  named after its version only. A boot before this decision recorded the version only
  (`"0.8.4"`), also for a package built as a candidate. The new boot reads such an entry as
  naming every build of that version, so a package that boot took back stays out, the one that
  ran stays the one to go back to, and an unfinished trial is taken back with its copy.
  Before it starts a package, the boot sets the environment
  variable `RHINVOICE_BUILD` to its build.
- **Only Rhinvoice Beta, and only on a boot that knows builds.** The app package reads
  `RHINVOICE_BUILD`. It does not import anything new from the boot, because an update runs on the
  boot of an earlier setup (ADR 0030). If the variable is missing, the boot is older: the
  installer names update folders after the version, as before, because an older boot orders
  folders by names it can read. If the variable is there, the installer names each folder after
  the build. Rhinvoice Beta then knows its running candidate. Rhinvoice never sees candidates,
  so it compares versions only, as before.
- **Which release is newer.** A higher version always is. For the same version, a release is
  newer only if both candidates are known and the release's is higher. So:
  - Rhinvoice Beta on rc.2 is offered rc.3.
  - The release promoted from rc.3 is not offered to the Beta that runs rc.3, because those are
    the same files.
  - A Beta still on rc.2 is offered that release: it is rc.3's files.
  - A build without a candidate is never offered a candidate of its own version.

  Rhinvoice Beta shows its version and the offered one with the candidate (`0.8.4-rc.2`, new
  `0.8.4-rc.3`). A release that a boot took back counts as failed under its build or, for a boot
  before this decision, under its version.
- **The setup download is unchanged.** It stays keyed by the version. Two candidates of one
  version that both need a new runtime are not expected; the second is installed with its setup.

## Consequences
- Rhinvoice Beta updates from one candidate to the next within the program. If the new one
  does not start, it is taken back to the previous candidate with its database, as any update
  is.
- Each Rhinvoice Beta installation needs a setup of 0.8.4 or later once: only its boot sets
  `RHINVOICE_BUILD`. Until then it behaves as before, and is offered the next version's
  candidates only.
- Rhinvoice on a new boot keeps its packages under build names (`0.8.4-rc.3`). Nothing it shows
  or compares changes.
- *Promote release* needs nothing new. It reads the candidate from the packages it releases.
- The ADR 0030 consequence "rc.2 of the same version is installed with its setup over rc.1" no
  longer holds from 0.8.4 on.
