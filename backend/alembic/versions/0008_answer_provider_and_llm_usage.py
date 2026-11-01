"""Add answers.model_provider and llm_usage: which provider wrote an answer, and the calls made
to a hosted provider each day (Phase 9).

Revision ID: 0008_answer_provider_llm_usage
Revises: 0007_durable_jobs
Create Date: 2026-11-01
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008_answer_provider_llm_usage"
down_revision: str | None = "0007_durable_jobs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("answers", sa.Column("model_provider", sa.String(length=30), nullable=True))
    # Until now, Ollama was the only provider, so every answer that names a model used it.
    op.execute("UPDATE answers SET model_provider = 'ollama' WHERE model_name IS NOT NULL")
    op.create_table(
        "llm_usage",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("calls", sa.Integer(), server_default="0", nullable=False),
        sa.Column("prompt_tokens", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("completion_tokens", sa.BigInteger(), server_default="0", nullable=False),
        sa.CheckConstraint("calls >= 0", name=op.f("ck_llm_usage_calls_non_negative")),
        sa.PrimaryKeyConstraint("day", name=op.f("pk_llm_usage")),
    )


def downgrade() -> None:
    op.drop_table("llm_usage")
    op.drop_column("answers", "model_provider")
