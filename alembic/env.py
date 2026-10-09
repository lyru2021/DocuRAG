import os
from dotenv import dotenv_values
from logging.config import fileConfig

from sqlalchemy import create_engine, pool
from alembic import context

from app.db.base import Base
from app.models.document import Document, Chunk

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline():
    raise RuntimeError("Offline migrations are not configured.")


def run_migrations_online():
    database_url = ( 
        os.environ.get("MIGRATION_DATABASE_URL")
        or dotenv_values(
            os.environ.get("ENV_FILE",".env")
        ).get("MIGRATION_DATABASE_URL")
    )

    if not database_url:
        raise RuntimeError("MIGRATION_DATABASE_URL is not required.")
    
    engine = create_engine(
        database_url,
        poolclass=pool.NullPool,
        echo=False,
    )
    try:
        with engine.connect() as connection:
            context.configure(
                connection=connection, target_metadata=target_metadata, compare_type=True
            )

            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
