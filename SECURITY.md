# Security policy

Rhinvoice holds invoices, customer addresses and bank details. We take reports seriously and
thank everyone who reports responsibly.

## Supported versions

Security fixes go into the latest release. Before 1.0 only the newest minor version gets them;
update to it before reporting.

## Reporting a vulnerability

Please **do not open a public issue.** Report privately through GitHub:
**Security → Report a vulnerability** in this repository
([direct link](https://github.com/rhinvoice/rhinvoice/security/advisories/new)).

Please include:

- the affected version and how Rhinvoice runs (Docker image, behind which proxy),
- the steps to reproduce it and what an attacker gains,
- whether you want to be named in the advisory.

We confirm a report within seven days, keep you informed and agree on a date for the
publication with you. Rhinvoice is a small project without a bug bounty.

## Rules for testing

- Test on your own installation. The public demo is reset every hour and shared with other
  visitors: no denial of service, no spam, no automated scanning against it.
- Do not access, change or delete data of other people.

## Hardening your installation

See the security notes in [`docs/install.md`](docs/install.md): TLS through a reverse proxy,
`RHINVOICE_FORWARDED_ALLOW_IPS`, rate limiting in the proxy, two-factor authentication and
encrypted backups.
