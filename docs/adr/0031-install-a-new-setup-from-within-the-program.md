# 0031 – Install a new setup from within the program, after asking

- Status: accepted
- Date: 2026-10-18

## Context
A release whose app package needs a newer runtime needs its setup ([ADR 0022](0022-desktop-updates.md)).
Until 0.8.1 the program only showed a link: the browser downloaded the setup, the user ran it
from the Downloads folder, with Rhinvoice still running. On Windows the setup then stopped at
files the running program kept open ("DeleteFile failed; code 5"), first a Python module
(`.pyd`, which the Restart Manager of the setup did not look at), then a DLL of PostgreSQL,
whose server kept running after the program had been ended. On a Mac the user had to drag the
app into the Applications folder by hand. The in-app update of an app package restarts the
program without asking, so an unsaved form was lost.

## Decision
- **The program downloads the setup itself.** `release.json` gets `setup_files`: per setup the
  URL, size and SHA-256, like the app packages; `setups` (only the links) stays for the
  programs before this decision. The setup goes to `<data>/app/setup/<version>/`, in the
  background, and the page shows the progress (`GET /api/updates`, `setup`). A file whose size or SHA-256
  differs is deleted and never run. Setups of versions installed by now are removed at the
  start. Without `setup_files` (an older release) or on Linux the link stays.
- **Asked first, always.** Before the program closes or restarts for an update, a dialog says
  so and asks to save first; it names unsaved changes of any form on the page (the document
  editor, the settings and the forms with a save bar). **Later** keeps everything; the
  download goes on and the notice offers **Install** once it is ready. This also applies to
  the in-app update of an app package.
- **Then the program hands over and closes** (`POST /api/updates/setup/run`), without a
  restart by the boot:
  - **Windows:** it starts the setup with `/SILENT /SP- /NORESTART /FROMRHINVOICE`, detached.
    The program holds a named mutex while it runs (`RhinvoiceRunning`, Rhinvoice Beta
    `RhinvoiceBetaRunning`); started with `/FROMRHINVOICE` the setup waits up to two minutes
    for it to go, installs with its progress window and starts Rhinvoice again.
  - **macOS:** `/bin/sh` runs a script that waits for the boot's session lock
    (`<data>/app/session.lock`, `lockf`), mounts the disk image, copies the app next to the
    installed one and swaps them, then opens it. If anything fails (no permission, an app
    started from the Downloads folder) the old app stays and the disk image opens, to drag
    the app into the Applications folder by hand. The download carries no quarantine flag;
    the SHA-256 of the signed `release.json` stands in for Gatekeeper's check.
- **The Windows setup protects itself** when run by hand, before it removes any file
  (`[InstallDelete]` runs first and once removed `pg_ctl.exe` from under a running program):
  - it asks to close a Rhinvoice that holds the mutex ("Rhinvoice läuft noch …", OK / Cancel);
  - it asks the same when the edition's database runs (`pg_ctl status`), which also finds a
    Rhinvoice from before this decision, then stops a database still left running with
    `pg_ctl stop --mode=fast`, as the program would;
  - it reports `.pyd` files to the Restart Manager besides `.exe` and `.dll`.
- **The program survives missing database tools** when it closes: it reports the error
  instead of ending the thread with a traceback.

## Consequences
- A setup update is one click and one question, like an app package update; an
  installation of 0.8.1 or older still gets the link once, for the first release with
  `setup_files`.
- The mutex and the script live in the app package, not in the boot: no new runtime
  generation is needed ([ADR 0022](0022-desktop-updates.md), the boot's interface is unchanged).
- The script and the setup's `[Code]` are tested by hand on both systems before a release
  that needs a setup; the unit tests check the commands the program starts.
- The installer script is saved as UTF-8 with a byte order mark, for the umlauts of its
  messages.
