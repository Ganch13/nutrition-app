"use client";

import { useCallback, useState } from "react";
import { Button, Card, EmptyState, ErrorBanner, IconButton, Loading, Segmented, Spinner } from "@/components/ui";
import { getErrorText } from "@/lib/api";
import {
  deleteExpenseSummary,
  deleteFinanceTransaction,
  getCycles,
  getFinanceCategories,
  getFinanceGoals,
  getFinanceTransactions,
  getPeriodSummary,
} from "@/lib/endpoints";
import { capitalizeFirst, formatMoney, formatWeekdayDayMonth, shiftMonth, todayInZone } from "@/lib/format";
import { useProfile } from "@/lib/profile-context";
import type { FinanceTransaction, Ledger } from "@/lib/types";
import { useAsyncData } from "@/lib/use-async-data";
import { formatPeriod, Stat } from "./shared";
import SummaryForm from "./SummaryForm";
import TransactionForm from "./TransactionForm";

/** Месяцы, которые задевает период: ("2026-10-28", "2026-11-09") → ["2026-10", "2026-11"]. */
function monthsBetween(start: string, end: string): string[] {
  const months: string[] = [];
  let month = start.slice(0, 7);
  while (month <= end.slice(0, 7)) {
    months.push(month);
    month = shiftMonth(month, 1);
  }
  return months;
}

/**
 * Вкладка «Операции»: листать периоды назад, добавить операцию, посмотреть, изменить и удалить записи.
 * Расход можно отнести к цели: правка и удаление такого расхода сами правят цель.
 * Вместо отдельных покупок можно внести «Сводку за период» (SummaryForm) или сочетать оба способа.
 * Период — календарный месяц или промежуток между поступлениями дохода (по настройке книги).
 * Операции сервер отдаёт по месяцам, поэтому для периода, который пересекает границу месяцев,
 * запрашиваются оба месяца, а лишние даты отбрасываются здесь.
 */
