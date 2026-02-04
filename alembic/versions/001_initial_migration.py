"""Initial migration - create users, sessions, messages, query_logs tables.

Revision ID: 001
Revises:
Create Date: 2026-02-04

Requirements: 7.1, 7.4
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create users table
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(255), unique=True, nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=True),
        sa.Column(
            "role",
            sa.Enum("USER", "ADMIN", name="userrole"),
            nullable=False,
            server_default="USER",
        ),
        sa.Column("failed_login_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # Create sessions table
    op.create_table(
        "sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])

    # Create messages table
    op.create_table(
        "messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("session_id", sa.String(36), sa.ForeignKey("sessions.id"), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("citations_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_messages_session_id", "messages", ["session_id"])

    # Create query_logs table
    op.create_table(
        "query_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("session_id", sa.String(36), sa.ForeignKey("sessions.id"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("query_type", sa.String(50), nullable=False),
        sa.Column("response_time_ms", sa.Integer(), nullable=False),
        sa.Column("data_source", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_query_logs_session_id", "query_logs", ["session_id"])
    op.create_index("ix_query_logs_user_id", "query_logs", ["user_id"])
    op.create_index("ix_query_logs_created_at", "query_logs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_query_logs_created_at", table_name="query_logs")
    op.drop_index("ix_query_logs_user_id", table_name="query_logs")
    op.drop_index("ix_query_logs_session_id", table_name="query_logs")
    op.drop_table("query_logs")

    op.drop_index("ix_messages_session_id", table_name="messages")
    op.drop_table("messages")

    op.drop_index("ix_sessions_user_id", table_name="sessions")
    op.drop_table("sessions")

    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")

    # Drop the enum type
    op.execute("DROP TYPE IF EXISTS userrole")
