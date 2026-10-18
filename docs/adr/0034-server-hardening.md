# 0034 – Server hardening: request bodies, DNS rebinding, sign-in floods

- Status: accepted
- Date: 2026-10-18

## Context
An audit of 0.8.2 found gaps that an anonymous visitor could use, or a web page in the
browser of a desktop user:
- The size limit of a request (2 MB, imports 6 MB, a PDF to an imported invoice 21 MB, an
  invoice import 210 MB) only looked at `Content-Length`. A body sent in chunks declares
  none; FastAPI reads the body before it checks the login, so anyone could fill the memory.
- The installation without Docker ([ADR 0021](0021-native-install-without-docker.md)) listens
  on 127.0.0.1 and checked no `Host`. A page of another site whose name is made to point at
  127.0.0.1 (DNS rebinding) talks to it as its own origin; the cookie is not sent there, but
  the setup form and the login are open to it.
- Sign-ins were limited per account (a lock after five failures), per address only on the
  public demo ([ADR 0018](0018-public-demo.md)).
- The name of an attachment went into `Content-Disposition` as it came.
- The `.env.example` files carried a placeholder database password that Docker Compose
  accepted.
- The local Chromium that prints PDFs on the desktop ran scripts and loaded from the network;
  Gotenberg in the Docker setup does neither ([ADR 0007](0007-pdf-via-gotenberg.md)).

## Decision
- **Bodies are counted as they arrive.** `BodyLimitMiddleware` wraps `receive`, adds up the
  bytes and stops at the path's limit with the usual 413 `too_large`, whatever the app made
  of the broken body; an app that caught the refusal gets no more of the body. An answer
  the app had already started cannot become a 413: the error is raised again, and the
  server closes the connection. The `Content-Length` check stays, so a
  declared size is refused before anything is read.
- **Only uploads get the larger limits.** The import, invoice import and file limits apply
  to `multipart/form-data` only, whose files Starlette writes to temporary files; any other
  body on those paths (JSON, urlencoded, held in memory as a whole) gets 2 MB.
- **The desktop server answers only itself.** With `local_port` set (the launcher sets it,
  `RHINVOICE_LOCAL_PORT` would too) a request needs `Host` `127.0.0.1:<port>` or
  `localhost:<port>` (on port 80 also without the port, as browsers send it), else 421
  `host_rejected`. A change (not GET, HEAD, OPTIONS) with an
  `Origin` other than these two is refused with 403 `origin_rejected`; one without `Origin`
  (not from a browser) passes, as the custom header of
  [ADR 0003](0003-session-cookies-and-csrf.md) already covers browsers. With Docker nothing
  changes: the reverse proxy decides which names reach the server.
- **Sign-ins are limited per address in every installation**: `POST /api/auth/login`,
  `/api/auth/password` (it checks the current password) and `/api/auth/password-reset*`
  together 10 per minute per client (the `RateLimiter` of the demo), answered with 429
  `rate_limited`, which the OpenAPI schema documents and the interface translates. Only
  requests that passed the Host, Origin and custom header checks are counted: a form that
  any web page posts to the login (403 `csrf_rejected`) must not use up the sign-ins of
  everyone behind the same proxy address. The demo keeps its 60 changes per minute on top. The client is the address uvicorn
  reports: behind a proxy the visitor's own only when `RHINVOICE_FORWARDED_ALLOW_IPS` names
  the proxy, otherwise all visitors share the proxy's limit. The docs say so, name the
  Docker network's gateway for a proxy on the same machine and warn against `*` behind a
  proxy that appends to `X-Forwarded-For` (uvicorn then takes the visitor's own entry).
- **Attachment names lose control characters** (`\x00`–`\x1f`, `\x7f`) before they go into
  the header, in the ASCII fallback and in `filename*`; a backslash in the fallback becomes
  `_`. The domain already refuses them for new attachments; this guards the header. The
  document PDF uses the same helper.
- **No default database password.** `POSTGRES_PASSWORD=` is empty in both `.env.example`
  files, so the `:?` check of the compose files stops the start until one is set.
- **The local Chromium prints like Gotenberg**: `--blink-settings=scriptEnabled=false`, and
  every http(s) request goes to a proxy that is not there (`--proxy-server=127.0.0.1:9`,
  `--proxy-bypass-list=<-loopback>`, so 127.0.0.1 too). The DevTools protocol still
  evaluates `document.fonts.ready`; a test prints a page with a script, a stylesheet, an
  image and a frame from a local server and checks that nothing ran or arrived.
- **The docs advise** creating the first account before the server is reachable from the
  internet, and a body limit in the proxy (210 MB, the invoice import).

## Consequences
- A body costs at most 2 MB of memory, also for anonymous visitors; an upload at most its
  limit on disk, in temporary files. The upload limits are not tied to a login: FastAPI
  reads the form before it checks the session.
- A desktop user who opens Rhinvoice under another name (e.g. a name in `/etc/hosts`) gets a
  421; 127.0.0.1 and localhost are what the program itself opens.
- Behind a proxy that is not named in `RHINVOICE_FORWARDED_ALLOW_IPS`, a flood of wrong
  sign-ins blocks everyone's sign-in for a minute; the account locks stay as they were.
  IPv6 clients are counted per address, not per /64 network.
- The end-to-end tests run all projects from one address: only the test of the login signs
  in for real; the others around a sign-in reuse the session of the global setup.
- The local Chromium still reads `file://` URLs, as Gotenberg reads `/tmp`; the pages come
  from our templates with escaped content.
