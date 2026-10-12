# 0003 – Server-side sessions, cookie auth and CSRF protection

- Status: accepted
- Date: 2026-10-09

## Context
The frontend is served by the same server as the API. Tokens in browser storage are vulnerable to XSS.

## Decision
- Login creates a random token (48 bytes, `secrets.token_urlsafe`). The database only holds its
  SHA-256 hash. Idle timeout 7 days, absolute timeout 30 days.
- Cookie `rhinvoice_session`: `HttpOnly`, `SameSite=Strict`, `Secure` (can be disabled only for local development
  via `RHINVOICE_COOKIE_SECURE=false`).
- CSRF: in addition to `SameSite=Strict`, every state-changing request to `/api/` requires the header
  `X-Rhinvoice-Client`. Browsers send custom headers cross-site only after a CORS preflight, which the API never
  allows (OWASP "Custom Request Headers").
- Passwords: argon2id, minimum length 12 (NIST SP 800-63B), lockout for 15 min. after 5 failed attempts,
  same response time for unknown users, transparent rehashing.
- Optional TOTP (RFC 6238, ±1 time step tolerance).
- Security headers (CSP without inline scripts, `frame-ancestors 'none'`, `nosniff`, Referrer-Policy).
- The first user is created via CLI (`rhinvoice user create`) or once via `/api/auth/setup`.
  The setup is protected against concurrent calls by a table lock.

## Consequences
No tokens in the JavaScript context. Third-party clients can use the API only with the header set,
which is intended.
