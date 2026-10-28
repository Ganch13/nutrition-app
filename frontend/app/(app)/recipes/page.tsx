"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import FoodPicker from "@/components/FoodPicker";
import { recipeSummaryLine } from "@/components/RecipePicker";
import {
  Badge,
  Button,
  Card,
  ErrorBanner,
  Loading,
  PageHeader,
  SelectField,
  TextField,
} from "@/components/ui";
import { getErrorText } from "@/lib/api";
import { createRecipe, deleteRecipe, getHouseholds, getRecipes, updateRecipe } from "@/lib/endpoints";
import { formatNumber, MEAL_TYPE_LABELS, optionalText, toOptions } from "@/lib/format";
import type { Food, PlanMealType, Recipe, RecipeInput } from "@/lib/types";
import { useAsyncData } from "@/lib/use-async-data";

const PAGE_SIZE = 30;

// Типы приёмов пищи, для которых бывают рецепты
const RECIPE_MEAL_TYPES: PlanMealType[] = ["breakfast", "lunch", "dinner", "snack"];

/** Что сейчас показано в форме справа: новый рецепт, изменение своего или копия встроенного. */
type FormState = { mode: "new" } | { mode: "edit"; recipe: Recipe } | { mode: "copy"; recipe: Recipe };

/** Страница «Рецепты»: поиск, свои и семейные рецепты (состав на одну порцию). */
export default function RecipesPage() {
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [mealType, setMealType] = useState("");
  const [portableOnly, setPortableOnly] = useState(false);
  const [limit, setLimit] = useState(PAGE_SIZE);
  const [form, setForm] = useState<FormState>({ mode: "new" });
  const [openId, setOpenId] = useState<number | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  // Поиск отправляется через 300 мс после последнего нажатия клавиши
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebounced(query);
      setLimit(PAGE_SIZE);
    }, 300);
    return () => clearTimeout(timer);
  }, [query]);

  const load = useCallback(
    () =>
      getRecipes({
        q: debounced,
        mealType: mealType as PlanMealType | "",
        portable: portableOnly ? true : undefined,
        limit,
      }),
    [debounced, mealType, portableOnly, limit],
  );
  const { data, loading, error, reload } = useAsyncData(load);

  /** Удаляет свой рецепт после подтверждения; уже составленные планы сохраняются. */
  async function handleDelete(recipe: Recipe) {
    if (!window.confirm(`Удалить рецепт «${recipe.name}»? Составленные планы питания сохранятся.`)) return;
    setActionError(null);
    try {
      await deleteRecipe(recipe.id);
      if (form.mode === "edit" && form.recipe.id === recipe.id) setForm({ mode: "new" });
      reload();
    } catch (err) {
      setActionError(getErrorText(err));
    }
  }

  return (
    <>
      <PageHeader
        title="Рецепты"
        subtitle="Блюда на одну порцию. Из них составляется меню на неделю, список закупок и план готовки"
      />

      <div className="grid gap-6 xl:grid-cols-[1fr_440px]">
        <div className="space-y-4">
          <Card>
            <div className="grid gap-3 sm:grid-cols-2">
              <TextField label="Поиск" value={query} onChange={setQuery} placeholder="Например: гречка" />
              <SelectField
                label="Приём пищи"
                value={mealType}
                onChange={(value) => {
                  setMealType(value);
                  setLimit(PAGE_SIZE);
                }}
                options={[["", "Любой"], ...RECIPE_MEAL_TYPES.map((type): [string, string] => [type, MEAL_TYPE_LABELS[type]])]}
              />
            </div>
            <label className="mt-3 flex items-center gap-2 text-sm text-slate-700">
              <input type="checkbox" checked={portableOnly} onChange={(event) => setPortableOnly(event.target.checked)} />
              Только блюда «с собой» (можно съесть на работе)
            </label>
            <p className="mt-3 text-xs text-slate-500">
              Встроенные рецепты изменить нельзя, но можно сделать свою копию.{" "}
              <Link href="/meal-plan" className="underline">К меню на неделю</Link>
            </p>
          </Card>

          {error && <ErrorBanner message={error} onRetry={reload} />}
          {actionError && <ErrorBanner message={actionError} />}
          {loading && data === null && <Loading />}
          {data?.items.length === 0 && <p className="text-sm text-slate-500">Ничего не найдено.</p>}

          <ul className="space-y-2">
            {data?.items.map((recipe) => (
              <li key={recipe.id} className="rounded-2xl border border-slate-200 bg-white p-4">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="font-medium">{recipe.name}</p>
                    <p className="text-xs text-slate-500">{recipeSummaryLine(recipe)} · на порцию</p>
                    <p className="text-xs text-slate-400">
                      {recipe.meal_types.map((type) => MEAL_TYPE_LABELS[type]).join(", ")} · готовка {recipe.prep_minutes} мин ·
                      хранится {recipe.keeps_days} дн.
                    </p>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    {recipe.portable && <Badge tone="green">с собой</Badge>}
                    {recipe.source === "household" && <Badge tone="amber">семейный</Badge>}
                    {recipe.source === "personal" && <Badge>мой</Badge>}
                  </div>
                </div>

                <div className="mt-2 flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setOpenId(openId === recipe.id ? null : recipe.id)}
                    className="text-xs text-slate-500 underline"
                  >
                    {openId === recipe.id ? "Скрыть состав" : "Состав и приготовление"}
                  </button>
                  {recipe.can_edit ? (
                    <>
                      <Button variant="secondary" onClick={() => setForm({ mode: "edit", recipe })}>
                        Изменить
                      </Button>
                      <Button variant="danger" onClick={() => handleDelete(recipe)}>
                        Удалить
                      </Button>
                    </>
                  ) : (
                    <Button variant="secondary" onClick={() => setForm({ mode: "copy", recipe })}>
                      Сделать свою копию
                    </Button>
                  )}
                </div>

                {openId === recipe.id && (
                  <div className="mt-3 space-y-3 rounded-xl bg-slate-50 px-3 py-3 text-sm">
                    <ul className="space-y-0.5 text-xs text-slate-600">
                      {recipe.ingredients.map((ingredient) => (
                        <li key={ingredient.food_id} className="flex justify-between gap-3">
                          <span>{ingredient.name}</span>
                          <span className="shrink-0">
                            {formatNumber(ingredient.amount_g, 0)} г
                            {ingredient.serving_grams &&
                              ` ≈ ${formatNumber(Number(ingredient.amount_g) / Number(ingredient.serving_grams), 1)} × «${ingredient.serving_name}»`}
                          </span>
                        </li>
                      ))}
                    </ul>
                    {recipe.instructions && <p className="text-slate-700">{recipe.instructions}</p>}
                  </div>
                )}
              </li>
            ))}
          </ul>

          {data && data.total > data.items.length && (
            <Button variant="secondary" onClick={() => setLimit(limit + PAGE_SIZE)}>
              Показать ещё ({data.items.length} из {data.total})
            </Button>
          )}
        </div>

        <Card
          title={form.mode === "edit" ? "Изменить рецепт" : form.mode === "copy" ? "Своя копия рецепта" : "Новый рецепт"}
        >
          <RecipeForm
            key={form.mode === "new" ? "new" : `${form.mode}-${form.recipe.id}`}
            state={form}
            onSaved={() => {
              setForm({ mode: "new" });
              reload();
            }}
            onCancel={form.mode === "new" ? undefined : () => setForm({ mode: "new" })}
          />
        </Card>
      </div>
    </>
  );
}

