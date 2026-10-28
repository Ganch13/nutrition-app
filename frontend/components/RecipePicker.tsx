"use client";

import { useCallback, useEffect, useState } from "react";
import { Badge, ErrorBanner, Loading, TextField } from "@/components/ui";
import { getRecipes } from "@/lib/endpoints";
import { formatNumber } from "@/lib/format";
import type { PlanMealType, Recipe } from "@/lib/types";
import { useAsyncData } from "@/lib/use-async-data";

/** Короткая строка пищевой ценности порции: "510 ккал · Б 48 · Ж 14 · У 54". */
export function recipeSummaryLine(recipe: Recipe): string {
  return (
    `${formatNumber(recipe.calories, 0)} ккал · Б ${formatNumber(recipe.protein_g, 0)} · ` +
    `Ж ${formatNumber(recipe.fat_g, 0)} · У ${formatNumber(recipe.carbs_g, 0)}`
  );
}

/**
 * Выбор рецепта: поиск и список результатов.
 * Аргументы: onSelect — вызывается с рецептом, на который нажали;
 * mealType — показывать только рецепты для этого приёма пищи (необязательно);
 * portableOnly — только блюда «с собой» (для еды на работе);
 * selectedId — id уже выбранного рецепта (подсвечивается).
 */
export default function RecipePicker({
  onSelect,
  mealType,
  portableOnly = false,
  selectedId,
}: {
  onSelect: (recipe: Recipe) => void;
  mealType?: PlanMealType;
  portableOnly?: boolean;
  selectedId?: number | null;
}) {
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");

  // Задержка поиска: пока пользователь печатает, лишних запросов нет
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(query), 300);
    return () => clearTimeout(timer);
  }, [query]);

  const load = useCallback(
    () => getRecipes({ q: debounced, mealType, portable: portableOnly ? true : undefined, limit: 8 }),
    [debounced, mealType, portableOnly],
  );
  const { data, loading, error, reload } = useAsyncData(load);

  return (
    <div className="space-y-3">
      <TextField label="Поиск рецепта" value={query} onChange={setQuery} placeholder="Например: курица" />

      {error && <ErrorBanner message={error} onRetry={reload} />}
      {loading && data === null && <Loading />}
      {data && data.items.length === 0 && <p className="text-sm text-slate-500">Ничего не найдено.</p>}

      <ul className="divide-y divide-slate-100 rounded-xl border border-slate-200">
        {data?.items.map((recipe) => (
          <li key={recipe.id}>
            <button
              type="button"
              onClick={() => onSelect(recipe)}
              className={`flex w-full items-start justify-between gap-3 px-3 py-2 text-left text-sm hover:bg-slate-50 ${
                selectedId === recipe.id ? "bg-brand-50" : ""
              }`}
            >
              <span className="min-w-0">
                <span className="block font-medium">{recipe.name}</span>
                <span className="block text-xs text-slate-500">{recipeSummaryLine(recipe)}</span>
              </span>
              <span className="flex shrink-0 flex-col items-end gap-1">
                {recipe.portable && <Badge tone="green">с собой</Badge>}
                {recipe.source !== "builtin" && (
                  <Badge tone={recipe.source === "household" ? "amber" : "slate"}>
                    {recipe.source === "household" ? "семейный" : "мой"}
                  </Badge>
                )}
              </span>
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
