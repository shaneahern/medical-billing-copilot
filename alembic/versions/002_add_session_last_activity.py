"""Add last_activity column to sessions table.

Revision ID: 002
Revises: 001
Create Date: 2026-02-04

Per Requirement 7.3: Session timeout after 30 minutes of inactivity.
"""

from alembic import op
import sqlalchemy as sa
from datetime import datetime, timezone


# revision identifiers, used by Alembic.
revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add last_activity column to sessions table."""
    op.add_column(
        "sessions",
        sa.Column(
            "last_activity",
            sa.DateTime(),
            nullable=True,
        ),
    )
    # Set default value for existing rows
    op.execute("UPDATE sessions SET last_activity = updated_at WHERE last_activity IS NULL")
    # Make column non-nullable after setting defaults
    op.alter_column("sessions", "last_activity", nullable=False)


def downgrade() -> None:
    """Remove last_activity column from sessions table."""
    op.drop_column("sessions", "last_activity")
