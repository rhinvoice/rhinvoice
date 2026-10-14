# 0024 – A forgotten password

- Status: accepted
- Date: 2026-10-14

## Context
Rhinvoice had no way back from a forgotten password: not on a server, not on a desktop. The
usual way, a link by e-mail, needs a mail server that many installations do not have, and the
installation without Docker (ADR 0021) has no terminal for the person in front of it.

## Decision
Who may reset a password is who could read the data anyway:

- **On a server, the administrator.** `rhinvoice user list` shows the accounts' e-mail addresses,
  `rhinvoice user reset-password --email …` sets a new password (`docker compose exec app …`).
  The login page's *Forgot password?* names these commands.
- **On a desktop, the computer's user.** `Settings.reset_code_dir` (set by the desktop
  launcher to its private data folder) switches the login page to a one-time code: Rhinvoice
  writes it, with the accounts' addresses, into a file in that folder (mode 0600) and opens the
  file. The code is valid for 15 minutes and once; five wrong tries (a wrong code or an unknown
  address, which look alike) void it; it is kept in memory only, so a restart voids it too. The
  server listens on 127.0.0.1 only.
- A reset also ends every session of the account and a lock from failed logins; a second factor
  (TOTP) stays.
- The public demo offers neither.

A link by e-mail can come later, for installations with a mail server, as a third method.

## Consequences
- No new table and no mail dependency; the Docker setup is unchanged apart from two commands.
- Someone who can read the desktop user's files can take over the account. That person can
  already copy the database, so nothing is lost; the program says so in the docs.
