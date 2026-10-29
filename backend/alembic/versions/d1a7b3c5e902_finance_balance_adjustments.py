"""finance balance adjustments

Что делает миграция:
  * новая таблица finance_balance_adjustments: корректировки баланса книги («на счетах на самом деле
    столько-то»). Они меняют только «Всего», в отчёты о доходах и расходах не входят.

Данные не меняются. Откат (downgrade) удаляет таблицу вместе со всеми корректировками.

Revision ID: d1a7b3c5e902
Revises: c4e8f2a91b37
Create Date: 2026-10-29 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd1a7b3c5e902'
down_revision: Union[str, Sequence[str], None] = 'c4e8f2a91b37'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'finance_balance_adjustments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('ledger_id', sa.Integer(), nullable=False),
        sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('adjusted_on', sa.Date(), nullable=False),
        sa.Column('note', sa.String(length=250), nullable=True),
        sa.Column('created_by_user_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('amount <> 0', name='ck_finance_balance_adjustments_amount_nonzero'),
        sa.ForeignKeyConstraint(['ledger_id'], ['ledgers.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_finance_balance_adjustments_ledger_date',
        'finance_balance_adjustments',
        ['ledger_id', 'adjusted_on'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_finance_balance_adjustments_ledger_date', table_name='finance_balance_adjustments')
    op.drop_table('finance_balance_adjustments')
