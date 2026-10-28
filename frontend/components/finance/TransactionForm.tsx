"use client";

import { useState } from "react";
import { Button, Card, ErrorBanner, Segmented, SelectField, TextField } from "@/components/ui";
import { getErrorText } from "@/lib/api";
import { createFinanceTransaction } from "@/lib/endpoints";
import { optionalText } from "@/lib/format";
import type { FinanceCategory, FinanceKind } from "@/lib/types";

/**
 * Форма добавления операции: расход или доход, сумма, категория, дата и описание.
 * Сначала сумма, потому что чаще всего человек помнит именно её.
 * Пример запроса, который уходит на сервер: { category_id: 3, amount: 450, occurred_on: "2026-10-28", description: "Хлеб и молоко" }.
 * onAdded — вызывается после добавления, чтобы страница обновила список.
 */
export default function TransactionForm({
  ledgerId,
  categories,
  today,
  onAdded,
}: {
  ledgerId: number;
  categories: FinanceCategory[];
  today: string;
  onAdded: () => void;
}) {
  const [kind, setKind] = useState<FinanceKind>("expense");
  const [categoryId, setCategoryId] = useState("");
  const [amount, setAmount] = useState("");
  const [date, setDate] = useState(today);
  const [description, setDescription] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Категории выбранного вида в виде пар [id, название]
  const options = categories
    .filter((category) => category.kind === kind)
    .map((category): [string, string] => [String(category.id), category.name]);
  // Если выбранная категория не подходит к виду, используем первую из списка
  const selected = options.some(([value]) => value === categoryId) ? categoryId : (options[0]?.[0] ?? "");

  /** Добавляет операцию и обновляет данные страницы. */
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

    setSaving(true);
    try {
      await createFinanceTransaction(ledgerId, {
        category_id: Number(selected),
        amount: value,
        occurred_on: date,
        description: optionalText(description),
      });
      setAmount("");
      setDescription("");
      onAdded();
    } catch (err) {
      setError(getErrorText(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card title="Новая операция">
      <form onSubmit={handleSubmit} className="space-y-4">
        <Segmented
          label="Вид операции"
          value={kind}
          onChange={(value) => setKind(value as FinanceKind)}
          options={[
            ["expense", "Расход"],
            ["income", "Доход"],
          ]}
        />
        <div className="grid gap-4 sm:grid-cols-2">
          <TextField label="Сумма" type="number" inputMode="decimal" min={0.01} step="0.01" value={amount} onChange={setAmount} required />
          <SelectField label="Категория" value={selected} onChange={setCategoryId} options={options} />
          <TextField label="Дата" type="date" value={date} onChange={setDate} required />
          <TextField label="Описание (необязательно)" value={description} onChange={setDescription} maxLength={250} />
        </div>
        {error && <ErrorBanner message={error} />}
        <Button type="submit" loading={saving}>
          Добавить
        </Button>
      </form>
    </Card>
  );
}
