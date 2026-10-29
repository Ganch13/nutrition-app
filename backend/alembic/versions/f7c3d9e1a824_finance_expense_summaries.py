"""finance expense summaries

Что делает миграция:
  * новая таблица finance_expense_summaries: сводка расходов за период (день, неделя, месяц, свои даты);
  * finance_transactions.summary_id: операция-строка сводки. Пусто у обычных операций.

Данные не меняются. Откат (downgrade) удаляет колонку и таблицу; строки сводок остаются
в операциях как обычные расходы (без пометки «сводка»).

Revision ID: f7c3d9e1a824
Revises: e5b2c8d4f613
Create Date: 2026-10-29 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f7c3d9e1a824'
down_revision: Union[str, Sequence[str], None] = 'e5b2c8d4f613'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'finance_expense_summaries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('ledger_id', sa.Integer(), nullable=False),
        sa.Column('period_start', sa.Date(), nullable=False),
        sa.Column('period_end', sa.Date(), nullable=False),
        sa.Column('note', sa.String(length=250), nullable=True),
        sa.Column('created_by_user_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('period_start <= period_end', name='ck_finance_expense_summaries_period'),
        sa.ForeignKeyConstraint(['ledger_id'], ['ledgers.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_finance_expense_summaries_ledger_period',
        'finance_expense_summaries',
        ['ledger_id', 'period_start', 'period_end'],
        unique=False,
    )
    op.add_column('finance_transactions', sa.Column('summary_id', sa.Integer(), nullable=True))
    op.create_index(
        op.f('ix_finance_transactions_summary_id'), 'finance_transactions', ['summary_id'], unique=False
    )
    op.create_foreign_key(
        'finance_transactions_summary_id_fkey',
        'finance_transactions',
        'finance_expense_summaries',
        ['summary_id'],
        ['id'],
        ondelete='CASCADE',
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('finance_transactions_summary_id_fkey', 'finance_transactions', type_='foreignkey')
    op.drop_index(op.f('ix_finance_transactions_summary_id'), table_name='finance_transactions')
    op.drop_column('finance_transactions', 'summary_id')
    op.drop_index('ix_finance_expense_summaries_ledger_period', table_name='finance_expense_summaries')
    op.drop_table('finance_expense_summaries')
