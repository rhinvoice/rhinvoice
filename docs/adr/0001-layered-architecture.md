# 0001 – Layered architecture with enforced boundaries

- Status: accepted
- Date: 2026-10-09

## Context
Rhinvoice should stay maintainable in the long run and understandable for contributors. Tax and invoicing logic
must be testable without a database, web framework or network.

## Decision
Four layers in the backend: `domain` → `application` → `infrastructure` → `api` (dependencies point inwards only).

- `domain`: plain Python, immutable dataclasses, no framework imports.
- `application`: use cases as handler classes with command dataclasses; ports as `Protocol`.
  Every use case opens its own unit of work; whatever is not `commit()`ted is rolled back.
- `infrastructure`: adapters (PostgreSQL, argon2, TOTP, later Gotenberg, QR, e-invoice).
- `api`: FastAPI routers, Pydantic schemas, settings, CLI, composition root (`api/container.py`).

The boundaries are checked with **import-linter** (`pyproject.toml`, `[tool.importlinter]`) and are part of `make qa`.

## Consequences
- Application tests run against in-memory fakes (`tests/unit/application/fakes.py`). A conformance test
  ensures that the fakes implement all port methods.
- Pydantic only appears in `api`; settings therefore live in `api` as well.
