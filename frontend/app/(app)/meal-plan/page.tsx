"use client";

import Link from "next/link";
import { useCallback, useState } from "react";
import FoodPicker, { foodSummaryLine } from "@/components/FoodPicker";
import RecipePicker, { recipeSummaryLine } from "@/components/RecipePicker";
import {
  Badge,
  Button,
  Card,
  ErrorBanner,
  Loading,
  PageHeader,
  SelectField,
  SuccessNotice,
  TextField,
} from "@/components/ui";
import PeriodNav from "@/components/PeriodNav";
import { getErrorText } from "@/lib/api";
import {
  createPlannedMeal,
  deletePlannedMeal,
  eatPlannedMeal,
  generateMealPlan,
  getMealPlanWeek,
  resetPlannedMeal,
  skipPlannedMeal,
  updatePlannedMeal,
} from "@/lib/endpoints";
import {
  formatDayShort,
  formatKcal,
  formatNumber,
  formatTimeInZone,
  MEAL_LOCATION_LABELS,
  MEAL_TYPE_LABELS,
  mondayOf,
  PLANNED_STATUS_LABELS,
  PLANNED_STATUS_TONES,
  shiftDate,
  todayInZone,
  toOptions,
  zonedToIso,
} from "@/lib/format";
import { useProfile } from "@/lib/profile-context";
import type {
  Food,
  MealLocation,
  MealPlanDay,
  PlannedMeal,
  PlanMealType,
  Recipe,
} from "@/lib/types";
import { useAsyncData } from "@/lib/use-async-data";

// Типы приёмов пищи, доступные в плане (в дневнике есть ещё «Другое»)
const PLAN_MEAL_LABELS: Record<PlanMealType, string> = {
  breakfast: MEAL_TYPE_LABELS.breakfast,
  lunch: MEAL_TYPE_LABELS.lunch,
  dinner: MEAL_TYPE_LABELS.dinner,
  snack: MEAL_TYPE_LABELS.snack,
};

// Время по умолчанию для вручную добавляемого приёма пищи
const DEFAULT_TIME: Record<PlanMealType, string> = {
  breakfast: "08:00",
  lunch: "13:00",
  snack: "16:00",
  dinner: "19:30",
};

const BATCH_OPTIONS: [string, string][] = [
  ["1", "Каждый день разные обеды и ужины"],
  ["2", "Повторять обед и ужин до 2 дней подряд"],
  ["3", "Повторять обед и ужин до 3 дней подряд"],
];

/** Размер порции после замены блюда: подбирается так, чтобы калорийность осталась прежней (0,5–2 порции). */
function scaleForSameCalories(oldKcal: string, recipe: Recipe): number {
  const raw = Number(oldKcal) / Number(recipe.calories);
  const stepped = Math.round(raw / 0.05) * 0.05;
  return Math.round(Math.min(2, Math.max(0.5, stepped)) * 100) / 100;
}

