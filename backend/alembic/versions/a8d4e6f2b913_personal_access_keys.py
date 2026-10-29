"""personal access keys and quick add requests

Что делает миграция (ТЗ 29.10.26(2), часть 2 — быстрое добавление расхода с iPhone):
  * таблица personal_access_keys: личные ключи доступа (в базе только SHA-256 ключа и его начало для узнавания);
  * таблица quick_add_requests: запомненные запросы с заголовком Idempotency-Key, чтобы повтор
    той же отправки не создал второй расход.

Данные не меняются. Откат (downgrade) удаляет обе таблицы: все ключи перестают работать,
быстрые команды на телефонах нужно будет настроить заново (сами расходы остаются).

Revision ID: a8d4e6f2b913
Revises: f7c3d9e1a824
Create Date: 2026-10-29 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a8d4e6f2b913'
down_revision: Union[str, Sequence[str], None] = 'f7c3d9e1a824'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'personal_access_keys',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('key_hash', sa.String(length=64), nullable=False),
        sa.Column('key_prefix', sa.String(length=10), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revoked_reason', sa.String(length=10), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('key_hash'),
    )
    op.create_index('ix_personal_access_keys_user', 'personal_access_keys', ['user_id'], unique=False)

    op.create_table(
        'quick_add_requests',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('access_key_id', sa.Integer(), nullable=False),
        sa.Column('idempotency_key', sa.String(length=100), nullable=False),
        sa.Column('transaction_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['access_key_id'], ['personal_access_keys.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['transaction_id'], ['finance_transactions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('access_key_id', 'idempotency_key', name='uq_quick_add_requests_key'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('quick_add_requests')
    op.drop_index('ix_personal_access_keys_user', table_name='personal_access_keys')
    op.drop_table('personal_access_keys')
