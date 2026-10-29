-- Диагностика (только чтение, ничего не меняет): доходы, которые сервер записал сам до версии 1.2.
--
-- До 1.2 доход по правилу мог начисляться автоматически (auto_post). Миграция 1.2 это выключила,
-- но уже созданные операции остались и входят в «Всего». В 1.2 доход появляется только после «Получено».
-- Запрос показывает доходы по правилам, записанные раньше даты обновления на 1.2 (release_at):
-- скорее всего, это и есть автоначисления. Решение, что с ними делать, за владельцем:
--   * удалить лишние операции в разделе «Финансы» → «Операции»;
--   * или просто ввести фактический остаток через «Изменить баланс» на главной.
--
-- Запуск на сервере (из папки проекта), дата — день обновления на 1.2:
--   docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env exec -T db \
--     psql -U nutrition -d nutrition -v release_at=2026-10-28 < deploy/diagnostics/auto-income-before-1.2.sql
--
-- Пример ответа:
--  книга | вид       | операция | дата       | сумма    | правило  | записана
--      1 | personal  |       17 | 2026-09-25 | 90000.00 | Зарплата | 2026-09-25 08:12:03+03

SELECT
    t.ledger_id                          AS "книга",
    CASE WHEN l.user_id IS NOT NULL THEN 'personal' ELSE 'household' END AS "вид",
    t.id                                 AS "операция",
    t.occurred_on                        AS "дата",
    t.amount                             AS "сумма",
    r.name                               AS "правило",
    t.created_at                         AS "записана"
FROM finance_transactions t
JOIN finance_categories c ON c.id = t.category_id AND c.kind = 'income'
JOIN finance_recurring_occurrences o ON o.transaction_id = t.id
JOIN finance_recurring_rules r ON r.id = o.rule_id
JOIN ledgers l ON l.id = t.ledger_id
WHERE t.created_at < :'release_at'::date
ORDER BY t.ledger_id, t.occurred_on;
