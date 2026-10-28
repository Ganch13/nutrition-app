"use client";

import { useCallback, useEffect, useState } from "react";
import { Badge, ErrorBanner, Loading, SelectField, TextField } from "@/components/ui";
import { getFoods } from "@/lib/endpoints";
import { FOOD_CATEGORY_LABELS, formatNumber, toOptions } from "@/lib/format";
import type { Food, FoodCategory } from "@/lib/types";
import { useAsyncData } from "@/lib/use-async-data";

/** Короткая строка пищевой ценности на 100 г: "121 ккал · Б 17 · Ж 5 · У 2". */
export function foodSummaryLine(food: Food): string {
  return (
    `${formatNumber(food.calories_per_100g, 0)} ккал · Б ${formatNumber(food.protein_per_100g, 1)} · ` +
    `Ж ${formatNumber(food.fat_per_100g, 1)} · У ${formatNumber(food.carbs_per_100g, 1)} (на 100 г)`
  );
}

/**
 * Выбор продукта из справочника: поле поиска, фильтр по категории и список результатов.
 * Аргументы: onSelect — вызывается с продуктом, на который нажали;
 * selectedId — id уже выбранного продукта (он подсвечивается).
 * Запрос к серверу отправляется через 300 мс после последнего нажатия клавиши.
 */
export default function FoodPicker({
  onSelect,
  selectedId,
}: {
  onSelect: (food: Food) => void;
  selectedId?: number | null;
}) {
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [category, setCategory] = useState("");

  // Задержка поиска: пока пользователь печатает, лишних запросов нет
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(query), 300);
    return () => clearTimeout(timer);
  }, [query]);

  const load = useCallback(
    () => getFoods({ q: debounced, category: category as FoodCategory | "", limit: 8 }),
    [debounced, category],
  );
  const { data, loading, error, reload } = useAsyncData(load);

  return (
    <div className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <TextField label="Поиск продукта" value={query} onChange={setQuery} placeholder="Например: творог" />
        <SelectField
          label="Категория"
          value={category}
          onChange={setCategory}
          options={[["", "Все категории"], ...toOptions(FOOD_CATEGORY_LABELS)]}
        />
      </div>

      {error && <ErrorBanner message={error} onRetry={reload} />}
      {loading && data === null && <Loading />}
      {data && data.items.length === 0 && <p className="text-sm text-slate-500">Ничего не найдено.</p>}

      <ul className="divide-y divide-slate-100 rounded-xl border border-slate-200">
        {data?.items.map((food) => (
          <li key={food.id}>
            <button
              type="button"
              onClick={() => onSelect(food)}
              className={`flex w-full items-start justify-between gap-3 px-3 py-2 text-left text-sm hover:bg-slate-50 ${
                selectedId === food.id ? "bg-brand-50" : ""
              }`}
            >
              <span className="min-w-0">
                <span className="block font-medium">{food.name}</span>
                <span className="block text-xs text-slate-500">{foodSummaryLine(food)}</span>
              </span>
              {food.source !== "builtin" && (
                <Badge tone={food.source === "household" ? "amber" : "slate"}>
                  {food.source === "household" ? "семейный" : "мой"}
                </Badge>
              )}
            </button>
          </li>
        ))}
      </ul>
      {data && data.total > data.items.length && (
        <p className="text-xs text-slate-500">
          Показано {data.items.length} из {data.total}. Уточните запрос.
        </p>
      )}
    </div>
  );
}
