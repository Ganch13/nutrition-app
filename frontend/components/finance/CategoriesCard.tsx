"use client";

import { useState } from "react";
import { Icon } from "@/components/icons";
import { Button, Card, ErrorBanner, SelectField, TextField } from "@/components/ui";
import { getErrorText } from "@/lib/api";
import { createFinanceCategory, deleteFinanceCategory } from "@/lib/endpoints";
import { FINANCE_KIND_LABELS, toOptions } from "@/lib/format";
import type { FinanceCategory, FinanceKind } from "@/lib/types";

const GROUP_TITLES: Record<FinanceKind, string> = { expense: "Категории расходов", income: "Категории доходов" };

/**
 * Категории книги: список и (для владельца и администратора) добавление и удаление.
 * Удалить можно категорию, в которой нет операций, иначе сервер вернёт понятную ошибку.
 * Подтверждение удаления показывается прямо в карточке, без системных окон.
 * categories — список из GET /finance/ledgers/{id}/categories; onChanged — перезагрузить список.
 */
export default function CategoriesCard({
  ledgerId,
  categories,
  canManage,
  onChanged,
}: {
  ledgerId: number;
  categories: FinanceCategory[];
  canManage: boolean;
  onChanged: () => void;
}) {
  const [name, setName] = useState("");
  const [kind, setKind] = useState<FinanceKind>("expense");
  const [adding, setAdding] = useState(false);
  // Категория, для которой сейчас спрашиваем подтверждение удаления
  const [confirmId, setConfirmId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  /** Добавляет категорию: POST .../categories. Пример: { name: "Подарки", kind: "expense" }. */
  async function handleAdd(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setAdding(true);
    try {
      await createFinanceCategory(ledgerId, { name: name.trim(), kind });
      setName("");
      onChanged();
    } catch (err) {
      setError(getErrorText(err));
    } finally {
      setAdding(false);
    }
  }

  /** Удаляет категорию после подтверждения: DELETE .../categories/{id}. */
  async function handleDelete(category: FinanceCategory) {
    setError(null);
    try {
      await deleteFinanceCategory(ledgerId, category.id);
      setConfirmId(null);
      onChanged();
    } catch (err) {
      setError(getErrorText(err));
      setConfirmId(null);
    }
  }

  return (
    <Card title="Категории" description="По ним группируются операции и считаются лимиты.">
      <div className="space-y-5">
        {(["expense", "income"] as FinanceKind[]).map((groupKind) => (
          <div key={groupKind}>
            <p className="mb-2 text-sm font-medium text-slate-600">{GROUP_TITLES[groupKind]}</p>
            <ul className="flex flex-wrap gap-2">
              {categories
                .filter((category) => category.kind === groupKind)
                .map((category) =>
                  confirmId === category.id ? (
                    <li key={category.id} className="flex items-center gap-2 rounded-full bg-red-50 py-1 pl-3 pr-1 text-sm text-red-700">
                      Удалить «{category.name}»?
                      <Button size="sm" variant="danger-solid" onClick={() => handleDelete(category)}>
                        Удалить
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => setConfirmId(null)}>
                        Нет
                      </Button>
                    </li>
                  ) : (
                    <li
                      key={category.id}
                      className="inline-flex items-center gap-1 rounded-full bg-slate-100 py-1 pl-3.5 pr-1.5 text-sm text-slate-800"
                    >
                      {category.name}
                      {canManage && (
                        <button
                          type="button"
                          onClick={() => setConfirmId(category.id)}
                          className="flex size-6 items-center justify-center rounded-full text-slate-500 hover:bg-white hover:text-red-600"
                          aria-label={`Удалить категорию ${category.name}`}
                        >
                          <Icon name="x" size={14} />
                        </button>
                      )}
                    </li>
                  ),
                )}
            </ul>
          </div>
        ))}
      </div>

      {canManage ? (
        <form onSubmit={handleAdd} className="mt-6 grid gap-4 border-t border-slate-100 pt-5 sm:grid-cols-[1fr_12rem_auto] sm:items-end">
          <TextField label="Новая категория" value={name} onChange={setName} required maxLength={80} />
          <SelectField
            label="Тип"
            value={kind}
            onChange={(value) => setKind(value as FinanceKind)}
            options={toOptions(FINANCE_KIND_LABELS)}
          />
          <Button type="submit" loading={adding}>
            Добавить
          </Button>
        </form>
      ) : (
        <p className="mt-5 text-sm text-slate-500">Категориями управляют владелец и администратор семьи.</p>
      )}

      {error && (
        <div className="mt-4">
          <ErrorBanner message={error} />
        </div>
      )}
    </Card>
  );
}
