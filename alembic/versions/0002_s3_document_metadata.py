"""Add S3 object and processing metadata to documents.

Revision ID: 0002_s3_document_metadata
Revises: 0001_initial_schema
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_s3_document_metadata"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM documents
            WHERE status IS NOT NULL
              AND status NOT IN ('pending', 'processing', 'completed', 'failed')
          ) THEN
            RAISE EXCEPTION 'Legacy documents contain unsupported status values';
          END IF;
          IF EXISTS (
            SELECT 1
            FROM records r
            LEFT JOIN documents d ON d.id = r.document_id
            WHERE d.id IS NULL
          ) THEN
            RAISE EXCEPTION 'Legacy records contain orphaned document_id values';
          END IF;
        END $$;
        """
    )
    op.execute("UPDATE documents SET status = 'pending' WHERE status IS NULL")
    op.execute("UPDATE documents SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL")
    op.execute("UPDATE documents SET updated_at = CURRENT_TIMESTAMP WHERE updated_at IS NULL")
    op.execute("UPDATE records SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL")

    op.execute(
        "ALTER TABLE documents ALTER COLUMN created_at TYPE TIMESTAMP WITH TIME ZONE "
        "USING created_at AT TIME ZONE 'UTC'"
    )
    op.execute(
        "ALTER TABLE documents ALTER COLUMN updated_at TYPE TIMESTAMP WITH TIME ZONE "
        "USING updated_at AT TIME ZONE 'UTC'"
    )
    op.execute(
        "ALTER TABLE records ALTER COLUMN created_at TYPE TIMESTAMP WITH TIME ZONE "
        "USING created_at AT TIME ZONE 'UTC'"
    )
    op.alter_column("documents", "status", existing_type=sa.String(), nullable=False)
    op.alter_column(
        "documents",
        "created_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )
    op.alter_column(
        "documents",
        "updated_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )
    op.alter_column(
        "records",
        "created_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )

    op.create_check_constraint(
        "ck_documents_status",
        "documents",
        "status IN ('pending', 'processing', 'completed', 'failed')",
    )
    op.create_foreign_key(
        "fk_records_document_id_documents",
        "records",
        "documents",
        ["document_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_documents_created_at", "documents", ["created_at"])
    op.create_index("ix_documents_status", "documents", ["status"])
    op.create_index("ix_records_category", "records", ["category"])
    op.create_index("ix_records_created_at", "records", ["created_at"])
    op.create_index("ix_records_document_id", "records", ["document_id"])

    op.add_column("documents", sa.Column("object_key", sa.String(), nullable=True))
    op.add_column("documents", sa.Column("checksum_sha256", sa.String(64), nullable=True))
    op.add_column("documents", sa.Column("trace_id", sa.String(), nullable=True))
    op.add_column(
        "documents",
        sa.Column(
            "processing_attempts",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("documents", "processing_attempts")
    op.drop_column("documents", "trace_id")
    op.drop_column("documents", "checksum_sha256")
    op.drop_column("documents", "object_key")
    op.drop_index("ix_records_document_id", table_name="records")
    op.drop_index("ix_records_created_at", table_name="records")
    op.drop_index("ix_records_category", table_name="records")
    op.drop_index("ix_documents_status", table_name="documents")
    op.drop_index("ix_documents_created_at", table_name="documents")
    op.drop_constraint("fk_records_document_id_documents", "records", type_="foreignkey")
    op.drop_constraint("ck_documents_status", "documents", type_="check")
    op.alter_column(
        "records",
        "created_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=True,
    )
    op.alter_column(
        "documents",
        "updated_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=True,
    )
    op.alter_column(
        "documents",
        "created_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=True,
    )
    op.alter_column("documents", "status", existing_type=sa.String(), nullable=True)
    op.execute(
        "ALTER TABLE records ALTER COLUMN created_at TYPE TIMESTAMP WITHOUT TIME ZONE "
        "USING created_at AT TIME ZONE 'UTC'"
    )
    op.execute(
        "ALTER TABLE documents ALTER COLUMN updated_at TYPE TIMESTAMP WITHOUT TIME ZONE "
        "USING updated_at AT TIME ZONE 'UTC'"
    )
    op.execute(
        "ALTER TABLE documents ALTER COLUMN created_at TYPE TIMESTAMP WITHOUT TIME ZONE "
        "USING created_at AT TIME ZONE 'UTC'"
    )
