"use client";

import { useState } from "react";
import { Button, Card, ErrorBanner, Segmented, SelectField, TextField } from "@/components/ui";
import { getErrorText } from "@/lib/api";
import { createFinanceTransaction, updateFinanceTransaction } from "@/lib/endpoints";
import { optionalText } from "@/lib/format";
import type { FinanceCategory, FinanceGoal, FinanceGoalKind, FinanceKind, FinanceTransaction } from "@/lib/types";

// Как цель подписана в списке: «Отпуск — накопление»
const GOAL_KIND_WORD: Record<FinanceGoalKind, string> = { savings: "накопление", debt: "долг", loan: "кредит" };

// Значение «без цели» в выпадающем списке
const NO_GOAL = "";

/**
 * Варианты поля «Цель»: «Без цели» и цели этой книги. Достигнутые долг и кредит не предлагаются
 * (платить в них уже нечего), кроме цели, к которой расход уже отнесён.
 * Пример: [["", "Без цели"], ["3", "Отпуск — накопление"], ["5", "Долг Ивану — долг"]]
 */
function goalOptions(goals: FinanceGoal[], currentGoalId: number | null): [string, string][] {
  const open = goals.filter((goal) => goal.kind === "savings" || !goal.done || goal.id === currentGoalId);
  return [[NO_GOAL, "Без цели"], ...open.map((goal): [string, string] => [String(goal.id), `${goal.name} — ${GOAL_KIND_WORD[goal.kind]}`])];
}

/**
 * Форма операции: расход или доход, сумма, категория, дата, описание и (для расхода) цель.
 * Сначала сумма, потому что чаще всего человек помнит именно её.
 *
 * Без transaction — добавление новой операции (карточка «Новая операция»). Пример запроса:
 *   { category_id: 3, amount: 5000, occurred_on: "2026-10-28", description: "Отложил", goal_id: 1 }
 * С transaction — правка существующей (компактный блок под строкой списка), уходит PATCH с теми же полями;
 * вид операции (расход/доход) при правке не меняется.
 *
 * Цель: каждая цель книги (личная в личной книге, общая в семейной) — вариант выбора. Расход на цель сам
 * меняет цель на ту же сумму: у накопления прогресс растёт, у долга и кредита остаток уменьшается.
 * goals приходят со страницы, поэтому только что созданная цель сразу есть в списке.
 * onDone — вызывается после сохранения, чтобы страница обновила список; onCancel — закрыть правку.
 */
export default function TransactionForm({
  ledgerId,
  categories,
  goals,
  today,
  transaction,
  onDone,
  onCancel,
}: {
  ledgerId: number;
  categories: FinanceCategory[];
  goals: FinanceGoal[];
  today: string;
  transaction?: FinanceTransaction;
  onDone: () => void;
  onCancel?: () => void;
}) {
  const editing = transaction !== undefined;
  const [kind, setKind] = useState<FinanceKind>(transaction?.kind ?? "expense");
  const [categoryId, setCategoryId] = useState(transaction ? String(transaction.category_id) : "");
  const [amount, setAmount] = useState(transaction ? String(Number(transaction.amount)) : "");
  const [date, setDate] = useState(transaction?.occurred_on ?? today);
  const [description, setDescription] = useState(transaction?.description ?? "");
  const [goalId, setGoalId] = useState(transaction?.goal_id ? String(transaction.goal_id) : NO_GOAL);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Категории выбранного вида в виде пар [id, название]
  const options = categories
    .filter((category) => category.kind === kind)
    .map((category): [string, string] => [String(category.id), category.name]);
  // Если выбранная категория не подходит к виду, используем первую из списка
  const selected = options.some(([value]) => value === categoryId) ? categoryId : (options[0]?.[0] ?? "");
  const goalChoices = goalOptions(goals, transaction?.goal_id ?? null);
  // Цель только у расхода; у дохода поле скрыто и на сервер уходит «без цели»
  const chosenGoal = kind === "expense" && goalId !== NO_GOAL ? Number(goalId) : null;

  /** Сохраняет операцию (новую или изменённую) и обновляет данные страницы. */
  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    if (selected === "") {
      setError("Выберите категорию.");
      return;
    }
    const value = Number(amount.replace(",", "."));
    if (!Number.isFinite(value) || value <= 0) {
      setError("Сумма должна быть больше нуля.");
      return;
    }
    if (chosenGoal !== null && date > today) {
      setError("Расход на цель не может быть в будущем.");
      return;
    }

    const data = {
      category_id: Number(selected),
      amount: value,
      occurred_on: date,
      description: optionalText(description),
      goal_id: chosenGoal,
    };
    setSaving(true);
    try {
      if (transaction) {
        await updateFinanceTransaction(ledgerId, transaction.id, data);
      } else {
        await createFinanceTransaction(ledgerId, data);
        setAmount("");
        setDescription("");
        setGoalId(NO_GOAL);
      }
      onDone();
    } catch (err) {
      setError(getErrorText(err));
    } finally {
      setSaving(false);
    }
  }

  const fields = (
    <form onSubmit={handleSubmit} className="space-y-4">
      {!editing && (
        <Segmented
          label="Вид операции"
          value={kind}
          onChange={(value) => setKind(value as FinanceKind)}
          options={[
            ["expense", "Расход"],
            ["income", "Доход"],
          ]}
        />
      )}
      <div className="grid gap-4 sm:grid-cols-2">
        <TextField label="Сумма" type="number" inputMode="decimal" min={0.01} step="0.01" value={amount} onChange={setAmount} required />
        <SelectField label="Категория" value={selected} onChange={setCategoryId} options={options} />
        <TextField label="Дата" type="date" value={date} onChange={setDate} required />
        <TextField label="Описание (необязательно)" value={description} onChange={setDescription} maxLength={250} />
        {kind === "expense" && goalChoices.length > 1 && (
          <SelectField
            label="Цель"
            value={goalId}
            onChange={setGoalId}
            options={goalChoices}
            hint={chosenGoal !== null ? "Сумма сама попадёт в цель: вносить её там ещё раз не нужно" : undefined}
          />
        )}
      </div>
      {error && <ErrorBanner message={error} />}
      <div className="flex flex-wrap gap-3">
        <Button type="submit" loading={saving}>
          {editing ? "Сохранить" : "Добавить"}
        </Button>
        {onCancel && (
          <Button variant="secondary" onClick={onCancel} disabled={saving}>
            Отмена
          </Button>
        )}
      </div>
    </form>
  );

  return editing ? <div className="mt-3 rounded-xl bg-slate-50 p-4">{fields}</div> : <Card title="Новая операция">{fields}</Card>;
}
