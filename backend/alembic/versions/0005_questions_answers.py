"""Add questions, answers, and citations: questions asked in a workspace, kept for three days.

Revision ID: 0005_questions_answers
Revises: 0004_document_chunks
Create Date: 2026-10-29
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005_questions_answers"
down_revision: str | None = "0004_document_chunks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "questions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_questions_user_id_users"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_questions_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_questions")),
    )
    op.create_index(op.f("ix_questions_created_at"), "questions", ["created_at"])
    op.create_index(op.f("ix_questions_user_id"), "questions", ["user_id"])
    op.create_index(
        "ix_questions_workspace_id_user_id_created_at",
        "questions",
        ["workspace_id", "user_id", "created_at"],
    )
    op.create_table(
        "answers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("mode", sa.String(length=20), nullable=False),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("abstention_reason", sa.String(length=30), nullable=True),
        sa.Column("model_name", sa.String(length=200), nullable=True),
        sa.CheckConstraint("mode IN ('generated', 'search_only')", name=op.f("ck_answers_mode")),
        sa.CheckConstraint(
            "abstention_reason IN ('no_indexed_documents', 'weak_evidence', "
            "'insufficient_evidence', 'uncited_answer')",
            name=op.f("ck_answers_abstention_reason"),
        ),
        sa.CheckConstraint(
            "(text IS NOT NULL) = (mode = 'generated' AND abstention_reason IS NULL)",
            name=op.f("ck_answers_text_matches_outcome"),
        ),
        sa.CheckConstraint(
            "mode = 'search_only' OR model_name IS NOT NULL",
            name=op.f("ck_answers_generated_has_model"),
        ),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["questions.id"],
            name=op.f("fk_answers_question_id_questions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_answers")),
        sa.UniqueConstraint("question_id", name=op.f("uq_answers_question_id")),
    )
    op.create_table(
        "citations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("answer_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_id", sa.Uuid(), nullable=False),
        sa.Column("similarity", sa.Float(), nullable=False),
        sa.CheckConstraint("number >= 1", name=op.f("ck_citations_number_positive")),
        sa.ForeignKeyConstraint(
            ["answer_id"],
            ["answers.id"],
            name=op.f("fk_citations_answer_id_answers"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["chunk_id"],
            ["document_chunks.id"],
            name=op.f("fk_citations_chunk_id_document_chunks"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_citations_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_citations")),
        sa.UniqueConstraint("answer_id", "number", name=op.f("uq_citations_answer_id")),
    )
    op.create_index(op.f("ix_citations_chunk_id"), "citations", ["chunk_id"])
    op.create_index(op.f("ix_citations_document_id"), "citations", ["document_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_citations_document_id"), table_name="citations")
    op.drop_index(op.f("ix_citations_chunk_id"), table_name="citations")
    op.drop_table("citations")
    op.drop_table("answers")
    op.drop_index("ix_questions_workspace_id_user_id_created_at", table_name="questions")
    op.drop_index(op.f("ix_questions_user_id"), table_name="questions")
    op.drop_index(op.f("ix_questions_created_at"), table_name="questions")
    op.drop_table("questions")
