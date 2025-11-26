import os
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Optionally override URL from environment
database_url = os.getenv("DATABASE_URL")
if database_url:
    config.set_main_option("sqlalchemy.url", database_url)
else:
    # Fallback to default SQLite if no DATABASE_URL is set
    config.set_main_option("sqlalchemy.url", "sqlite:///./app/orolexa.db")

# add your model's MetaData object here for 'autogenerate' support
# from app.models import SQLModel
# For SQLModel, we use None here unless autogenerate is set up explicitly
target_metadata = None

def run_migrations_offline():
    # Get database URL from environment or config
    url = os.getenv("DATABASE_URL") or config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    # Get database URL from environment or config
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        database_url = config.get_main_option("sqlalchemy.url")
    
    # Create engine directly from URL to avoid config interpolation issues
    from sqlalchemy import create_engine
    connectable = create_engine(
        database_url,
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
