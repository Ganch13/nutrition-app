"use client";

import { useState } from "react";
import { Badge, Button, Card, ErrorBanner, IconButton, Loading, ProgressBar, TextField } from "@/components/ui";
import { getErrorText } from "@/lib/api";
import {
  addFinanceGoalEntry,
  deleteFinanceGoal,
  deleteFinanceGoalEntry,
  getFinanceGoal,
  updateFinanceGoal,
} from "@/lib/endpoints";
import { formatDayMonth, formatMoney, formatShortDate, optionalText } from "@/lib/format";
import type { FinanceGoal, FinanceGoalDetail, FinanceGoalKind } from "@/lib/types";

const KIND_LABEL: Record<FinanceGoalKind, string> = { savings: "Накопление", debt: "Долг", loan: "Кредит" };
// Слова для кнопки и формы взноса
const ENTRY_WORD: Record<FinanceGoalKind, { button: string; field: string }> = {
  savings: { button: "Добавить взнос", field: "Сумма взноса" },
  debt: { button: "Добавить выплату", field: "Сумма выплаты" },
  loan: { button: "Добавить платёж", field: "Сумма платежа" },
};

// Цвета участников в общей полосе прогресса: у каждого человека свой, одинаковый в полосе и в легенде
const CONTRIBUTOR_COLORS = [
  { bar: "bg-brand-600", dot: "bg-brand-600 text-white" },
  { bar: "bg-saffron", dot: "bg-saffron text-slate-900" },
  { bar: "bg-good-500", dot: "bg-good-500 text-white" },
  { bar: "bg-red-500", dot: "bg-red-500 text-white" },
];

/** Круг с первой буквой имени. */
function Avatar({ name, className }: { name: string; className: string }) {
  return (
    <span className={`flex size-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${className}`} aria-hidden="true">
      {name.trim().charAt(0).toUpperCase() || "?"}
    </span>
  );
}

/**
 * Карточка финансовой цели: накопление, долг или кредит.
 *   * копилка и долг показывают, сколько осталось накопить или выплатить;
 *   * кредит показывает остаток основного долга и сколько из последнего платежа ушло банку на проценты;
 *   * у общей цели полоса прогресса делится на цвета участников: видно, кто сколько внёс.
 * Из карточки можно добавить взнос, открыть историю, изменить или удалить цель.
 * today — сегодняшняя дата; onChanged — обновить список целей после изменения.
 */
