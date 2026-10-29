"use client";

import { useCallback, useState } from "react";
import { Button, Card, ErrorBanner, IconButton, Segmented, SelectField, TextField } from "@/components/ui";
import { getErrorText } from "@/lib/api";
import { checkExpenseSummary, createExpenseSummary } from "@/lib/endpoints";
import { formatMoney, mondayOf, optionalText, shiftDate, shiftMonth } from "@/lib/format";
import type { ExpenseSummaryCheck, ExpenseSummaryCheckInput, FinanceCategory, FinanceGoal } from "@/lib/types";
import { formatPeriod } from "./shared";
import SummaryReconcileDialog from "./SummaryReconcileDialog";

/** За какой период сводка: день, неделя (пн–вс), месяц или свои даты. */
type PeriodKind = "day" | "week" | "month" | "custom";

/** Строка формы. key нужен React для списка; значения полей хранятся строками, как их ввёл человек. */
type Line = { key: number; categoryId: string; amount: string; goalId: string };

/**
 * Период по выбору. Неделя и месяц не заходят в будущее: заканчиваются сегодня, если ещё не прошли.
 * Примеры при today = "2026-10-28":
 *   ("day",   "2026-10-25") → ["2026-10-25", "2026-10-25"]
 *   ("week",  "2026-10-22") → ["2026-10-19", "2026-10-25"]
 *   ("month", "2026-10-10") → ["2026-10-01", "2026-10-28"]
 */
function periodOf(kind: PeriodKind, anchor: string, customStart: string, customEnd: string, today: string): [string, string] {
  if (kind === "custom") return [customStart, customEnd];
  if (kind === "day") return [anchor, anchor];
  const cap = (end: string) => (end > today ? today : end);
  if (kind === "week") {
    const start = mondayOf(anchor);
    return [start, cap(shiftDate(start, 6))];
  }
  const month = anchor.slice(0, 7);
  return [`${month}-01`, cap(shiftDate(`${shiftMonth(month, 1)}-01`, -1))];
}

/**
 * Форма «Сводка за период»: вместо отдельных покупок — итог за день, неделю, месяц или свои даты,
 * несколько строк «категория — сумма» за один раз. Строке можно указать цель, как обычному расходу.
 *
 * Порядок: «Сохранить» → сверка на сервере. Если за период уже есть расходы тех же категорий, открывается окно
 * «Это дополнение или повтор?» (SummaryReconcileDialog) — решение за человеком. Иначе сводка сохраняется сразу.
 * Пример запроса: { period_start: "2026-10-19", period_end: "2026-10-25",
 *                   lines: [{ category_id: 3, amount: 8000 }, { category_id: 5, amount: 1200 }], note: "Чеки" }
 * onDone — обновить страницу после сохранения.
 */
