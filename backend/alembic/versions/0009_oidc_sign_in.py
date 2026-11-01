"""Add provider identities, pending provider sign-ins, and optional passwords (Phase 10).

A user who signs in only through an OpenID Connect provider has no password, so
users.password_hash becomes optional. user_identities links a user to the provider's issuer
and subject, which are unique together. oidc_login_states holds each started sign-in until it
is finished or expires.

Revision ID: 0009_oidc_sign_in
Revises: 0008_answer_provider_llm_usage
Create Date: 2026-11-02
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009_oidc_sign_in"
down_revision: str | None = "0008_answer_provider_llm_usage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("users", "password_hash", existing_type=sa.String(length=255), nullable=True)
    op.create_table(
        "user_identities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("issuer", sa.String(length=512), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_identities_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_identities")),
        sa.UniqueConstraint("issuer", "subject", name=op.f("uq_user_identities_issuer")),
    )
    op.create_index(op.f("ix_user_identities_user_id"), "user_identities", ["user_id"])
    op.create_table(
        "oidc_login_states",
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=64), nullable=False),
        sa.Column("nonce", sa.String(length=64), nullable=False),
        sa.Column("code_verifier", sa.String(length=128), nullable=False),
        sa.Column("return_to", sa.String(length=512), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("token_hash", name=op.f("pk_oidc_login_states")),
    )
    op.create_index(op.f("ix_oidc_login_states_expires_at"), "oidc_login_states", ["expires_at"])


def downgrade() -> None:
    op.drop_table("oidc_login_states")
    op.drop_table("user_identities")
    # Users without a password can't be kept once the column is required again.
    op.execute("DELETE FROM users WHERE password_hash IS NULL")
    op.alter_column("users", "password_hash", existing_type=sa.String(length=255), nullable=False)
