"""Initial schema generated from the SQLAlchemy models."""

from alembic import op

from app.db.base import Base
from app.models import tables as _tables  # noqa: F401

revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(op.get_bind())
