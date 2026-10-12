# 0002 – SQLAlchemy Core with explicit mappers instead of ORM instrumentation

- Status: accepted
- Date: 2026-10-09

## Context
CLAUDE.md requires immutable domain objects (`@dataclass(frozen=True, slots=True)`) and an
"imperative mapping" in `infrastructure`. SQLAlchemy's imperative ORM mapping instruments the
mapped classes and sets attributes after construction. That does not work with `frozen=True` and `slots=True`.

## Decision
The schema is defined with SQLAlchemy Core (`infrastructure/db/tables.py`). Repositories translate
rows explicitly into domain objects and back (`_x_from_row`, `_x_values`). Alembic creates the migrations.
One test compares the migrated schema with the metadata (drift check), another one migrates fully
down and back up again.

## Consequences
- More code per repository, but fully typed, without magic and without lazy-loading surprises.
- Domain objects remain true value objects.
