"""review fixes: revoked_tokens, Project.is_public, drop is_personal

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-07 00:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = '0002'
down_revision: str | Sequence[str] | None = '0001'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('revoked_tokens',
    sa.Column('jti', sa.String(), nullable=False),
    sa.Column('expires_at', sa.DateTime(), nullable=False),
    sa.Column('revoked_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('jti')
    )
    op.add_column('projects', sa.Column('is_public', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.drop_column('workspaces', 'is_personal')
    op.drop_column('teams', 'is_personal')


def downgrade() -> None:
    op.add_column('teams', sa.Column('is_personal', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('workspaces', sa.Column('is_personal', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.drop_column('projects', 'is_public')
    op.drop_table('revoked_tokens')