/** Страница «Меню»: план питания на неделю, автосоставление, отметки «съел / пропустил». */
export default function MealPlanPage() {
  const { profile } = useProfile();
  const userId = profile.id;
  const zone = profile.timezone;
  const today = todayInZone(zone);

  // Понедельник показываемой недели, например "2026-10-26"
  const [weekStart, setWeekStart] = useState(() => mondayOf(todayInZone(profile.timezone)));
  const load = useCallback(() => getMealPlanWeek(userId, weekStart), [userId, weekStart]);
  const { data: week, loading, error, reload } = useAsyncData(load);

  const [message, setMessage] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const weekEnd = shiftDate(weekStart, 6);

  return (
    <>
      <PageHeader
        title="Меню на неделю"
        subtitle="План питания с учётом нормы, расписания и тренировок"
      />

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <PeriodNav
          title={`${formatDayShort(weekStart)} – ${formatDayShort(weekEnd)}`}
          prevLabel="Предыдущая неделя"
          nextLabel="Следующая неделя"
          todayLabel="Эта неделя"
          onPrev={() => setWeekStart(shiftDate(weekStart, -7))}
          onNext={() => setWeekStart(shiftDate(weekStart, 7))}
          onToday={() => setWeekStart(mondayOf(today))}
          todayDisabled={weekStart === mondayOf(today)}
        />
        <span className="ml-auto flex gap-2">
          <Link href="/shopping" className="rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50">
            Закупки и готовка
          </Link>
          <Link href="/recipes" className="rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50">
            Рецепты
          </Link>
        </span>
      </div>

      <div className="space-y-4">
        {message && <SuccessNotice message={message} />}
        {actionError && <ErrorBanner message={actionError} />}
        {error && <ErrorBanner message={error} onRetry={reload} />}
        {loading && week === null && <Loading />}

        {week && !week.target_ready && (
          <div className="rounded-xl bg-amber-50 px-4 py-3 text-sm text-amber-800">
            <p className="font-medium">Автосоставление пока недоступно: не хватает данных для нормы питания.</p>
            <ul className="mt-1 list-disc pl-5">
              {week.warnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
            <p className="mt-2">
              <Link href="/progress" className="font-medium underline">Добавить вес</Link>
              {" · "}
              <Link href="/profile" className="font-medium underline">Открыть профиль</Link>
            </p>
          </div>
        )}

        {week && (
          <GeneratePanel
            userId={userId}
            weekStart={weekStart}
            today={today}
            disabled={!week.target_ready}
            onDone={(text) => {
              setActionError(null);
              setMessage(text);
              reload();
            }}
            onError={(text) => {
              setMessage(null);
              setActionError(text);
            }}
          />
        )}

        {week?.days.map((day) => (
          <DayCard
            key={day.date}
            day={day}
            isToday={day.date === today}
            userId={userId}
            zone={zone}
            onChanged={() => {
              setMessage(null);
              setActionError(null);
              reload();
            }}
            onError={(text) => {
              setMessage(null);
              setActionError(text);
            }}
          />
        ))}
      </div>
    </>
  );
}

/** Панель «Составить план»: период, повторы блюд, замена уже составленных дней. */
function GeneratePanel({
  userId,
  weekStart,
  today,
  disabled,
  onDone,
  onError,
}: {
  userId: number;
  weekStart: string;
  today: string;
  disabled: boolean;
  onDone: (text: string) => void;
  onError: (text: string) => void;
}) {
  // Сколько дней недели осталось с сегодняшнего (если сегодня внутри показанной недели)
  const todayIndex = Math.round(
    (new Date(`${today}T00:00:00Z`).getTime() - new Date(`${weekStart}T00:00:00Z`).getTime()) / 86_400_000,
  );
  const todayInWeek = todayIndex >= 0 && todayIndex <= 6;

  const [period, setPeriod] = useState<"week" | "from-today">("week");
  const [batchDays, setBatchDays] = useState("2");
  const [overwrite, setOverwrite] = useState(false);
  const [saving, setSaving] = useState(false);
  const [warnings, setWarnings] = useState<string[]>([]);

  async function handleGenerate() {
    setSaving(true);
    setWarnings([]);
    const fromToday = period === "from-today" && todayInWeek;
    try {
      const result = await generateMealPlan(userId, {
        start: fromToday ? today : weekStart,
        days: fromToday ? 7 - todayIndex : 7,
        overwrite,
        batch_days: Number(batchDays),
      });
      const parts = [`Добавлено приёмов пищи: ${result.created_meals}.`];
      if (result.replaced_meals > 0) parts.push(`Заменено: ${result.replaced_meals}.`);
      if (result.skipped_days.length > 0) {
        parts.push(`Дней с готовым планом пропущено: ${result.skipped_days.length} (включите замену, чтобы составить заново).`);
      }
      setWarnings(result.warnings);
      onDone(parts.join(" "));
    } catch (err) {
      onError(getErrorText(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card title="Составить план автоматически">
      <div className="grid gap-3 sm:grid-cols-2">
        <SelectField
          label="Период"
          value={period}
          onChange={(value) => setPeriod(value as "week" | "from-today")}
          options={[
            ["week", "Вся неделя"],
            ...(todayInWeek ? ([["from-today", "С сегодняшнего дня до конца недели"]] as [string, string][]) : []),
          ]}
        />
        <SelectField label="Повторы блюд" value={batchDays} onChange={setBatchDays} options={BATCH_OPTIONS} />
      </div>
      <label className="mt-3 flex items-center gap-2 text-sm text-slate-700">
        <input type="checkbox" checked={overwrite} onChange={(event) => setOverwrite(event.target.checked)} />
        Заменить уже составленные дни (съеденное и пропущенное сохранится)
      </label>
      <div className="mt-4 flex flex-wrap items-center gap-3">
        <Button onClick={handleGenerate} loading={saving} disabled={disabled}>
          {saving ? "Составляем..." : "Составить план"}
        </Button>
        <p className="text-xs text-slate-500">
          Количество приёмов пищи и активность настраиваются в разделе{" "}
          <Link href="/norms" className="underline">«Нормы и цели»</Link>.
        </p>
      </div>
      {warnings.length > 0 && (
        <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-amber-800">
          {warnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      )}
    </Card>
  );
}

/** Карточка одного дня: норма и сумма плана, приёмы пищи, добавление вручную. */
function DayCard({
  day,
  isToday,
  userId,
  zone,
  onChanged,
  onError,
}: {
  day: MealPlanDay;
  isToday: boolean;
  userId: number;
  zone: string;
  onChanged: () => void;
  onError: (text: string) => void;
}) {
  const [adding, setAdding] = useState(false);
  const { target } = day;
  const planned = Number(day.planned_calories);
  const percent = target.calories ? Math.round((planned / target.calories) * 100) : 0;

  return (
    <section
      className={`rounded-2xl border bg-white p-5 sm:p-6 ${isToday ? "border-brand-600 ring-1 ring-brand-100" : "border-slate-200"}`}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-lg font-bold capitalize">{formatDayShort(day.date)}</h2>
          {isToday && <Badge tone="green">сегодня</Badge>}
          {target.is_training_day && <Badge tone="amber">тренировка · {target.training_minutes} мин</Badge>}
        </div>
        {target.ready && target.calories !== null && (
          <p className="text-sm text-slate-600">
            <span className="font-semibold text-slate-900">{formatNumber(planned, 0)}</span> / {target.calories} ккал
          </p>
        )}
      </div>

      {target.ready && target.calories !== null && (
        <>
          <div className="mt-2 h-2 overflow-hidden rounded-full bg-slate-100" aria-hidden="true">
            <div
              className={`h-full rounded-full ${percent > 110 ? "bg-amber-500" : "bg-good-500"}`}
              style={{ width: `${Math.min(100, percent)}%` }}
            />
          </div>
          <p className="mt-1.5 text-xs text-slate-500">
            Белки {formatNumber(day.planned_protein_g, 0)} / {target.protein_g} г · Жиры{" "}
            {formatNumber(day.planned_fat_g, 0)} / {target.fat_g} г · Углеводы {formatNumber(day.planned_carbs_g, 0)} /{" "}
            {target.carbs_g} г
          </p>
        </>
      )}
      {day.warnings.map((warning) => (
        <p key={warning} className="mt-2 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800">
          {warning}
        </p>
      ))}

      {day.meals.length === 0 ? (
        <p className="mt-4 text-sm text-slate-500">На этот день ничего не запланировано.</p>
      ) : (
        <ul className="mt-4 divide-y divide-slate-100">
          {day.meals.map((meal) => (
            <MealRow key={meal.id} meal={meal} userId={userId} zone={zone} onChanged={onChanged} onError={onError} />
          ))}
        </ul>
      )}

      <div className="mt-4">
        {adding ? (
          <AddMealPanel
            date={day.date}
            userId={userId}
            zone={zone}
            onAdded={() => {
              setAdding(false);
              onChanged();
            }}
            onCancel={() => setAdding(false)}
            onError={onError}
          />
        ) : (
          <Button variant="secondary" onClick={() => setAdding(true)}>
            + Добавить приём пищи
          </Button>
        )}
      </div>
    </section>
  );
}

/** Строка приёма пищи с кнопками «Съел», «Пропустить», «Изменить», «Удалить». */
function MealRow({
  meal,
  userId,
  zone,
  onChanged,
  onError,
}: {
  meal: PlannedMeal;
  userId: number;
  zone: string;
  onChanged: () => void;
  onError: (text: string) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(false);

  /** Выполняет запрос, блокируя кнопки, и обновляет страницу; ошибку показывает вверху. */
  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    try {
      await action();
      setEditing(false);
      onChanged();
    } catch (err) {
      onError(getErrorText(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete() {
    if (!window.confirm(`Убрать «${meal.title}» из плана?`)) return;
    await run(() => deletePlannedMeal(userId, meal.id));
  }

  const dimmed = meal.status === "skipped";
  const scale = Number(meal.portion_scale);

  return (
    <li className="py-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className={`min-w-0 ${dimmed ? "opacity-60" : ""}`}>
          <p className="text-xs text-slate-500">
            {formatTimeInZone(meal.planned_at, zone)} · {PLAN_MEAL_LABELS[meal.meal_type]}
          </p>
          <p className="font-medium">{meal.title}</p>
          <p className="text-xs text-slate-500">
            {formatKcal(meal.calories)} · Б {formatNumber(meal.protein_g, 0)} · Ж {formatNumber(meal.fat_g, 0)} · У{" "}
            {formatNumber(meal.carbs_g, 0)}
            {meal.recipe_id !== null && scale !== 1 && ` · порция ×${formatNumber(scale, 2)}`}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {meal.location !== "home" && <Badge tone={meal.location === "work" ? "amber" : "slate"}>{MEAL_LOCATION_LABELS[meal.location]}</Badge>}
          {meal.status !== "planned" && <Badge tone={PLANNED_STATUS_TONES[meal.status]}>{PLANNED_STATUS_LABELS[meal.status]}</Badge>}
        </div>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
        {meal.status !== "eaten" && (
          <Button loading={busy} onClick={() => run(() => eatPlannedMeal(userId, meal.id))}>
            Съел
          </Button>
        )}
        {meal.status === "planned" && (
          <Button variant="secondary" loading={busy} onClick={() => run(() => skipPlannedMeal(userId, meal.id))}>
            Пропустить
          </Button>
        )}
        {meal.status !== "planned" && (
          <Button variant="secondary" loading={busy} onClick={() => run(() => resetPlannedMeal(userId, meal.id))}>
            Вернуть в план
          </Button>
        )}
        {meal.status === "planned" && (
          <Button variant="secondary" onClick={() => setEditing(!editing)}>
            {editing ? "Закрыть" : "Изменить"}
          </Button>
        )}
        <button type="button" onClick={() => setOpen(!open)} className="text-xs text-slate-500 underline">
          {open ? "Скрыть состав" : "Состав"}
        </button>
        <button type="button" onClick={handleDelete} disabled={busy} className="ml-auto text-xs text-red-600 underline disabled:opacity-60">
          Убрать
        </button>
      </div>

      {open && (
        <ul className="mt-2 space-y-0.5 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-600">
          {meal.items.map((item, index) => (
            <li key={`${item.name}-${index}`} className="flex justify-between gap-3">
              <span>{item.name}</span>
              <span className="shrink-0">
                {formatNumber(item.amount_g, 0)} г · {formatKcal(item.calories)}
              </span>
            </li>
          ))}
        </ul>
      )}

      {editing && (
        <EditMealPanel meal={meal} zone={zone} busy={busy} onSave={(changes) => run(() => updatePlannedMeal(userId, meal.id, changes))} />
      )}
    </li>
  );
}

/** Форма изменения: день, время, тип, место, размер порции и замена блюда. */
function EditMealPanel({
  meal,
  zone,
  busy,
  onSave,
}: {
  meal: PlannedMeal;
  zone: string;
  busy: boolean;
  onSave: (changes: Parameters<typeof updatePlannedMeal>[2]) => void;
}) {
  const [date, setDate] = useState(meal.plan_date);
  const [time, setTime] = useState(formatTimeInZone(meal.planned_at, zone));
  const [mealType, setMealType] = useState<PlanMealType>(meal.meal_type);
  const [location, setLocation] = useState<MealLocation>(meal.location);
  const [scale, setScale] = useState(String(Number(meal.portion_scale)));
  const [replacing, setReplacing] = useState(false);

  const originalTime = formatTimeInZone(meal.planned_at, zone);
  const scaleNumber = Number(scale);
  const scaleValid = Number.isFinite(scaleNumber) && scaleNumber >= 0.25 && scaleNumber <= 5;

  function handleSave() {
    const changes: Parameters<typeof updatePlannedMeal>[2] = {};
    if (date !== meal.plan_date || time !== originalTime) changes.planned_at = zonedToIso(date, time, zone);
    if (mealType !== meal.meal_type) changes.meal_type = mealType;
    if (location !== meal.location) changes.location = location;
    if (scaleNumber !== Number(meal.portion_scale)) changes.portion_scale = scaleNumber;
    onSave(changes);
  }

  return (
    <div className="mt-3 space-y-3 rounded-xl border border-slate-200 bg-slate-50 p-3">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <TextField label="День" type="date" value={date} onChange={setDate} />
        <TextField label="Время" type="time" value={time} onChange={setTime} />
        <SelectField label="Приём пищи" value={mealType} onChange={(v) => setMealType(v as PlanMealType)} options={toOptions(PLAN_MEAL_LABELS)} />
        <SelectField label="Где" value={location} onChange={(v) => setLocation(v as MealLocation)} options={toOptions(MEAL_LOCATION_LABELS)} />
        <TextField
          label="Порция (×)"
          type="number"
          step="0.05"
          min="0.25"
          max="5"
          value={scale}
          onChange={setScale}
          hint={meal.recipe_id === null ? "Состав изменится пропорционально" : undefined}
        />
      </div>
      <div className="flex flex-wrap gap-2">
        <Button loading={busy} disabled={!scaleValid || !date || !time} onClick={handleSave}>
          Сохранить
        </Button>
        <Button variant="secondary" onClick={() => setReplacing(!replacing)}>
          {replacing ? "Не заменять блюдо" : "Заменить блюдо"}
        </Button>
      </div>
      {replacing && (
        <RecipePicker
          mealType={mealType}
          portableOnly={location === "work"}
          selectedId={meal.recipe_id}
          onSelect={(recipe) =>
            onSave({ recipe_id: recipe.id, portion_scale: scaleForSameCalories(meal.calories, recipe) })
          }
        />
      )}
      {!scaleValid && <p className="text-xs text-red-600">Размер порции: от 0,25 до 5.</p>}
    </div>
  );
}

/** Форма добавления приёма пищи вручную: рецепт или продукт с массой. */
function AddMealPanel({
  date,
  userId,
  zone,
  onAdded,
  onCancel,
  onError,
}: {
  date: string;
  userId: number;
  zone: string;
  onAdded: () => void;
  onCancel: () => void;
  onError: (text: string) => void;
}) {
  const [mealType, setMealType] = useState<PlanMealType>("lunch");
  const [time, setTime] = useState(DEFAULT_TIME.lunch);
  const [location, setLocation] = useState<MealLocation>("home");
  const [mode, setMode] = useState<"recipe" | "food">("recipe");
  const [recipe, setRecipe] = useState<Recipe | null>(null);
  const [scale, setScale] = useState("1");
  const [food, setFood] = useState<Food | null>(null);
  const [grams, setGrams] = useState("100");
  const [saving, setSaving] = useState(false);

  function changeMealType(value: string) {
    setMealType(value as PlanMealType);
    setTime(DEFAULT_TIME[value as PlanMealType]);
  }

  const scaleNumber = Number(scale);
  const gramsNumber = Number(grams);
  const ready =
    time !== "" &&
    (mode === "recipe"
      ? recipe !== null && scaleNumber >= 0.25 && scaleNumber <= 5
      : food !== null && gramsNumber > 0 && gramsNumber <= 5000);

  async function handleSubmit() {
    setSaving(true);
    const plannedAt = zonedToIso(date, time, zone);
    try {
      if (mode === "recipe" && recipe) {
        await createPlannedMeal(userId, {
          planned_at: plannedAt,
          meal_type: mealType,
          location,
          recipe_id: recipe.id,
          portion_scale: scaleNumber,
        });
      } else if (food) {
        await createPlannedMeal(userId, {
          planned_at: plannedAt,
          meal_type: mealType,
          location,
          items: [{ food_id: food.id, amount_g: gramsNumber }],
        });
      }
      onAdded();
    } catch (err) {
      onError(getErrorText(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-3 rounded-xl border border-slate-200 bg-slate-50 p-3">
      <div className="grid gap-3 sm:grid-cols-3">
        <SelectField label="Приём пищи" value={mealType} onChange={changeMealType} options={toOptions(PLAN_MEAL_LABELS)} />
        <TextField label="Время" type="time" value={time} onChange={setTime} />
        <SelectField label="Где" value={location} onChange={(v) => setLocation(v as MealLocation)} options={toOptions(MEAL_LOCATION_LABELS)} />
      </div>

      <div className="flex gap-2">
        <Button variant={mode === "recipe" ? "primary" : "secondary"} onClick={() => setMode("recipe")}>
          Из рецепта
        </Button>
        <Button variant={mode === "food" ? "primary" : "secondary"} onClick={() => setMode("food")}>
          Из продукта
        </Button>
      </div>

      {mode === "recipe" ? (
        <>
          <RecipePicker mealType={mealType} portableOnly={location === "work"} selectedId={recipe?.id} onSelect={setRecipe} />
          {recipe && (
            <div className="grid items-end gap-3 sm:grid-cols-2">
              <p className="text-sm">
                <span className="font-medium">{recipe.name}</span>
                <span className="block text-xs text-slate-500">{recipeSummaryLine(recipe)} на порцию</span>
              </p>
              <TextField label="Порция (×)" type="number" step="0.05" min="0.25" max="5" value={scale} onChange={setScale} />
            </div>
          )}
        </>
      ) : (
        <>
          <FoodPicker selectedId={food?.id} onSelect={setFood} />
          {food && (
            <div className="grid items-end gap-3 sm:grid-cols-2">
              <p className="text-sm">
                <span className="font-medium">{food.name}</span>
                <span className="block text-xs text-slate-500">{foodSummaryLine(food)}</span>
              </p>
              <TextField label="Масса, г" type="number" min="1" max="5000" value={grams} onChange={setGrams} />
            </div>
          )}
        </>
      )}

      <div className="flex gap-2">
        <Button loading={saving} disabled={!ready} onClick={handleSubmit}>
          Добавить
        </Button>
        <Button variant="secondary" onClick={onCancel}>
          Отмена
        </Button>
      </div>
    </div>
  );
}
