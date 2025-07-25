"""Add wheel_speed and post_channels to raffles

Revision ID: add_wheel_speed_001
Revises: 
Create Date: 2024-01-01 00:00:00

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = 'add_wheel_speed_001'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    # Add wheel_speed column
    op.add_column('raffles', sa.Column('wheel_speed', sa.String(), nullable=True))
    op.execute("UPDATE raffles SET wheel_speed = 'fast' WHERE wheel_speed IS NULL")
    
    # Add post_channels column
    op.add_column('raffles', sa.Column('post_channels', sa.JSON(), nullable=True))
    op.execute("UPDATE raffles SET post_channels = '[]' WHERE post_channels IS NULL")

def downgrade():
    op.drop_column('raffles', 'wheel_speed')
    op.drop_column('raffles', 'post_channels')