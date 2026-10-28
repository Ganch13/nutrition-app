"use client";

import { useCallback, useEffect, useState } from "react";
import { foodSummaryLine } from "@/components/FoodPicker";
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
import { createFood, deleteFood, getFoods, getHouseholds, updateFood } from "@/lib/endpoints";
import { FOOD_CATEGORY_LABELS, formatNumber, optionalNumber, optionalText, toOptions } from "@/lib/format";
import type { Food, FoodCategory, FoodInput } from "@/lib/types";
import { useAsyncData } from "@/lib/use-async-data";

const PAGE_SIZE = 30;

/** Страница «Продукты»: поиск по справочнику, свои и семейные продукты. */
export default function FoodsPage() {
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [category, setCategory] = useState("");
  const [limit, setLimit] = useState(PAGE_SIZE);
  const [editing, setEditing] = useState<Food | null>(null);
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
    () => getFoods({ q: debounced, category: category as FoodCategory | "", limit }),
    [debounced, category, limit],
  );
  const { data, loading, error, reload } = useAsyncData(load);

  /** Удаляет свой продукт после подтверждения; записи питания остаются. */
  async function handleDelete(food: Food) {
    if (!window.confirm(`Удалить продукт «${food.name}»? Уже сделанные записи питания сохранятся.`)) return;
    setActionError(null);
    try {
      await deleteFood(food.id);
      reload();
    } catch (err) {
      setActionError(getErrorText(err));
    }
  }

  return (
    <>
      <PageHeader
        title="Продукты"
        subtitle="Справочник калорийности и состава. Значения встроенных продуктов ориентировочные"
      />

      <div className="grid gap-6 xl:grid-cols-[1fr_400px]">
        <div className="space-y-4">
          <Card>
            <div className="grid gap-3 sm:grid-cols-2">
              <TextField label="Поиск" value={query} onChange={setQuery} placeholder="Например: гречка" />
              <SelectField
                label="Категория"
                value={category}
                onChange={(value) => {
                  setCategory(value);
                  setLimit(PAGE_SIZE);
                }}
                options={[["", "Все категории"], ...toOptions(FOOD_CATEGORY_LABELS)]}
              />
            </div>
            <p className="mt-3 text-xs text-slate-500">
              Встроенные значения — средние по общедоступным таблицам, у разных производителей они отличаются.
              Для точного учёта добавьте свой продукт с данными с упаковки.
            </p>
          </Card>

          {error && <ErrorBanner message={error} onRetry={reload} />}
          {actionError && <ErrorBanner message={actionError} />}
          {loading && data === null && <Loading />}
          {data?.items.length === 0 && <p className="text-sm text-slate-500">Ничего не найдено.</p>}

          <ul className="space-y-2">
            {data?.items.map((food) => (
              <li key={food.id} className="rounded-2xl border border-slate-200 bg-white p-4">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="font-medium">{food.name}</p>
                    <p className="text-xs text-slate-500">
                      {FOOD_CATEGORY_LABELS[food.category]} · {foodSummaryLine(food)}
                    </p>
                    {food.serving_name && food.serving_grams && (
                      <p className="text-xs text-slate-400">
                        {food.serving_name} = {formatNumber(food.serving_grams, 0)} г
                      </p>
                    )}
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    {food.source === "household" && <Badge tone="amber">семейный</Badge>}
                    {food.source === "personal" && <Badge>мой</Badge>}
                    {food.can_edit && (
                      <>
                        <Button variant="secondary" onClick={() => setEditing(food)}>
                          Изменить
                        </Button>
                        <Button variant="danger" onClick={() => handleDelete(food)}>
                          Удалить
                        </Button>
                      </>
                    )}
                  </div>
                </div>
              </li>
            ))}
          </ul>

          {data && data.total > data.items.length && (
            <Button variant="secondary" onClick={() => setLimit(limit + PAGE_SIZE)}>
              Показать ещё ({data.items.length} из {data.total})
            </Button>
          )}
        </div>

        <Card title={editing ? "Изменить продукт" : "Свой продукт"}>
          <FoodForm
            key={editing?.id ?? "new"}
            food={editing}
            onSaved={() => {
              setEditing(null);
              reload();
            }}
            onCancel={editing ? () => setEditing(null) : undefined}
          />
        </Card>
      </div>
    </>
  );
}

/**
 * Форма продукта: создание (food = null) или изменение.
 * Значения вводятся на 100 г. Для нового продукта можно выбрать семью, тогда его увидят все участники.
 */
function FoodForm({
  food,
  onSaved,
  onCancel,
}: {
  food: Food | null;
  onSaved: () => void;
  onCancel?: () => void;
}) {
  const { data: households } = useAsyncData(getHouseholds);

  const [name, setName] = useState(food?.name ?? "");
  const [category, setCategory] = useState<string>(food?.category ?? "other");
  const [calories, setCalories] = useState(food ? String(Number(food.calories_per_100g)) : "");
  const [protein, setProtein] = useState(food ? String(Number(food.protein_per_100g)) : "0");
  const [fat, setFat] = useState(food ? String(Number(food.fat_per_100g)) : "0");
  const [carbs, setCarbs] = useState(food ? String(Number(food.carbs_per_100g)) : "0");
  const [servingName, setServingName] = useState(food?.serving_name ?? "");
  const [servingGrams, setServingGrams] = useState(food?.serving_grams ? String(Number(food.serving_grams)) : "");
  const [householdId, setHouseholdId] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /** Отправляет форму: PATCH для существующего продукта, POST для нового. */
  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    const servingNameValue = optionalText(servingName);
    const servingGramsValue = optionalNumber(servingGrams);
    if ((servingNameValue === null) !== (servingGramsValue === null)) {
      setError("Название порции и её масса задаются вместе: заполните оба поля или оставьте оба пустыми.");
      return;
    }

    const values = {
      name: name.trim(),
      category: category as FoodCategory,
      calories_per_100g: Number(calories),
      protein_per_100g: Number(protein),
      fat_per_100g: Number(fat),
      carbs_per_100g: Number(carbs),
      serving_name: servingNameValue,
      serving_grams: servingGramsValue,
    };

    setSaving(true);
    try {
      if (food) {
        await updateFood(food.id, values);
      } else {
        const input: FoodInput = { ...values, household_id: householdId === "" ? null : Number(householdId) };
        await createFood(input);
        setName("");
        setCalories("");
        setProtein("0");
        setFat("0");
        setCarbs("0");
        setServingName("");
        setServingGrams("");
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
      <SelectField label="Категория" value={category} onChange={setCategory} options={toOptions(FOOD_CATEGORY_LABELS)} />
      <p className="text-xs text-slate-500">Значения на 100 г продукта (как на упаковке).</p>
      <div className="grid grid-cols-2 gap-3">
        <TextField label="Калории, ккал" type="number" min={0} max={900} step="0.1" value={calories} onChange={setCalories} required />
        <TextField label="Белки, г" type="number" min={0} max={100} step="0.1" value={protein} onChange={setProtein} required />
        <TextField label="Жиры, г" type="number" min={0} max={100} step="0.1" value={fat} onChange={setFat} required />
        <TextField label="Углеводы, г" type="number" min={0} max={100} step="0.1" value={carbs} onChange={setCarbs} required />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <TextField label="Порция (необязательно)" value={servingName} onChange={setServingName} maxLength={40} placeholder="1 пачка" />
        <TextField label="Масса порции, г" type="number" min={0} step="0.1" value={servingGrams} onChange={setServingGrams} />
      </div>

      {!food && households && households.length > 0 && (
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
          {food ? "Сохранить" : "Добавить продукт"}
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
