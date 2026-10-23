"""create platform_users and complaints tables

Revision ID: 20281dbb037a
Revises: 
Create Date: 2026-08-07 18:29:39.127348

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20281dbb037a'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('platform_users',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('hashed_password', sa.String(length=255), nullable=False),
    sa.Column('full_name', sa.String(length=255), nullable=False),
    sa.Column('agency_code', sa.String(length=10), nullable=False),
    sa.Column('role', sa.String(length=20), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_platform_users_agency_code'), 'platform_users', ['agency_code'], unique=False)
    op.create_index(op.f('ix_platform_users_email'), 'platform_users', ['email'], unique=True)

    op.create_table('complaints',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('unique_key', sa.String(length=50), nullable=False),
    sa.Column('agency', sa.String(length=10), nullable=False),
    sa.Column('complaint_type', sa.String(length=255), nullable=False),
    sa.Column('descriptor', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=50), nullable=False),
    sa.Column('borough', sa.String(length=20), nullable=False),
    sa.Column('incident_zip', sa.String(length=10), nullable=True),
    sa.Column('incident_address', sa.String(length=500), nullable=True),
    sa.Column('created_date', sa.DateTime(timezone=True), nullable=False),
    sa.Column('closed_date', sa.DateTime(timezone=True), nullable=True),
    sa.Column('resolution_description', sa.Text(), nullable=True),
    sa.Column('ingested_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_complaints_agency'), 'complaints', ['agency'], unique=False)
    op.create_index(op.f('ix_complaints_borough'), 'complaints', ['borough'], unique=False)
    op.create_index(op.f('ix_complaints_complaint_type'), 'complaints', ['complaint_type'], unique=False)
    op.create_index(op.f('ix_complaints_created_date'), 'complaints', ['created_date'], unique=False)
    op.create_index(op.f('ix_complaints_status'), 'complaints', ['status'], unique=False)
    op.create_index(op.f('ix_complaints_unique_key'), 'complaints', ['unique_key'], unique=True)
    op.create_index('ix_complaints_agency_borough_created', 'complaints', ['agency', 'borough', 'created_date'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_complaints_agency_borough_created', table_name='complaints')
    op.drop_index(op.f('ix_complaints_unique_key'), table_name='complaints')
    op.drop_index(op.f('ix_complaints_status'), table_name='complaints')
    op.drop_index(op.f('ix_complaints_created_date'), table_name='complaints')
    op.drop_index(op.f('ix_complaints_complaint_type'), table_name='complaints')
    op.drop_index(op.f('ix_complaints_borough'), table_name='complaints')
    op.drop_index(op.f('ix_complaints_agency'), table_name='complaints')
    op.drop_table('complaints')

    op.drop_index(op.f('ix_platform_users_email'), table_name='platform_users')
    op.drop_index(op.f('ix_platform_users_agency_code'), table_name='platform_users')
    op.drop_table('platform_users')
