"""goal entries from transactions

Что делает миграция:
  * finance_goal_entries.transaction_id: запись в цели, созданная расходом («Расход 5 000 → цель „Отпуск“»).
    Пусто у взносов, внесённых вручную. Уникально: одна операция — не больше одной записи.

Данные не меняются: все существующие записи остаются ручными. Откат (downgrade) удаляет колонку;
записи из расходов остаются в целях как обычные взносы.

Revision ID: e5b2c8d4f613
Revises: d1a7b3c5e902
Create Date: 2026-10-29 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5b2c8d4f613'
down_revision: Union[str, Sequence[str], None] = 'd1a7b3c5e902'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('finance_goal_entries', sa.Column('transaction_id', sa.Integer(), nullable=True))
    op.create_unique_constraint(
        'finance_goal_entries_transaction_id_key', 'finance_goal_entries', ['transaction_id']
    )
    op.create_foreign_key(
        'finance_goal_entries_transaction_id_fkey',
        'finance_goal_entries',
        'finance_transactions',
        ['transaction_id'],
        ['id'],
        ondelete='CASCADE',
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('finance_goal_entries_transaction_id_fkey', 'finance_goal_entries', type_='foreignkey')
    op.drop_constraint('finance_goal_entries_transaction_id_key', 'finance_goal_entries', type_='unique')
    op.drop_column('finance_goal_entries', 'transaction_id')
