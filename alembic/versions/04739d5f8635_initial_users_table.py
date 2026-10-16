"""initial users table

Revision ID: 04739d5f8635
Revises: 
Create Date: 2026-10-14 10:57:52.453644

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# Идентификаторы миграции
revision: str = '04739d5f8635'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Создать исходную таблицу пользователей."""

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("age", sa.Integer(), nullable=False),
        sa.Column("height_cm", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="users_pkey"),
    )


def downgrade() -> None:
    """Удалить таблицу пользователей."""

    op.drop_table("users")



