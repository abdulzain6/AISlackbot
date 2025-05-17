from logging.config import fileConfig
import os
from sqlalchemy import create_engine
from sqlalchemy import pool

from alembic import context
from src.database.engine import Base
from dotenv import load_dotenv

load_dotenv()

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

DB_URL = os.getenv("DATABASE_URL")

EXCLUDED_TABLES = ["langchain_pg_collection", "langchain_pg_embedding"]

def include_object(object, name, type_, reflected, compare_to):
    if type_ == "table" and name in EXCLUDED_TABLES:
        return False
    return True

def run_migrations_offline() -> None:
    context.configure(
        url=DB_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    connectable = create_engine(DB_URL, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