/** Ингредиент в форме: масса хранится строкой (как в поле ввода), ккал на 100 г нужны для подсчёта итога. */
type IngredientRow = { food_id: number; name: string; amount: string; kcalPer100: number };

/**
 * Форма рецепта: создание, изменение или копия встроенного.
 * Состав задаётся на одну порцию; внизу показан примерный итог калорий.
 */
function RecipeForm({
  state,
  onSaved,
  onCancel,
}: {
  state: FormState;
  onSaved: () => void;
  onCancel?: () => void;
}) {
  const source = state.mode === "new" ? null : state.recipe;
  const { data: households } = useAsyncData(getHouseholds);

  const [name, setName] = useState(source ? (state.mode === "copy" ? `${source.name} (моя версия)` : source.name) : "");
  const [mealTypes, setMealTypes] = useState<PlanMealType[]>(source?.meal_types ?? ["lunch"]);
  const [portable, setPortable] = useState(source?.portable ?? false);
  const [prepMinutes, setPrepMinutes] = useState(String(source?.prep_minutes ?? 20));
  const [keepsDays, setKeepsDays] = useState(String(source?.keeps_days ?? 2));
  const [instructions, setInstructions] = useState(source?.instructions ?? "");
  const [householdId, setHouseholdId] = useState("");
  const [rows, setRows] = useState<IngredientRow[]>(
    source
      ? source.ingredients.map((ingredient) => ({
          food_id: ingredient.food_id,
          name: ingredient.name,
          amount: String(Number(ingredient.amount_g)),
          kcalPer100: (Number(ingredient.calories) / Number(ingredient.amount_g)) * 100,
        }))
      : [],
  );
  const [adding, setAdding] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const totalKcal = rows.reduce((sum, row) => sum + (Number(row.amount) * row.kcalPer100) / 100, 0);

  function toggleMealType(type: PlanMealType) {
    setMealTypes((current) => (current.includes(type) ? current.filter((item) => item !== type) : [...current, type]));
  }

  /** Добавляет выбранный продукт в состав (если он уже есть, ничего не меняет). */
  function addFood(food: Food) {
    setAdding(false);
    setRows((current) => {
      if (current.some((row) => row.food_id === food.id)) return current;
      const grams = food.serving_grams ? Number(food.serving_grams) : 100;
      return [
        ...current,
        { food_id: food.id, name: food.name, amount: String(grams), kcalPer100: Number(food.calories_per_100g) },
      ];
    });
  }

  /** Отправляет форму: PATCH для изменения, POST для нового рецепта и копии. */
  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    if (mealTypes.length === 0) return setError("Выберите хотя бы один приём пищи.");
    if (rows.length === 0) return setError("Добавьте хотя бы один продукт в состав.");
    if (rows.some((row) => !(Number(row.amount) > 0))) return setError("Масса каждого продукта должна быть больше нуля.");

    const values = {
      name: name.trim(),
      meal_types: mealTypes,
      portable,
      prep_minutes: Number(prepMinutes),
      keeps_days: Number(keepsDays),
      instructions: optionalText(instructions),
      ingredients: rows.map((row) => ({ food_id: row.food_id, amount_g: Number(row.amount) })),
    };

    setSaving(true);
    try {
      if (state.mode === "edit") {
        await updateRecipe(state.recipe.id, values);
      } else {
        const input: RecipeInput = { ...values, household_id: householdId === "" ? null : Number(householdId) };
        await createRecipe(input);
      }
      onSaved();
    } catch (err) {
      setError(getErrorText(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <TextField label="Название" value={name} onChange={setName} required maxLength={150} />

      <fieldset className="space-y-1.5">
        <legend className="text-sm font-medium text-slate-700">Подходит для</legend>
        <div className="flex flex-wrap gap-x-4 gap-y-1">
          {RECIPE_MEAL_TYPES.map((type) => (
            <label key={type} className="flex items-center gap-1.5 text-sm text-slate-700">
              <input type="checkbox" checked={mealTypes.includes(type)} onChange={() => toggleMealType(type)} />
              {MEAL_TYPE_LABELS[type]}
            </label>
          ))}
        </div>
      </fieldset>

      <label className="flex items-center gap-2 text-sm text-slate-700">
        <input type="checkbox" checked={portable} onChange={(event) => setPortable(event.target.checked)} />
        Можно взять с собой на работу
      </label>

      <div className="grid grid-cols-2 gap-3">
        <TextField label="Готовка, мин" type="number" min={0} max={600} value={prepMinutes} onChange={setPrepMinutes} required />
        <TextField
          label="Хранится, дней"
          type="number"
          min={1}
          max={7}
          value={keepsDays}
          onChange={setKeepsDays}
          required
          hint="Сколько дней блюдо можно держать в холодильнике"
        />
      </div>

      <div className="space-y-2">
        <p className="text-sm font-medium text-slate-700">Состав на одну порцию</p>
        {rows.length === 0 && <p className="text-xs text-slate-500">Пока пусто.</p>}
        <ul className="space-y-2">
          {rows.map((row) => (
            <li key={row.food_id} className="flex items-end gap-2">
              <span className="min-w-0 flex-1 truncate pb-2 text-sm">{row.name}</span>
              <div className="w-24 shrink-0">
                <TextField
                  label="г"
                  type="number"
                  min={1}
                  max={3000}
                  step="1"
                  value={row.amount}
                  onChange={(value) =>
                    setRows((current) => current.map((item) => (item.food_id === row.food_id ? { ...item, amount: value } : item)))
                  }
                />
              </div>
              <button
                type="button"
                aria-label={`Убрать ${row.name}`}
                onClick={() => setRows((current) => current.filter((item) => item.food_id !== row.food_id))}
                className="pb-2 text-lg text-red-600"
              >
                ×
              </button>
            </li>
          ))}
        </ul>
        {adding ? (
          <div
            className="space-y-2 rounded-xl border border-slate-200 bg-slate-50 p-3"
            // Enter в поле поиска продукта не должен отправлять всю форму рецепта
            onKeyDown={(event) => {
              if (event.key === "Enter") event.preventDefault();
            }}
          >
            <FoodPicker onSelect={addFood} />
            <Button variant="secondary" onClick={() => setAdding(false)}>
              Закрыть поиск
            </Button>
          </div>
        ) : (
          <Button variant="secondary" onClick={() => setAdding(true)}>
            + Добавить продукт
          </Button>
        )}
        {rows.length > 0 && (
          <p className="text-xs text-slate-500">Итого примерно {formatNumber(totalKcal, 0)} ккал на порцию.</p>
        )}
      </div>

      <label className="block space-y-1.5">
        <span className="text-sm font-medium text-slate-700">Как готовить (необязательно)</span>
        <textarea
          value={instructions}
          onChange={(event) => setInstructions(event.target.value)}
          maxLength={4000}
          rows={3}
          className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none focus:border-brand-600"
        />
      </label>

      {state.mode !== "edit" && households && households.length > 0 && (
        <SelectField
          label="Кому доступен"
          value={householdId}
          onChange={setHouseholdId}
          options={[
            ["", "Только мне"],
            ...households.map((household): [string, string] => [String(household.id), `Семья «${household.name}»`]),
          ]}
        />
      )}

      <div className="flex gap-2">
        <Button type="submit" loading={saving}>
          {state.mode === "edit" ? "Сохранить" : "Добавить рецепт"}
        </Button>
        {onCancel && (
          <Button variant="secondary" onClick={onCancel}>
            Отмена
          </Button>
        )}
      </div>
      {error && <ErrorBanner message={error} />}
    </form>
  );
}
