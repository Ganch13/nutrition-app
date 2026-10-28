"use client";

import { useState } from "react";
import { Button, Card, EmptyState, ErrorBanner, ProgressBar, SelectField, TextField } from "@/components/ui";
import { getErrorText } from "@/lib/api";
import { setFinanceBudget } from "@/lib/endpoints";
import { formatMoney } from "@/lib/format";
import type { CategorySummary, Ledger } from "@/lib/types";

/**
 * Лимиты расходов по категориям за текущий период. Лимит действует на период целиком:
 * на календарный месяц или на промежуток между поступлениями дохода (как выбрано в настройках книги).
 * Менять лимиты могут владелец и администратор семьи (или хозяин личной книги); остальные только смотрят.
 * categories — итоги по категориям из GET .../period-summary; onChanged — обновить данные страницы.
 */
export default function LimitsCard({
  ledger,
  categories,
  onChanged,
}: {
  ledger: Ledger;
  categories: CategorySummary[];
  onChanged: () => void;
}) {
  const money = (value: string | number) => formatMoney(value, ledger.currency);
  const expenses = categories.filter((row) => row.kind === "expense");
  // Показываем категории, где есть лимит или расходы
  const visible = expenses.filter((row) => row.budget_limit !== null || Number(row.total) > 0);
  const withoutLimit = expenses.filter((row) => row.budget_limit === null);

  // Какая категория сейчас редактируется и что введено в поле
  const [editing, setEditing] = useState<number | null>(null);
  const [value, setValue] = useState("");
  const [newCategory, setNewCategory] = useState("");
  const [newLimit, setNewLimit] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  /** Сохраняет лимит категории (число) или убирает его (null). */
  async function save(categoryId: number, limit: number | null) {
    setError(null);
    setSaving(true);
    try {
      await setFinanceBudget(ledger.id, categoryId, limit);
      setEditing(null);
      setNewLimit("");
      onChanged();
    } catch (err) {
      setError(getErrorText(err));
    } finally {
      setSaving(false);
    }
  }

  /** Превращает текст поля в положительное число или null, если введено что-то неподходящее. */
  function parseLimit(text: string): number | null {
    const number = Number(text.replace(",", "."));
    return Number.isFinite(number) && number > 0 ? number : null;
  }

  const periodWord = ledger.cycle_mode === "income" ? "период" : "месяц";
  const selectedNew = withoutLimit.some((row) => String(row.category_id) === newCategory)
    ? newCategory
    : String(withoutLimit[0]?.category_id ?? "");

  return (
    <Card title="Лимиты по категориям" description={`Лимит действует на весь ${periodWord}. Полоска показывает, сколько уже потрачено.`}>
      {error && (
        <div className="mb-4">
          <ErrorBanner message={error} />
        </div>
      )}

      {visible.length === 0 ? (
        <EmptyState title="Пока нет расходов и лимитов">
          Добавьте расход на вкладке «Операции» или задайте лимит ниже.
        </EmptyState>
      ) : (
        <ul className="space-y-5">
          {visible.map((row) => {
            const spent = Number(row.total);
            const limit = row.budget_limit === null ? null : Number(row.budget_limit);
            const over = limit !== null && spent > limit;
            return (
              <li key={row.category_id}>
                <div className="flex items-center justify-between gap-3 text-sm">
                  <span className="font-medium text-slate-900">{row.name}</span>
                  <span className={`num ${over ? "font-medium text-red-600" : "text-slate-600"}`}>
                    {money(spent)}
                    {limit !== null && ` из ${money(limit)}`}
                  </span>
                </div>
                {limit !== null && (
                  <div className="mt-2">
                    <ProgressBar label={`Расходы по категории «${row.name}»`} value={spent / limit} tone={over ? "red" : spent / limit > 0.85 ? "amber" : "brand"} />
                  </div>
                )}

                {ledger.can_manage &&
                  (editing === row.category_id ? (
                    <form
                      className="mt-3 flex flex-wrap items-end gap-3"
                      onSubmit={(event) => {
                        event.preventDefault();
                        const parsed = parseLimit(value);
                        if (parsed === null) {
                          setError("Лимит должен быть больше нуля.");
                          return;
                        }
                        void save(row.category_id, parsed);
                      }}
                    >
                      <div className="w-44">
                        <TextField label={`Лимит на ${periodWord}`} type="number" inputMode="decimal" min={0.01} step="0.01" value={value} onChange={setValue} required />
                      </div>
                      <Button type="submit" loading={saving}>
                        Сохранить
                      </Button>
                      {limit !== null && (
                        <Button variant="danger" disabled={saving} onClick={() => void save(row.category_id, null)}>
                          Убрать лимит
                        </Button>
                      )}
                      <Button variant="ghost" onClick={() => setEditing(null)}>
                        Отмена
                      </Button>
                    </form>
                  ) : (
                    <button
                      type="button"
                      className="mt-1 text-xs font-medium text-brand-700 underline underline-offset-2"
                      onClick={() => {
                        setEditing(row.category_id);
                        setValue(limit === null ? "" : String(limit));
                      }}
                    >
                      {limit === null ? "Задать лимит" : "Изменить лимит"}
                    </button>
                  ))}
              </li>
            );
          })}
        </ul>
      )}

      {ledger.can_manage && withoutLimit.length > 0 && (
        <form
          className="mt-6 grid gap-3 border-t border-slate-100 pt-5 sm:grid-cols-[1fr_1fr_auto] sm:items-end"
          onSubmit={(event) => {
            event.preventDefault();
            const parsed = parseLimit(newLimit);
            if (parsed === null || selectedNew === "") {
              setError("Выберите категорию и введите лимит больше нуля.");
              return;
            }
            void save(Number(selectedNew), parsed);
          }}
        >
          <SelectField
            label="Новый лимит для категории"
            value={selectedNew}
            onChange={setNewCategory}
            options={withoutLimit.map((row): [string, string] => [String(row.category_id), row.name])}
          />
          <TextField label={`Сумма на ${periodWord}`} type="number" inputMode="decimal" min={0.01} step="0.01" value={newLimit} onChange={setNewLimit} required />
          <Button type="submit" loading={saving}>
            Задать
          </Button>
        </form>
      )}
    </Card>
  );
}
