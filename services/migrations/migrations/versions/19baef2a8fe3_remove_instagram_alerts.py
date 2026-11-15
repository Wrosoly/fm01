"""remove_instagram_alerts

Revision ID: 19baef2a8fe3
Revises: 5e7a1c9d2b40
Create Date: 2026-11-15 12:52:17.222393

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "19baef2a8fe3"
down_revision: str | Sequence[str] | None = "5e7a1c9d2b40"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
	"""Upgrade schema."""
	op.execute("DELETE FROM media_alerts WHERE platform = 'instagram'")


def downgrade() -> None:
	"""Downgrade schema."""
