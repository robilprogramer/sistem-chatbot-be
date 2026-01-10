import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool
from dotenv import load_dotenv

from alembic import context

load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from informasional.utils.db import Base

# Import semua model yang INGIN di-manage oleh Alembic
# from informasional.models import *  # Import semua model sekaligus

# Import semua model yang INGIN di-manage oleh Alembic
from informasional.models.master_cabang import MasterCabangModel
from informasional.models.master_jenjang import MasterJenjangModel
from informasional.models.master_kategori import MasterKategoriModel
from informasional.models.document import Document, DocumentPage
from informasional.models.chunk import ChunkModel
from informasional.models.embedding import EmbeddingModel
# Import model transaksional (TAMBAH INI)
from informasional.models.registration import (
    StudentRegistration,
    RegistrationDocument,
    RegistrationTracking,
)
from informasional.models.conversation import (
    Conversation,
    ConversationState,
)
config = context.config

DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL:
    config.set_main_option("sqlalchemy.url", DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def include_object(object, name, type_, reflected, compare_to):
    """Exclude tables not managed by Alembic"""
    excluded_tables = {
        # NextAuth tables
        'User', 'Account', 'Session', 'VerificationToken',  # Legacy/existing tables yang tidak mau di-drop
        'document_chunks', 'document_embeddings',
    }
    
    if type_ == "table" and name in excluded_tables:
        return False
    return True


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

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