"use client";

import { useState } from "react";
import { Badge, Button, ErrorBanner, TextField } from "@/components/ui";
import { getErrorText } from "@/lib/api";
import { confirmOccurrence, skipOccurrence, undoOccurrence } from "@/lib/endpoints";
import { daysBetween, formatDayMonth, formatMoney, plural } from "@/lib/format";
import type { Ledger, Occurrence } from "@/lib/types";

/** Когда платёж, словами относительно сегодня: «сегодня», «завтра», «через 5 дн.», «просрочен на 3 дн.». */
function dueLabel(today: string, dueOn: string): string {
  const diff = daysBetween(today, dueOn);
  if (diff === 0) return "сегодня";
  if (diff === 1) return "завтра";
  if (diff > 1) return `через ${diff} ${plural(diff, ["день", "дня", "дней"])}`;
  const late = -diff;
  return `просрочен на ${late} ${plural(late, ["день", "дня", "дней"])}`;
}

/**
 * Список ближайших и просроченных выплат с кнопками «Оплачено» / «Получено» и «Пропустить».
 * Отметка создаёт операцию в книге, а правило продолжает жить: следующее повторение придёт в свой срок.
 * Можно отметить другую сумму (например, коммуналка пришла дороже), отменить отметку или вернуть пропущенное.
 * today — сегодняшняя дата по серверу; onChanged — что вызвать после изменения (обновить данные страницы).
 */
export default function OccurrenceList({
  ledger,
  items,
  today,
  onChanged,
}: {
  ledger: Ledger;
  items: Occurrence[];
  today: string;
  onChanged: () => void;
}) {
  const [error, setError] = useState<string | null>(null);
  // Ключ выплаты, по которой идёт запрос или открыта форма «другая сумма»
  const [busy, setBusy] = useState<string | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [amount, setAmount] = useState("");
  const [date, setDate] = useState(today);

  const keyOf = (item: Occurrence) => `${item.rule_id}-${item.due_on}`;

  /** Выполняет действие над выплатой, обновляет данные и показывает ошибку, если она случилась. */
  async function run(item: Occurrence, action: () => Promise<unknown>) {
    setError(null);
    setBusy(keyOf(item));
    try {
      await action();
      setEditing(null);
      onChanged();
    } catch (err) {
      setError(getErrorText(err));
    } finally {
      setBusy(null);
    }
  }

  /** Открывает форму «другая сумма»: подставляет плановую сумму и сегодняшнюю дату. */
  function openEditor(item: Occurrence) {
    setEditing(keyOf(item));
    setAmount(String(Number(item.planned_amount)));
    setDate(today);
  }

  return (
    <div className="space-y-3">
      {error && <ErrorBanner message={error} />}
      <ul className="divide-y divide-slate-100">
        {items.map((item) => {
          const key = keyOf(item);
          const income = item.kind === "income";
          const isBusy = busy === key;
          return (
            <li key={key} className="py-3">
              <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
                <div className="flex min-w-0 items-center gap-3">
                  <span
                    className={`size-2.5 shrink-0 rounded-full ${income ? "bg-good-500" : item.overdue ? "bg-red-500" : "bg-brand-800"}`}
                    aria-hidden="true"
                  />
                  <div className="min-w-0">
                    <p className="truncate font-medium text-slate-900">{item.rule_name}</p>
                    <p className={`text-xs ${item.overdue && item.status === "pending" ? "font-medium text-red-600" : "text-slate-500"}`}>
                      {formatDayMonth(item.due_on)}
                      {item.status === "pending" && `, ${dueLabel(today, item.due_on)}`}
                    </p>
                  </div>
                </div>

                <div className="flex flex-wrap items-center justify-end gap-2">
                  <p className={`num font-semibold ${income ? "text-good-700" : "text-slate-900"}`}>
                    {income ? "+" : "−"}
                    {formatMoney(item.amount, ledger.currency)}
                  </p>

                  {item.status === "pending" && (
                    <>
                      <Button size="sm" loading={isBusy} onClick={() => run(item, () => confirmOccurrence(ledger.id, item.rule_id, item.due_on))}>
                        {income ? "Получено" : "Оплачено"}
                      </Button>
                      <Button size="sm" variant="ghost" disabled={isBusy} onClick={() => (editing === key ? setEditing(null) : openEditor(item))}>
                        Другая сумма
                      </Button>
                      <Button size="sm" variant="ghost" disabled={isBusy} onClick={() => run(item, () => skipOccurrence(ledger.id, item.rule_id, item.due_on))}>
                        Пропустить
                      </Button>
                    </>
                  )}
                  {item.status === "posted" && (
                    <>
                      <Badge tone="green">{income ? "Получено" : "Оплачено"}</Badge>
                      <Button size="sm" variant="ghost" loading={isBusy} onClick={() => run(item, () => undoOccurrence(ledger.id, item.rule_id, item.due_on))}>
                        Отменить
                      </Button>
                    </>
                  )}
                  {item.status === "skipped" && (
                    <>
                      <Badge>Пропущено</Badge>
                      <Button size="sm" variant="ghost" loading={isBusy} onClick={() => run(item, () => undoOccurrence(ledger.id, item.rule_id, item.due_on))}>
                        Вернуть
                      </Button>
                    </>
                  )}
                </div>
              </div>

              {editing === key && (
                <form
                  className="mt-3 grid gap-3 rounded-xl bg-slate-50 p-4 sm:grid-cols-[1fr_1fr_auto] sm:items-end"
                  onSubmit={(event) => {
                    event.preventDefault();
                    const value = Number(amount.replace(",", "."));
                    if (!Number.isFinite(value) || value <= 0) {
                      setError("Сумма должна быть больше нуля.");
                      return;
                    }
                    void run(item, () =>
                      confirmOccurrence(ledger.id, item.rule_id, item.due_on, { amount: value, occurred_on: date }),
                    );
                  }}
                >
                  <TextField
                    label={income ? "Сколько пришло" : "Сколько заплатили"}
                    type="number"
                    inputMode="decimal"
                    min={0.01}
                    step="0.01"
                    value={amount}
                    onChange={setAmount}
                    required
                  />
                  <TextField label="Дата" type="date" value={date} onChange={setDate} required />
                  <Button type="submit" loading={isBusy}>
                    Отметить
                  </Button>
                </form>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