export default function SummaryForm({
  ledgerId,
  currency,
  categories,
  goals,
  today,
  onDone,
}: {
  ledgerId: number;
  currency: string;
  categories: FinanceCategory[];
  goals: FinanceGoal[];
  today: string;
  onDone: () => void;
}) {
  const expenseOptions = categories
    .filter((category) => category.kind === "expense")
    .map((category): [string, string] => [String(category.id), category.name]);
  const firstCategory = expenseOptions[0]?.[0] ?? "";
  const goalChoices: [string, string][] = [
    ["", "Без цели"],
    ...goals.filter((goal) => goal.kind === "savings" || !goal.done).map((goal): [string, string] => [String(goal.id), goal.name]),
  ];

  const [kind, setKind] = useState<PeriodKind>("week");
  const [anchor, setAnchor] = useState(today);
  const [customStart, setCustomStart] = useState(shiftDate(today, -6));
  const [customEnd, setCustomEnd] = useState(today);
  const [lines, setLines] = useState<Line[]>([{ key: 1, categoryId: firstCategory, amount: "", goalId: "" }]);
  const [nextKey, setNextKey] = useState(2);
  const [note, setNote] = useState("");
  const [check, setCheck] = useState<ExpenseSummaryCheck | null>(null);
  const [payload, setPayload] = useState<ExpenseSummaryCheckInput | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);

  const [start, end] = periodOf(kind, anchor, customStart, customEnd, today);
  const total = lines.reduce((sum, line) => sum + (Number(line.amount.replace(",", ".")) || 0), 0);

  /** Меняет одно поле строки. Пример: updateLine(2, { amount: "1200" }). */
  function updateLine(key: number, changes: Partial<Line>) {
    setLines((list) => list.map((line) => (line.key === key ? { ...line, ...changes } : line)));
  }

  function addLine() {
    setLines((list) => [...list, { key: nextKey, categoryId: firstCategory, amount: "", goalId: "" }]);
    setNextKey((key) => key + 1);
  }

  /** Проверяет поля и собирает тело запроса; null — есть ошибка (она уже показана). */
  function buildPayload(): ExpenseSummaryCheckInput | null {
    if (start === "" || end === "" || start > end) {
      setError("Проверьте даты периода: начало не может быть позже конца.");
      return null;
    }
    if (end > today) {
      setError("Сводку можно внести только за прошедшие дни.");
      return null;
    }
    const prepared = [];
    for (const line of lines) {
      const amount = Number(line.amount.replace(",", "."));
      if (line.categoryId === "" || !Number.isFinite(amount) || amount <= 0) {
        setError("В каждой строке выберите категорию и укажите сумму больше нуля.");
        return null;
      }
      prepared.push({ category_id: Number(line.categoryId), amount, goal_id: line.goalId ? Number(line.goalId) : null });
    }
    return { period_start: start, period_end: end, lines: prepared };
  }

  /** Сохраняет сводку (mode — ответ из окна сверки) и очищает форму. */
  async function save(data: ExpenseSummaryCheckInput, mode?: "add" | "replace", replaceIds?: number[]) {
    setBusy(true);
    setError(null);
    try {
      const result = await createExpenseSummary(ledgerId, {
        ...data,
        mode,
        replace_ids: replaceIds,
        note: optionalText(note),
      });
      const replaced = result.replaced_count > 0 ? `, заменено расходов: ${result.replaced_count}` : "";
      setSaved(`Сводка за ${formatPeriod(result.period_start, result.period_end)} сохранена: ${formatMoney(result.total, currency)}${replaced}.`);
      setCheck(null);
      setPayload(null);
      setLines([{ key: nextKey, categoryId: firstCategory, amount: "", goalId: "" }]);
      setNextKey((key) => key + 1);
      setNote("");
      onDone();
    } catch (err) {
      setError(getErrorText(err));
    } finally {
      setBusy(false);
    }
  }

  /** «Сохранить»: сначала сверка; при пересечении — окно выбора, иначе сразу сохранение. */
  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSaved(null);
    const data = buildPayload();
    if (data === null) return;

    setBusy(true);
    let result: ExpenseSummaryCheck;
    try {
      result = await checkExpenseSummary(ledgerId, data);
    } catch (err) {
      setError(getErrorText(err));
      setBusy(false);
      return;
    }
    setBusy(false);
    if (result.matches.length === 0) {
      await save(data);
    } else {
      setPayload(data);
      setCheck(result);
    }
  }

  const cancelDialog = useCallback(() => {
    setCheck(null);
    setPayload(null);
    setError(null);
  }, []);

  return (
    <Card title="Сводка за период" description="Итог трат за день, неделю или месяц — несколькими строками сразу">
      <form onSubmit={handleSubmit} className="space-y-4">
        <Segmented
          label="Период"
          value={kind}
          onChange={(value) => setKind(value as PeriodKind)}
          options={[
            ["day", "День"],
            ["week", "Неделя"],
            ["month", "Месяц"],
            ["custom", "Свои даты"],
          ]}
        />
        {kind === "custom" ? (
          <div className="grid gap-4 sm:grid-cols-2">
            <TextField label="С" type="date" value={customStart} onChange={setCustomStart} max={today} required />
            <TextField label="По" type="date" value={customEnd} onChange={setCustomEnd} max={today} required />
          </div>
        ) : (
          <TextField
            label={kind === "day" ? "День" : kind === "week" ? "Любой день недели" : "Любой день месяца"}
            type="date"
            value={anchor}
            onChange={setAnchor}
            max={today}
            hint={start && end ? `Период: ${formatPeriod(start, end)}` : undefined}
            required
          />
        )}

        <div className="space-y-3">
          {lines.map((line, index) => (
            <div key={line.key} className="grid items-end gap-3 rounded-xl bg-slate-50 p-3 sm:grid-cols-[1fr_8rem_1fr_auto]">
              <SelectField
                label={`Категория ${index + 1}`}
                value={line.categoryId}
                onChange={(value) => updateLine(line.key, { categoryId: value })}
                options={expenseOptions}
              />
              <TextField
                label="Сумма"
                type="number"
                inputMode="decimal"
                min={0.01}
                step="0.01"
                value={line.amount}
                onChange={(value) => updateLine(line.key, { amount: value })}
                required
              />
              {goalChoices.length > 1 ? (
                <SelectField label="Цель" value={line.goalId} onChange={(value) => updateLine(line.key, { goalId: value })} options={goalChoices} />
              ) : (
                <span />
              )}
              <IconButton
                icon="trash"
                tone="danger"
                label={`Убрать строку ${index + 1}`}
                disabled={lines.length === 1}
                onClick={() => setLines((list) => list.filter((item) => item.key !== line.key))}
              />
            </div>
          ))}
          <div className="flex flex-wrap items-center justify-between gap-3">
            <Button size="sm" variant="secondary" onClick={addLine} disabled={lines.length >= 30}>
              Добавить строку
            </Button>
            <p className="text-sm text-slate-600">
              Итого: <span className="num font-semibold text-slate-900">{formatMoney(total, currency)}</span>
            </p>
          </div>
        </div>

        <TextField label="Пояснение (необязательно)" value={note} onChange={setNote} maxLength={250} placeholder="Чеки за неделю" />

        {error && check === null && <ErrorBanner message={error} />}
        {saved && (
          <p role="status" className="text-sm font-medium text-good-700">
            {saved}
          </p>
        )}
        <Button type="submit" loading={busy && check === null}>
          Сохранить сводку
        </Button>
      </form>

      {check && payload && (
        <SummaryReconcileDialog
          check={check}
          currency={currency}
          busy={busy}
          error={error}
          onAdd={() => void save(payload, "add")}
          onReplace={() => void save(payload, "replace", check.matches.map((match) => match.transaction_id))}
          onCancel={cancelDialog}
        />
      )}
    </Card>
  );
}