export default function OperationsTab({ ledger }: { ledger: Ledger }) {
  const { profile } = useProfile();
  const today = todayInZone(profile.timezone);
  // 0 — текущий период, 1 — предыдущий, 2 — позапрошлый и так далее
  const [back, setBack] = useState(0);

  const load = useCallback(async () => {
    // Запрос previous=N&count=1 возвращает все периоды от N-го назад до текущего; нужный из них первый
    const report = await getCycles(ledger.id, back, 1);
    const period = report.cycles[0];
    // Цели книги — варианты поля «Цель» в форме расхода (загружаются каждый раз, поэтому новая цель видна сразу)
    const [summary, categories, goals, ...monthLists] = await Promise.all([
      getPeriodSummary(ledger.id, period.start),
      getFinanceCategories(ledger.id),
      getFinanceGoals(ledger.id),
      ...monthsBetween(period.start, period.end).map((month) => getFinanceTransactions(ledger.id, month)),
    ]);
    const transactions = monthLists
      .flat()
      .filter((item) => item.occurred_on >= period.start && item.occurred_on <= period.end)
      .sort((a, b) => (a.occurred_on === b.occurred_on ? b.id - a.id : a.occurred_on < b.occurred_on ? 1 : -1));
    return { period, summary, categories, goals, transactions };
  }, [ledger.id, ledger.cycle_mode, back]);
  const { data, error, loading, reload } = useAsyncData(load);

  const [actionError, setActionError] = useState<string | null>(null);
  const [confirmId, setConfirmId] = useState<number | null>(null);
  // Операция, открытая для правки (форма под строкой); null — ничего не правится
  const [editId, setEditId] = useState<number | null>(null);
  // Как вносить траты: отдельной покупкой или сводкой за период
  const [entryMode, setEntryMode] = useState<"single" | "summary">("single");

  /** Удаляет операцию и обновляет список. */
  async function handleDelete(transaction: FinanceTransaction, wholeSummary = false) {
    setActionError(null);
    try {
      if (wholeSummary && transaction.summary_id !== null) await deleteExpenseSummary(ledger.id, transaction.summary_id);
      else await deleteFinanceTransaction(ledger.id, transaction.id);
      setConfirmId(null);
      reload();
    } catch (err) {
      setActionError(getErrorText(err));
    }
  }

  if (error && data === null) return <ErrorBanner message={error} onRetry={reload} />;
  if (data === null) return <Loading />;

  const money = (value: string | number) => formatMoney(value, ledger.currency);
  // Операции по датам: [["2026-10-28", [операции...]], ...] в порядке от новых к старым
  const groups: [string, FinanceTransaction[]][] = [];
  for (const transaction of data.transactions) {
    const last = groups[groups.length - 1];
    if (last && last[0] === transaction.occurred_on) last[1].push(transaction);
    else groups.push([transaction.occurred_on, [transaction]]);
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-2">
        <IconButton icon="chevron-left" label="Предыдущий период" onClick={() => setBack(back + 1)} disabled={back >= 12} />
        <p className="min-w-44 text-center text-base font-semibold text-slate-900">{formatPeriod(data.period.start, data.period.end)}</p>
        <IconButton icon="chevron-right" label="Следующий период" onClick={() => setBack(Math.max(0, back - 1))} disabled={back === 0} />
        {back > 0 && (
          <Button size="sm" variant="secondary" onClick={() => setBack(0)}>
            К текущему
          </Button>
        )}
        {loading && (
          <span className="text-slate-400">
            <Spinner />
          </span>
        )}
      </div>

      {error && <ErrorBanner message={error} onRetry={reload} />}
      {actionError && <ErrorBanner message={actionError} />}

      <div className="grid grid-cols-3 gap-3">
        <Stat label="Доходы" value={money(data.summary.income)} tone="good" />
        <Stat label="Расходы" value={money(data.summary.expense)} />
        <Stat label="Итого" value={money(data.summary.balance)} tone={Number(data.summary.balance) < 0 ? "bad" : "default"} />
      </div>

      {back === 0 && (
        <div className="space-y-4">
          <Segmented
            label="Как внести траты"
            value={entryMode}
            onChange={(value) => setEntryMode(value as "single" | "summary")}
            options={[
              ["single", "Покупка"],
              ["summary", "Сводка за период"],
            ]}
          />
          {entryMode === "single" ? (
            <TransactionForm ledgerId={ledger.id} categories={data.categories} goals={data.goals} today={today} onDone={reload} />
          ) : (
            <SummaryForm
              ledgerId={ledger.id}
              currency={ledger.currency}
              categories={data.categories}
              goals={data.goals}
              today={today}
              onDone={reload}
            />
          )}
        </div>
      )}

      <Card title="Операции">
        {groups.length === 0 ? (
          <EmptyState title="В этом периоде операций нет">
            {back === 0 ? "Добавьте первую операцию выше." : "Вернитесь к текущему периоду, чтобы добавить операцию."}
          </EmptyState>
        ) : (
          <div className="space-y-5">
            {groups.map(([date, items]) => (
              <section key={date}>
                <h3 className="mb-1 text-sm font-medium text-slate-500">{capitalizeFirst(formatWeekdayDayMonth(date))}</h3>
                <ul className="divide-y divide-slate-100">
                  {items.map((transaction) => {
                    // Удалять можно свои операции; управляющий может удалять любые
                    const canDelete = ledger.can_manage || transaction.created_by_user_id === profile.id;
                    const income = transaction.kind === "income";
                    return (
                      <li key={transaction.id} className="py-3">
                        <div className="flex items-center justify-between gap-3">
                          <div className="min-w-0">
                            <p className="truncate font-medium text-slate-900">{transaction.category_name}</p>
                            {transaction.summary_start && transaction.summary_end && (
                              <p className="truncate text-xs font-medium text-slate-600">
                                Сводка {formatPeriod(transaction.summary_start, transaction.summary_end)}
                              </p>
                            )}
                            {transaction.goal_name && (
                              <p className="truncate text-xs font-medium text-brand-700">→ цель «{transaction.goal_name}»</p>
                            )}
                            {(transaction.description || ledger.kind === "household") && (
                              <p className="truncate text-xs text-slate-500">
                                {transaction.description}
                                {transaction.description && ledger.kind === "household" ? ", " : ""}
                                {ledger.kind === "household" ? transaction.created_by_name : ""}
                              </p>
                            )}
                          </div>
                          <div className="flex shrink-0 items-center gap-1">
                            <p className={`num font-semibold ${income ? "text-good-700" : "text-slate-900"}`}>
                              {income ? "+" : "−"}
                              {money(transaction.amount)}
                            </p>
                            {canDelete && (
                              <Button
                                size="sm"
                                variant="ghost"
                                aria-label={`Изменить операцию «${transaction.category_name}»`}
                                onClick={() => {
                                  setConfirmId(null);
                                  setEditId(editId === transaction.id ? null : transaction.id);
                                }}
                              >
                                Изменить
                              </Button>
                            )}
                            {canDelete && (
                              <IconButton
                                icon="trash"
                                tone="danger"
                                label={`Удалить операцию «${transaction.category_name}»`}
                                onClick={() => setConfirmId(confirmId === transaction.id ? null : transaction.id)}
                              />
                            )}
                          </div>
                        </div>
                        {editId === transaction.id && (
                          <TransactionForm
                            key={transaction.id}
                            ledgerId={ledger.id}
                            categories={data.categories}
                            goals={data.goals}
                            today={today}
                            transaction={transaction}
                            onDone={() => {
                              setEditId(null);
                              reload();
                            }}
                            onCancel={() => setEditId(null)}
                          />
                        )}
                        {confirmId === transaction.id && (
                          <div className="mt-2 flex flex-wrap items-center gap-3 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">
                            <span>
                              Удалить операцию? Если она создана из повторяющегося платежа, платёж отметится пропущенным.
                              {transaction.goal_name && ` Сумма уйдёт и из цели «${transaction.goal_name}».`}
                            </span>
                            <Button size="sm" variant="danger-solid" onClick={() => handleDelete(transaction)}>
                              {transaction.summary_id !== null ? "Удалить строку" : "Удалить"}
                            </Button>
                            {transaction.summary_id !== null && (
                              <Button size="sm" variant="danger" onClick={() => handleDelete(transaction, true)}>
                                Удалить всю сводку
                              </Button>
                            )}
                            <Button size="sm" variant="secondary" onClick={() => setConfirmId(null)}>
                              Отмена
                            </Button>
                          </div>
                        )}
                      </li>
                    );
                  })}
                </ul>
              </section>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
