"""Remove database-backed document content after the S3 pipeline is ready.

Revision ID: 0003_remove_raw_csv
Revises: 0002_s3_document_metadata
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_remove_raw_csv"
down_revision: str | None = "0002_s3_document_metadata"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("documents", "raw_csv")


def downgrade() -> None:
    op.add_column("documents", sa.Column("raw_csv", sa.Text(), nullable=True))
