from alembic import context
from sqlalchemy import engine_from_config, pool

from rhinvoice.infrastructure.db.tables import metadata

config = context.config

connectable = config.attributes.get("connection")
if connectable is None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    ).connect()

with connectable as connection:
    context.configure(connection=connection, target_metadata=metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()
