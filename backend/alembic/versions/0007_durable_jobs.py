"""Durable indexing jobs with leases and attempts (Phase 8).

Revision ID: 0007_durable_jobs
Revises: 0006_chunk_search_vector
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007_durable_jobs"
down_revision: str | None = "0006_chunk_search_vector"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(50), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column(
            "run_after", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default="5", nullable=False),
        sa.Column("locked_by", sa.String(100)),
        sa.Column("locked_until", sa.DateTime(timezone=True)),
        sa.Column("dedupe_key", sa.String(100), nullable=False),
        sa.Column("last_error_code", sa.String(50)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("kind = 'index_document'", name="ck_jobs_kind"),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')",
            name="ck_jobs_status",
        ),
        sa.CheckConstraint(
            "attempts >= 0 AND max_attempts > 0 AND attempts <= max_attempts",
            name="ck_jobs_attempts",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_jobs"),
    )
    op.create_index("ix_jobs_due", "jobs", ["status", "run_after", "created_at"])
    op.create_index(
        "uq_jobs_dedupe_unfinished",
        "jobs",
        ["dedupe_key"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )
    op.execute("""
        UPDATE documents SET status = 'queued' WHERE status = 'processing';
        INSERT INTO jobs (
            id, kind, payload, status, run_after, attempts, max_attempts,
            dedupe_key, created_at, updated_at
        )
        SELECT gen_random_uuid(), 'index_document',
               json_build_object('document_id', id::text), 'queued', now(), 0, 5,
               'index_document:' || id::text, now(), now()
        FROM documents WHERE status = 'queued'
        ON CONFLICT (dedupe_key) WHERE status IN ('queued', 'running') DO NOTHING;
    """)


def downgrade() -> None:
    op.drop_index("uq_jobs_dedupe_unfinished", table_name="jobs")
    op.drop_index("ix_jobs_due", table_name="jobs")
    op.drop_table("jobs")
