"""Change telegram_id to BIGINT

Revision ID: change_telegram_id_001
Revises: add_wheel_speed_001
Create Date: 2024-01-26 00:00:00

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = 'change_telegram_id_001'
down_revision = 'add_wheel_speed_001'
branch_labels = None
depends_on = None

def upgrade():
    # Изменяем тип колонки telegram_id на BIGINT
    op.alter_column('users', 'telegram_id',
                    existing_type=sa.Integer(),
                    type_=sa.BigInteger(),
                    existing_nullable=True)
    
    op.alter_column('admins', 'telegram_id',
                    existing_type=sa.Integer(),
                    type_=sa.BigInteger(),
                    existing_nullable=True)

def downgrade():
    # Откат к Integer (может привести к потере данных!)
    op.alter_column('users', 'telegram_id',
                    existing_type=sa.BigInteger(),
                    type_=sa.Integer(),
                    existing_nullable=True)
    
    op.alter_column('admins', 'telegram_id',
                    existing_type=sa.BigInteger(),
                    type_=sa.Integer(),
                    existing_nullable=True)