export default function GoalCard({
  goal,
  today,
  onChanged,
}: {
  goal: FinanceGoal;
  today: string;
  onChanged: () => void;
}) {
  const money = (value: string | number) => formatMoney(value, goal.currency);
  const words = ENTRY_WORD[goal.kind];

  // Что открыто под карточкой: форма взноса, история, редактирование, подтверждение удаления
  const [panel, setPanel] = useState<"entry" | "history" | "edit" | "delete" | null>(null);
  const [detail, setDetail] = useState<FinanceGoalDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  /** Открывает панель; для истории подгружает записи. */
  async function open(next: "entry" | "history" | "edit" | "delete") {
    setError(null);
    if (panel === next) {
      setPanel(null);
      return;
    }
    setPanel(next);
    if (next === "history") {
      setDetail(null);
      try {
        setDetail(await getFinanceGoal(goal.ledger_id, goal.id));
      } catch (err) {
        setError(getErrorText(err));
      }
    }
  }

  /** Выполняет действие, показывает ошибку и обновляет список целей. */
  async function run(action: () => Promise<void>) {
    setError(null);
    setBusy(true);
    try {
      await action();
      onChanged();
    } catch (err) {
      setError(getErrorText(err));
    } finally {
      setBusy(false);
    }
  }

  // Полоса прогресса: у общей цели делится по участникам
  const colorOf = (index: number) => CONTRIBUTOR_COLORS[index % CONTRIBUTOR_COLORS.length];
  const segments =
    goal.shared && goal.contributors.length > 0
      ? goal.contributors.map((contributor, index) => ({ share: contributor.share * goal.progress, className: colorOf(index).bar }))
      : undefined;

  // Главная фраза карточки (тексты заданы в описании продукта)
  const headline =
    goal.kind === "savings"
      ? `Осталось накопить: ${money(goal.remaining)}`
      : goal.kind === "debt"
        ? `Осталось выплатить: ${money(goal.remaining)}`
        : `Остаток основного долга: ${money(goal.remaining)}`;
  const subline =
    goal.kind === "savings"
      ? `Накоплено ${money(goal.paid_total)} из ${money(goal.target_amount)}`
      : goal.kind === "debt"
        ? `Выплачено ${money(goal.paid_total)} из ${money(goal.target_amount)}`
        : null;

  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="font-display text-xl font-semibold text-slate-900">{goal.name}</h3>
          <div className="mt-2 flex flex-wrap gap-1.5">
            <Badge>{KIND_LABEL[goal.kind]}</Badge>
            <Badge tone={goal.shared ? "amber" : "slate"}>{goal.shared ? "Общая" : "Личная"}</Badge>
            {goal.done && <Badge tone="green">{goal.kind === "savings" ? "Цель достигнута" : "Погашено"}</Badge>}
          </div>
        </div>
        <p className="figure num text-2xl text-slate-900">{Math.round(goal.progress * 100)} %</p>
      </div>

      <div className="mt-5">
        <p className="font-medium text-slate-900">{headline}</p>
        {subline && <p className="num mt-0.5 text-sm text-slate-500">{subline}</p>}
        {goal.kind === "loan" && (
          <div className="mt-1 space-y-0.5 text-sm text-slate-500">
            {goal.last_interest !== null && (
              <p className="num">Из последнего платежа на проценты банку ушло {money(goal.last_interest)}</p>
            )}
            {goal.interest_paid_total !== null && Number(goal.interest_paid_total) > 0 && (
              <p className="num">Всего процентов выплачено: {money(goal.interest_paid_total)}</p>
            )}
            {goal.next_payment_on && !goal.done && <p>Следующий платёж: {formatDayMonth(goal.next_payment_on)}</p>}
          </div>
        )}
      </div>

      <div className="mt-4">
        <ProgressBar
          label={`Прогресс цели «${goal.name}»`}
          value={goal.progress}
          segments={segments}
          tone={goal.done || goal.kind === "savings" ? "good" : "brand"}
        />
        {goal.shared && goal.contributors.length > 0 && (
          <ul className="mt-3 flex flex-wrap gap-x-5 gap-y-2">
            {goal.contributors.map((contributor, index) => (
              <li key={`${contributor.user_id}-${index}`} className="flex items-center gap-2 text-sm text-slate-600">
                <Avatar name={contributor.name} className={colorOf(index).dot} />
                <span>
                  {contributor.name}: <span className="num font-medium text-slate-900">{money(contributor.total)}</span>
                  <span className="num text-slate-500"> ({Math.round(contributor.share * 100)} %)</span>
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>

      {error && (
        <div className="mt-4">
          <ErrorBanner message={error} />
        </div>
      )}

      <div className="mt-5 flex flex-wrap items-center gap-2">
        {!goal.done && (
          <Button size="sm" onClick={() => open("entry")}>
            {words.button}
          </Button>
        )}
        <Button size="sm" variant="secondary" onClick={() => open("history")}>
          История
        </Button>
        {goal.can_edit && (
          <div className="ml-auto flex gap-1">
            <IconButton icon="pencil" label="Изменить цель" onClick={() => open("edit")} />
            <IconButton icon="trash" tone="danger" label="Удалить цель" onClick={() => open("delete")} />
          </div>
        )}
      </div>

      {panel === "entry" && (
        <EntryForm
          goal={goal}
          today={today}
          label={words.field}
          onSaved={(updated) => {
            setDetail(updated);
            setPanel(null);
            onChanged();
          }}
        />
      )}

      {panel === "history" && (
        <div className="mt-5 border-t border-slate-100 pt-4">
          {detail === null ? (
            !error && <Loading />
          ) : detail.entries.length === 0 ? (
            <p className="text-sm text-slate-500">Взносов пока нет.</p>
          ) : (
            <ul className="divide-y divide-slate-100">
              {detail.entries.map((entry) => (
                <li key={entry.id} className="flex items-start justify-between gap-3 py-3">
                  <div className="min-w-0 text-sm">
                    <p className="font-medium text-slate-900">
                      {formatShortDate(entry.paid_on)}
                      {goal.shared && <span className="font-normal text-slate-500">, {entry.user_name}</span>}
                    </p>
                    {entry.interest_part !== null && entry.principal_part !== null && (
                      <p className="num text-xs text-slate-500">
                        проценты банку {money(entry.interest_part)}, основной долг {money(entry.principal_part)}
                        {entry.balance_after !== null && `, остаток ${money(entry.balance_after)}`}
                      </p>
                    )}
                    {entry.note && <p className="text-xs text-slate-500">{entry.note}</p>}
                    {entry.transaction_id !== null && (
                      <p className="text-xs text-brand-700">из расхода — изменить или удалить можно в «Операциях»</p>
                    )}
                  </div>
                  <div className="flex shrink-0 items-center gap-1">
                    <p className="num font-semibold text-slate-900">{money(entry.amount)}</p>
                    {entry.can_delete && (
                      <IconButton
                        icon="trash"
                        tone="danger"
                        label="Удалить запись"
                        disabled={busy}
                        onClick={() =>
                          run(async () => {
                            setDetail(await deleteFinanceGoalEntry(goal.ledger_id, goal.id, entry.id));
                          })
                        }
                      />
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {panel === "edit" && (
        <EditForm
          goal={goal}
          onSaved={() => {
            setPanel(null);
            onChanged();
          }}
        />
      )}

      {panel === "delete" && (
        <div className="mt-5 flex flex-wrap items-center gap-3 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">
          <span>Удалить цель «{goal.name}» вместе с историей взносов?{goal.shared && " Её увидят и другие участники семьи."}</span>
          <Button
            size="sm"
            variant="danger-solid"
            loading={busy}
            onClick={() => run(() => deleteFinanceGoal(goal.ledger_id, goal.id))}
          >
            Удалить
          </Button>
          <Button size="sm" variant="secondary" onClick={() => setPanel(null)}>
            Отмена
          </Button>
        </div>
      )}
    </Card>
  );
}

/** Форма взноса или платежа: сумма, дата и необязательная заметка. */
function EntryForm({
  goal,
  today,
  label,
  onSaved,
}: {
  goal: FinanceGoal;
  today: string;
  label: string;
  onSaved: (detail: FinanceGoalDetail) => void;
}) {
  const [amount, setAmount] = useState("");
  const [date, setDate] = useState(today);
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /** Отправляет взнос: POST .../goals/{id}/entries. */
  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = Number(amount.replace(",", "."));
    if (!Number.isFinite(value) || value <= 0) {
      setError("Сумма должна быть больше нуля.");
      return;
    }
    setError(null);
    setSaving(true);
    try {
      onSaved(await addFinanceGoalEntry(goal.ledger_id, goal.id, { amount: value, paid_on: date, note: optionalText(note) }));
    } catch (err) {
      setError(getErrorText(err));
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="mt-5 space-y-4 rounded-xl bg-slate-50 p-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <TextField label={label} type="number" inputMode="decimal" min={0.01} step="0.01" value={amount} onChange={setAmount} required />
        <TextField label="Дата" type="date" value={date} onChange={setDate} required />
      </div>
      <TextField label="Заметка (необязательно)" value={note} onChange={setNote} maxLength={250} />
      {error && <ErrorBanner message={error} />}
      <Button type="submit" loading={saving}>
        Записать
      </Button>
    </form>
  );
}

/** Форма изменения цели: название, суммы, для кредита ещё ставка и день платежа. */
function EditForm({ goal, onSaved }: { goal: FinanceGoal; onSaved: () => void }) {
  const [name, setName] = useState(goal.name);
  const [target, setTarget] = useState(String(Number(goal.target_amount)));
  const [start, setStart] = useState(String(Number(goal.start_amount)));
  const [rate, setRate] = useState(goal.interest_rate === null ? "" : String(Number(goal.interest_rate)));
  const [day, setDay] = useState(goal.payment_day === null ? "" : String(goal.payment_day));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const targetLabel = goal.kind === "savings" ? "Сколько нужно накопить" : goal.kind === "debt" ? "Сумма долга" : "Основной долг на начало";

  /** Сохраняет изменения: PATCH .../goals/{id}. */
  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSaving(true);
    try {
      await updateFinanceGoal(goal.ledger_id, goal.id, {
        name: name.trim(),
        target_amount: Number(target.replace(",", ".")),
        ...(goal.kind !== "loan" ? { start_amount: Number(start.replace(",", ".")) } : {}),
        ...(goal.kind === "loan" ? { interest_rate: Number(rate.replace(",", ".")), payment_day: Number(day) } : {}),
      });
      onSaved();
    } catch (err) {
      setError(getErrorText(err));
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="mt-5 space-y-4 rounded-xl bg-slate-50 p-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <TextField label="Название" value={name} onChange={setName} required maxLength={100} />
        <TextField label={targetLabel} type="number" inputMode="decimal" min={0.01} step="0.01" value={target} onChange={setTarget} required />
        {goal.kind !== "loan" && (
          <TextField
            label={goal.kind === "savings" ? "Уже накоплено к началу" : "Уже выплачено к началу"}
            type="number"
            inputMode="decimal"
            min={0}
            step="0.01"
            value={start}
            onChange={setStart}
            required
          />
        )}
        {goal.kind === "loan" && (
          <>
            <TextField label="Ставка, % годовых" type="number" inputMode="decimal" min={0} max={1000} step="0.001" value={rate} onChange={setRate} required />
            <TextField label="День ежемесячного платежа" type="number" inputMode="numeric" min={1} max={31} value={day} onChange={setDay} required />
          </>
        )}
      </div>
      {error && <ErrorBanner message={error} />}
      <Button type="submit" loading={saving}>
        Сохранить
      </Button>
    </form>
  );
}
