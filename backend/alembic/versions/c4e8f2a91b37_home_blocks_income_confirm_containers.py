"""home blocks, semimonthly income, primary/additional rules, schedule containers

Что делает миграция:
  * users.home_hidden_blocks: какие блоки главной страницы пользователь скрыл;
  * finance_recurring_rules: частота semimonthly («два раза в месяц») и второй день месяца;
    starts_cycle переименовано в is_primary (основной / дополнительный доход или платёж);
  * доходы больше не начисляются сами (auto_post=false) и не имеют даты окончания: правило дохода,
    которое уже закончилось, ставится на паузу, у остальных дата окончания очищается;
  * schedule_events.is_container: событие-блок, внутри которого могут быть другие события.

Откат (downgrade): частота semimonthly превращается в monthly по первому дню, остальное возвращается как было
(автоначисление доходов не восстанавливается: какие правила его имели, уже неизвестно).

Revision ID: c4e8f2a91b37
Revises: 7a1c3e5b9d20
Create Date: 2026-10-28 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'c4e8f2a91b37'
down_revision: Union[str, Sequence[str], None] = '7a1c3e5b9d20'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Правила, чья категория — доход
INCOME_RULES = (
    "category_id IN (SELECT id FROM finance_categories WHERE kind = 'income')"
)


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'users',
        sa.Column('home_hidden_blocks', postgresql.ARRAY(sa.String(length=20)), server_default=sa.text("'{}'"), nullable=False),
    )

    op.alter_column('finance_recurring_rules', 'starts_cycle', new_column_name='is_primary')
    op.alter_column('finance_recurring_rules', 'frequency', type_=sa.String(length=12), existing_nullable=False)
    op.add_column('finance_recurring_rules', sa.Column('second_day_of_month', sa.Integer(), nullable=True))
    op.drop_constraint('ck_finance_rules_frequency', 'finance_recurring_rules', type_='check')
    op.create_check_constraint(
        'ck_finance_rules_frequency',
        'finance_recurring_rules',
        "frequency IN ('weekly', 'biweekly', 'semimonthly', 'monthly', 'yearly')",
    )
    op.create_check_constraint(
        'ck_finance_rules_second_day',
        'finance_recurring_rules',
        'second_day_of_month IS NULL OR second_day_of_month BETWEEN 1 AND 31',
    )

    # Доходы: без автоначисления и без даты окончания. Закончившиеся — на паузу, чтобы не ожили
    op.execute(f"UPDATE finance_recurring_rules SET auto_post = false WHERE {INCOME_RULES}")
    op.execute(
        f"UPDATE finance_recurring_rules SET is_active = false "
        f"WHERE {INCOME_RULES} AND end_on IS NOT NULL AND end_on < CURRENT_DATE"
    )
    op.execute(f"UPDATE finance_recurring_rules SET end_on = NULL WHERE {INCOME_RULES}")
    # Раньше у платежей отметка «начинает цикл» всегда была false; теперь это «основной платёж»
    op.execute(f"UPDATE finance_recurring_rules SET is_primary = true WHERE NOT ({INCOME_RULES})")

    op.add_column(
        'schedule_events',
        sa.Column('is_container', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('schedule_events', 'is_container')

    op.execute(
        "UPDATE finance_recurring_rules SET frequency = 'monthly' WHERE frequency = 'semimonthly'"
    )
    op.drop_constraint('ck_finance_rules_second_day', 'finance_recurring_rules', type_='check')
    op.drop_constraint('ck_finance_rules_frequency', 'finance_recurring_rules', type_='check')
    op.create_check_constraint(
        'ck_finance_rules_frequency',
        'finance_recurring_rules',
        "frequency IN ('weekly', 'biweekly', 'monthly', 'yearly')",
    )
    op.drop_column('finance_recurring_rules', 'second_day_of_month')
    op.alter_column('finance_recurring_rules', 'frequency', type_=sa.String(length=10), existing_nullable=False)
    op.execute(f"UPDATE finance_recurring_rules SET is_primary = false WHERE NOT ({INCOME_RULES})")
    op.alter_column('finance_recurring_rules', 'is_primary', new_column_name='starts_cycle')

    op.drop_column('users', 'home_hidden_blocks')
