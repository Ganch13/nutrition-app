"""finance: recurring rules, budget cycles, goals, nullable transaction author

Что делает миграция:
  * finance_recurring_rules / finance_recurring_occurrences: повторяющиеся доходы и обязательные платежи;
  * ledgers.cycle_mode: календарный месяц или бюджетный цикл «от дохода до дохода»;
  * finance_goals / finance_goal_entries: накопления, долги и кредиты с процентами;
  * finance_transactions.created_by_user_id становится необязательным (SET NULL), чтобы при удалении
    аккаунта общие семейные операции оставались в книге.

Откат (downgrade): операции без автора удаляются, иначе вернуть NOT NULL нельзя.

Revision ID: 7a1c3e5b9d20
Revises: dd2eb071704c
Create Date: 2026-10-28 10:39:48.356864

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7a1c3e5b9d20'
down_revision: Union[str, Sequence[str], None] = 'dd2eb071704c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('finance_goals',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('ledger_id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.String(length=10), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('target_amount', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('start_amount', sa.Numeric(precision=12, scale=2), server_default=sa.text('0'), nullable=False),
    sa.Column('interest_rate', sa.Numeric(precision=6, scale=3), nullable=True),
    sa.Column('payment_day', sa.Integer(), nullable=True),
    sa.Column('created_by_user_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("kind <> 'loan' OR (interest_rate IS NOT NULL AND payment_day IS NOT NULL)", name='ck_finance_goals_loan_fields'),
    sa.CheckConstraint("kind IN ('savings', 'debt', 'loan')", name='ck_finance_goals_kind'),
    sa.CheckConstraint('interest_rate IS NULL OR (interest_rate >= 0 AND interest_rate <= 1000)', name='ck_finance_goals_rate'),
    sa.CheckConstraint('payment_day IS NULL OR payment_day BETWEEN 1 AND 31', name='ck_finance_goals_payment_day'),
    sa.CheckConstraint('start_amount >= 0', name='ck_finance_goals_start_non_negative'),
    sa.CheckConstraint('target_amount > 0', name='ck_finance_goals_target_positive'),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['ledger_id'], ['ledgers.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_finance_goals_ledger', 'finance_goals', ['ledger_id'], unique=False)
    op.create_table('finance_goal_entries',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('goal_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('paid_on', sa.Date(), nullable=False),
    sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('interest_part', sa.Numeric(precision=12, scale=2), nullable=True),
    sa.Column('principal_part', sa.Numeric(precision=12, scale=2), nullable=True),
    sa.Column('balance_after', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('note', sa.String(length=250), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('amount > 0', name='ck_finance_goal_entries_amount_positive'),
    sa.ForeignKeyConstraint(['goal_id'], ['finance_goals.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_finance_goal_entries_goal_date', 'finance_goal_entries', ['goal_id', 'paid_on'], unique=False)
    op.create_table('finance_recurring_rules',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('ledger_id', sa.Integer(), nullable=False),
    sa.Column('category_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('frequency', sa.String(length=10), nullable=False),
    sa.Column('start_on', sa.Date(), nullable=False),
    sa.Column('day_of_month', sa.Integer(), nullable=True),
    sa.Column('end_on', sa.Date(), nullable=True),
    sa.Column('auto_post', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('starts_cycle', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('created_by_user_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("frequency IN ('weekly', 'biweekly', 'monthly', 'yearly')", name='ck_finance_rules_frequency'),
    sa.CheckConstraint('amount > 0', name='ck_finance_rules_amount_positive'),
    sa.CheckConstraint('day_of_month IS NULL OR day_of_month BETWEEN 1 AND 31', name='ck_finance_rules_day_of_month'),
    sa.CheckConstraint('end_on IS NULL OR end_on >= start_on', name='ck_finance_rules_period'),
    sa.ForeignKeyConstraint(['category_id'], ['finance_categories.id'], ),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['ledger_id'], ['ledgers.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_finance_rules_ledger', 'finance_recurring_rules', ['ledger_id'], unique=False)
    op.create_table('finance_recurring_occurrences',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('rule_id', sa.Integer(), nullable=False),
    sa.Column('due_on', sa.Date(), nullable=False),
    sa.Column('status', sa.String(length=10), nullable=False),
    sa.Column('transaction_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status IN ('posted', 'skipped')", name='ck_finance_occurrences_status'),
    sa.ForeignKeyConstraint(['rule_id'], ['finance_recurring_rules.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['transaction_id'], ['finance_transactions.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('rule_id', 'due_on', name='uq_finance_occurrences_rule_due')
    )
    op.create_index(op.f('ix_finance_recurring_occurrences_transaction_id'), 'finance_recurring_occurrences', ['transaction_id'], unique=False)
    op.alter_column('finance_transactions', 'created_by_user_id',
               existing_type=sa.INTEGER(),
               nullable=True)
    op.drop_constraint('finance_transactions_created_by_user_id_fkey', 'finance_transactions', type_='foreignkey')
    op.create_foreign_key('finance_transactions_created_by_user_id_fkey', 'finance_transactions', 'users', ['created_by_user_id'], ['id'], ondelete='SET NULL')
    op.add_column('ledgers', sa.Column('cycle_mode', sa.String(length=10), server_default=sa.text("'calendar'"), nullable=False))
    op.create_check_constraint('ck_ledgers_cycle_mode', 'ledgers', "cycle_mode IN ('calendar', 'income')")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('ck_ledgers_cycle_mode', 'ledgers', type_='check')
    op.drop_column('ledgers', 'cycle_mode')
    # Операции удалённых авторов нельзя оставить: у старой схемы автор обязателен
    op.execute("DELETE FROM finance_transactions WHERE created_by_user_id IS NULL")
    op.drop_constraint('finance_transactions_created_by_user_id_fkey', 'finance_transactions', type_='foreignkey')
    op.create_foreign_key('finance_transactions_created_by_user_id_fkey', 'finance_transactions', 'users', ['created_by_user_id'], ['id'])
    op.alter_column('finance_transactions', 'created_by_user_id',
               existing_type=sa.INTEGER(),
               nullable=False)
    op.drop_index(op.f('ix_finance_recurring_occurrences_transaction_id'), table_name='finance_recurring_occurrences')
    op.drop_table('finance_recurring_occurrences')
    op.drop_index('ix_finance_rules_ledger', table_name='finance_recurring_rules')
    op.drop_table('finance_recurring_rules')
    op.drop_index('ix_finance_goal_entries_goal_date', table_name='finance_goal_entries')
    op.drop_table('finance_goal_entries')
    op.drop_index('ix_finance_goals_ledger', table_name='finance_goals')
    op.drop_table('finance_goals')
