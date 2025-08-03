"""Add display_type to raffles

Revision ID: add_display_type_001
Revises: change_telegram_id_001
Create Date: 2024-01-27 00:00:00

"""
from alembic import op
import sqlalchemy as sa

revision = 'add_display_type_001'
down_revision = 'change_telegram_id_001'
branch_labels = None
depends_on = None

def upgrade():
    # Добавляем новое поле display_type
    op.add_column('raffles', sa.Column('display_type', sa.String(), server_default='wheel'))

def downgrade():
    op.drop_column('raffles', 'display_type')