"""scope hospital administrators

Revision ID: ccd17378d29e
Revises: df1e64bedff2
Create Date: 2026-07-03 14:26:38.696545
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'ccd17378d29e'
down_revision: Union[str, None] = 'df1e64bedff2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    with op.batch_alter_table('users') as batch_op:
        batch_op.add_column(sa.Column('hospital_id', sa.String(length=36), nullable=True))
        batch_op.create_index(op.f('ix_users_hospital_id'), ['hospital_id'], unique=False)
        batch_op.create_foreign_key('fk_users_hospital_id', 'hospitals', ['hospital_id'], ['id'])

def downgrade() -> None:
    with op.batch_alter_table('users') as batch_op:
        batch_op.drop_constraint('fk_users_hospital_id', type_='foreignkey')
        batch_op.drop_index(op.f('ix_users_hospital_id'))
        batch_op.drop_column('hospital_id')
