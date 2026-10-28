"use client";

import { useCallback, useState } from "react";
import FoodPicker from "@/components/FoodPicker";
import HomeBlockReturn from "@/components/HomeBlockReturn";
import {
  Button,
  Card,
  ErrorBanner,
  Loading,
  PageHeader,
  SelectField,
  TextField,
} from "@/components/ui";
import PeriodNav from "@/components/PeriodNav";
import { getErrorText } from "@/lib/api";
import {
  createMealEntry,
  createMealFromFood,
  deleteMealEntry,
  getDailyEntries,
  getDailySummary,
} from "@/lib/endpoints";
import {
  currentTimeValue,
  formatDateLong,
  formatNumber,
  formatTime,
  MEAL_TYPE_LABELS,
  optionalText,
  shiftDate,
  todayInZone,
  toIsoFromLocal,
  toOptions,
} from "@/lib/format";
import { useProfile } from "@/lib/profile-context";
import type { Food, MealType } from "@/lib/types";
import { useAsyncData } from "@/lib/use-async-data";

/** Страница «Питание»: итоги выбранного дня, список приёмов пищи и форма добавления. */
export default function NutritionPage() {
  const { profile } = useProfile();
  const userId = profile.id;
  // Сегодня в часовом поясе профиля, например "2026-10-26"
  const today = todayInZone(profile.timezone);

  // Выбранный день, "ГГГГ-ММ-ДД"
  const [date, setDate] = useState(today);

  // Итоги и записи дня загружаются вместе и заново при смене даты
  const loadDay = useCallback(
    () => Promise.all([getDailySummary(userId, date), getDailyEntries(userId, date)]),
    [userId, date],
  );
  const day = useAsyncData(loadDay);
  // day.data → [итоги дня, список приёмов пищи] или null, пока данных нет
  const summary = day.data?.[0] ?? null;
  const entries = day.data?.[1] ?? null;

  // Поля формы. Время берём с устройства; дата — выбранный день страницы
  const [time, setTime] = useState(currentTimeValue);
  const [mealType, setMealType] = useState("lunch");
  const [description, setDescription] = useState("");
  const [calories, setCalories] = useState("");
  const [protein, setProtein] = useState("0");
  const [fat, setFat] = useState("0");
  const [carbs, setCarbs] = useState("0");
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  /** Добавляет приём пищи на выбранный день и обновляет итоги. */
  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);
    setSaving(true);
    try {
      await createMealEntry(userId, {
        // Дата страницы + время поля, например "2026-10-26T13:30" → ISO с часовым поясом устройства
        eaten_at: toIsoFromLocal(`${date}T${time}`),
        meal_type: mealType as MealType,
        description: description.trim(),
        calories: Number(calories),
        protein_g: Number(protein),
        fat_g: Number(fat),
        carbs_g: Number(carbs),
        notes: optionalText(notes),
      });
      setDescription("");
      setCalories("");
      setProtein("0");
      setFat("0");
      setCarbs("0");
      setNotes("");
      day.reload();
    } catch (err) {
      setFormError(getErrorText(err));
    } finally {
      setSaving(false);
    }
  }

  /** Удаляет приём пищи после подтверждения. */
  async function handleDelete(entryId: number) {
    if (!window.confirm("Удалить запись?")) return;
    setFormError(null);
    try {
      await deleteMealEntry(userId, entryId);
      day.reload();
    } catch (err) {
      setFormError(getErrorText(err));
    }
  }

  return (
    <>
      <PageHeader title="Питание" subtitle={formatDateLong(date)} />
      <HomeBlockReturn block="nutrition" />

      <div className="mb-6">
        <PeriodNav
          prevLabel="Предыдущий день"
          nextLabel="Следующий день"
          todayLabel="Сегодня"
          onPrev={() => setDate(shiftDate(date, -1))}
          onNext={() => setDate(shiftDate(date, 1))}
          onToday={() => setDate(today)}
          todayDisabled={date === today}
        />
      </div>

      {day.error && (
        <div className="mb-6">
          <ErrorBanner message={day.error} onRetry={day.reload} />
        </div>
      )}

      <div className="grid gap-6 xl:grid-cols-2">
        <div className="space-y-6">
          <Card title="Итоги дня">
            {summary === null ? (
              <Loading />
            ) : (
              <>
                <p className="text-3xl font-bold">
                  {formatNumber(summary.calories, 0)}
                  <span className="ml-2 text-sm font-normal text-slate-400">ккал</span>
                </p>
                <div className="mt-4 grid grid-cols-3 gap-3 text-sm">
                  <div className="rounded-xl bg-slate-50 p-3">
                    <p className="text-slate-500">Белки</p>
                    <p className="mt-1 font-semibold">{formatNumber(summary.protein_g, 0)} г</p>
                  </div>
                  <div className="rounded-xl bg-slate-50 p-3">
                    <p className="text-slate-500">Жиры</p>
                    <p className="mt-1 font-semibold">{formatNumber(summary.fat_g, 0)} г</p>
                  </div>
                  <div className="rounded-xl bg-slate-50 p-3">
                    <p className="text-slate-500">Углеводы</p>
                    <p className="mt-1 font-semibold">{formatNumber(summary.carbs_g, 0)} г</p>
                  </div>
                </div>
                <p className="mt-3 text-xs text-slate-500">Записей за день: {summary.entries_count}</p>
              </>
            )}
          </Card>

          <Card title="Добавить из справочника">
            <FoodMealForm userId={userId} date={date} onAdded={day.reload} />
          </Card>

          <Card title="Добавить приём пищи вручную">
            <form onSubmit={handleSubmit} className="grid gap-3 sm:grid-cols-2">
              <TextField label="Время" type="time" value={time} onChange={setTime} required />
              <SelectField
                label="Тип"
                value={mealType}
                onChange={setMealType}
                options={toOptions(MEAL_TYPE_LABELS)}
              />
              <div className="sm:col-span-2">
                <TextField
                  label="Что съели"
                  value={description}
                  onChange={setDescription}
                  required
                  maxLength={250}
                />
              </div>
              <TextField
                label="Калории, ккал"
                type="number"
                min={0}
                step="1"
                value={calories}
                onChange={setCalories}
                required
              />
              <TextField label="Белки, г" type="number" min={0} step="0.1" value={protein} onChange={setProtein} required />
              <TextField label="Жиры, г" type="number" min={0} step="0.1" value={fat} onChange={setFat} required />
              <TextField label="Углеводы, г" type="number" min={0} step="0.1" value={carbs} onChange={setCarbs} required />
              <div className="sm:col-span-2">
                <TextField label="Заметка (необязательно)" value={notes} onChange={setNotes} />
              </div>
              <div className="sm:col-span-2">
                <Button type="submit" loading={saving}>
                  Добавить
                </Button>
              </div>
            </form>
            {formError && (
              <div className="mt-4">
                <ErrorBanner message={formError} />
              </div>
            )}
          </Card>
        </div>

        <Card title="Приёмы пищи">
          {entries === null && day.loading && <Loading />}
          {entries?.length === 0 && <p className="text-sm text-slate-500">За этот день записей нет.</p>}
          <ul className="divide-y divide-slate-100">
            {entries?.map((entry) => (
              <li key={entry.id} className="flex items-center justify-between gap-3 py-3">
                <div className="min-w-0">
                  <p className="font-medium">
                    {formatTime(entry.eaten_at)} · {MEAL_TYPE_LABELS[entry.meal_type]}
                  </p>
                  <p className="truncate text-sm text-slate-500">{entry.description}</p>
                  <p className="text-xs text-slate-400">
                    {formatNumber(entry.calories, 0)} ккал · Б {formatNumber(entry.protein_g, 0)} · Ж{" "}
                    {formatNumber(entry.fat_g, 0)} · У {formatNumber(entry.carbs_g, 0)}
                  </p>
                </div>
                <Button variant="danger" onClick={() => handleDelete(entry.id)}>
                  Удалить
                </Button>
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </>
  );
}

/**
 * Добавление приёма пищи из справочника: найти продукт, указать граммы или порции.
 * Калории и БЖУ показываются сразу (расчёт на экране), а в дневник их записывает сервер.
 * Аргументы: userId — id пользователя; date — выбранный день "2026-10-27"; onAdded — обновить страницу.
 */
function FoodMealForm({ userId, date, onAdded }: { userId: number; date: string; onAdded: () => void }) {
  const [food, setFood] = useState<Food | null>(null);
  // "g" — вводим граммы, "serving" — число порций продукта (например, 2 яйца)
  const [unit, setUnit] = useState<"g" | "serving">("g");
  const [amount, setAmount] = useState("100");
  const [time, setTime] = useState(currentTimeValue);
  const [mealType, setMealType] = useState("lunch");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const servingGrams = food?.serving_grams ? Number(food.serving_grams) : null;
  const canUseServings = servingGrams !== null;
  // Масса в граммах: введённая или число порций × масса порции
  const grams = unit === "serving" && servingGrams !== null ? Number(amount) * servingGrams : Number(amount);
  // Предварительный расчёт для показа; сохранённые значения всё равно считает сервер
  const preview = food && grams > 0 ? {
    calories: (Number(food.calories_per_100g) * grams) / 100,
    protein: (Number(food.protein_per_100g) * grams) / 100,
    fat: (Number(food.fat_per_100g) * grams) / 100,
    carbs: (Number(food.carbs_per_100g) * grams) / 100,
  } : null;

  /** Выбор продукта: если у него есть порция, по умолчанию считаем порциями. */
  function handleSelect(selected: Food) {
    setFood(selected);
    if (selected.serving_grams) {
      setUnit("serving");
      setAmount("1");
    } else {
      setUnit("g");
      setAmount("100");
    }
  }

  /** Отправляет запись на сервер. */
  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!food) return;
    setError(null);
    setSaving(true);
    try {
      await createMealFromFood(userId, {
        food_id: food.id,
        ...(unit === "serving" ? { servings: Number(amount) } : { amount_g: Number(amount) }),
        eaten_at: toIsoFromLocal(`${date}T${time}`),
        meal_type: mealType as MealType,
        notes: null,
      });
      setFood(null);
      onAdded();
    } catch (err) {
      setError(getErrorText(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-4">
      <FoodPicker onSelect={handleSelect} selectedId={food?.id} />

      {food && (
        <form onSubmit={handleSubmit} className="space-y-3 rounded-xl bg-slate-50 p-4">
          <p className="font-medium">{food.name}</p>
          <div className="grid gap-3 sm:grid-cols-2">
            <SelectField
              label="Единица"
              value={unit}
              onChange={(value) => {
                setUnit(value as "g" | "serving");
                setAmount(value === "serving" ? "1" : String(Math.round(servingGrams ?? 100)));
              }}
              options={[
                ["g", "Граммы"],
                ...(canUseServings ? ([["serving", `Порции (${food.serving_name})`]] as [string, string][]) : []),
              ]}
            />
            <TextField
              label={unit === "serving" ? "Сколько порций" : "Масса, г"}
              type="number"
              min={0}
              step={unit === "serving" ? "0.5" : "1"}
              value={amount}
              onChange={setAmount}
              required
            />
            <TextField label="Время" type="time" value={time} onChange={setTime} required />
            <SelectField label="Тип" value={mealType} onChange={setMealType} options={toOptions(MEAL_TYPE_LABELS)} />
          </div>
          {preview && (
            <p className="text-sm text-slate-600">
              {formatNumber(grams, 0)} г ≈ {formatNumber(preview.calories, 0)} ккал · Б {formatNumber(preview.protein, 1)} ·
              Ж {formatNumber(preview.fat, 1)} · У {formatNumber(preview.carbs, 1)}
            </p>
          )}
          <Button type="submit" loading={saving} disabled={!preview}>
            Добавить в дневник
          </Button>
        </form>
      )}
      {error && <ErrorBanner message={error} />}
    </div>
  );
}
