"use client";

import Link from "next/link";
import { useCallback, useState } from "react";
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
  getGoalProgress,
  getNutritionSettings,
  getNutritionTarget,
  saveNutritionSettings,
} from "@/lib/endpoints";
import {
  ACTIVITY_LEVEL_LABELS,
  formatDateLong,
  formatKg,
  formatNumber,
  formatShortDate,
  GOAL_PROGRESS_LABELS,
  GOAL_PROGRESS_TONES,
  GOAL_TYPE_LABELS,
  optionalNumber,
  shiftDate,
  todayInZone,
  toOptions,
} from "@/lib/format";
import { useProfile } from "@/lib/profile-context";
import type { ActivityLevel, GoalProgress, NutritionTarget } from "@/lib/types";
import { useAsyncData } from "@/lib/use-async-data";

// Что именно не хватает для расчёта: код из backend → подсказка и ссылка
const MISSING_HINTS: Record<string, { text: string; href: string }> = {
  weight: { text: "Добавьте измерение веса", href: "/progress" },
  birth_date: { text: "Укажите дату рождения", href: "/profile" },
};

/** Страница «Нормы и цели»: суточная норма питания, настройки расчёта и прогресс целей. */
export default function NormsPage() {
  const { profile } = useProfile();
  const userId = profile.id;
  const today = todayInZone(profile.timezone);
  const [date, setDate] = useState(today);

  const loadTarget = useCallback(() => getNutritionTarget(userId, date), [userId, date]);
  const target = useAsyncData(loadTarget);

  const loadProgress = useCallback(() => getGoalProgress(userId), [userId]);
  const progress = useAsyncData(loadProgress);

  return (
    <>
      <PageHeader title="Нормы и цели" subtitle="Сколько есть, чтобы прийти к своей цели" />

      <div className="grid gap-6 xl:grid-cols-2">
        <div className="space-y-6">
          <div className="space-y-2">
            <PeriodNav
              prevLabel="Предыдущий день"
              nextLabel="Следующий день"
              todayLabel="Сегодня"
              onPrev={() => setDate(shiftDate(date, -1))}
              onNext={() => setDate(shiftDate(date, 1))}
              onToday={() => setDate(today)}
              todayDisabled={date === today}
            />
            <p className="text-sm font-medium capitalize text-slate-600">{formatDateLong(date)}</p>
          </div>

          <Card title="Норма на день">
            {target.error && <ErrorBanner message={target.error} onRetry={target.reload} />}
            {target.data === null && target.loading && <Loading />}
            {target.data && <TargetView target={target.data} />}
          </Card>

          <SettingsCard userId={userId} onSaved={target.reload} />
        </div>

        <div className="space-y-4">
          <h2 className="text-lg font-bold">Прогресс целей</h2>
          {progress.error && <ErrorBanner message={progress.error} onRetry={progress.reload} />}
          {progress.data === null && progress.loading && <Loading />}
          {progress.data?.length === 0 && (
            <Card>
              <p className="text-sm text-slate-500">
                Активных целей нет. Добавьте цель в разделе{" "}
                <Link href="/progress" className="font-medium text-brand-700 underline underline-offset-2">
                  «Прогресс»
                </Link>
                : норма питания будет учитывать её.
              </p>
            </Card>
          )}
          {progress.data?.map((item) => <ProgressCard key={item.goal_id} item={item} />)}
        </div>
      </div>
    </>
  );
}

/** Показ нормы: калории, БЖУ, состав расхода, предупреждения и пошаговое объяснение. */
function TargetView({ target }: { target: NutritionTarget }) {
  if (!target.ready || target.calories === null) {
    return (
      <div className="space-y-3">
        <p className="text-sm text-slate-600">Для расчёта не хватает данных:</p>
        <ul className="space-y-2">
          {target.missing.map((code) => {
            const hint = MISSING_HINTS[code];
            return (
              <li key={code}>
                <Link href={hint?.href ?? "/profile"} className="text-sm font-medium text-brand-700 underline underline-offset-2">
                  {hint?.text ?? code}
                </Link>
              </li>
            );
          })}
        </ul>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div>
        <p className="text-4xl font-bold">
          {formatNumber(target.calories, 0)}
          <span className="ml-2 text-sm font-normal text-slate-400">ккал</span>
        </p>
        <div className="mt-1 flex flex-wrap gap-2">
          {target.is_training_day ? (
            <Badge tone="green">день тренировки · {target.training_minutes} мин</Badge>
          ) : (
            <Badge>день без тренировок</Badge>
          )}
          {target.goal_type && <Badge tone="amber">{GOAL_TYPE_LABELS[target.goal_type]}</Badge>}
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3 text-sm">
        <div className="rounded-xl bg-slate-50 p-3">
          <p className="text-slate-500">Белки</p>
          <p className="mt-1 font-semibold">{target.protein_g} г</p>
        </div>
        <div className="rounded-xl bg-slate-50 p-3">
          <p className="text-slate-500">Жиры</p>
          <p className="mt-1 font-semibold">{target.fat_g} г</p>
        </div>
        <div className="rounded-xl bg-slate-50 p-3">
          <p className="text-slate-500">Углеводы</p>
          <p className="mt-1 font-semibold">{target.carbs_g} г</p>
        </div>
      </div>
      <p className="text-xs text-slate-500">
        Клетчатка от {target.fiber_g} г, вода около {target.water_ml ? formatNumber(target.water_ml / 1000, 1) : "—"} л.
      </p>

      {target.warnings.map((warning) => (
        <div key={warning} className="rounded-xl bg-amber-50 px-4 py-3 text-sm text-amber-800">
          {warning}
        </div>
      ))}

      <details className="text-sm text-slate-600">
        <summary className="cursor-pointer font-medium">Как это посчитано</summary>
        <ul className="mt-2 list-disc space-y-1 pl-5">
          {target.explanation.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
        <p className="mt-2 text-xs text-slate-500">
          Это ориентир для планирования, а не медицинская рекомендация. При заболеваниях и особых состояниях
          норму определяет врач.
        </p>
      </details>
    </div>
  );
}

/** Форма настроек: активность, число приёмов пищи, свой белок и калории. */
function SettingsCard({ userId, onSaved }: { userId: number; onSaved: () => void }) {
  const load = useCallback(() => getNutritionSettings(userId), [userId]);
  const { data: settings, loading, error, reload } = useAsyncData(load);

  return (
    <Card title="Настройки расчёта">
      {error && <ErrorBanner message={error} onRetry={reload} />}
      {settings === null && loading && <Loading />}
      {settings && (
        <SettingsForm
          userId={userId}
          initial={{
            activity: settings.activity_level,
            meals: String(settings.meals_per_day),
            protein: settings.protein_g_per_kg ? String(Number(settings.protein_g_per_kg)) : "",
            calories: settings.calorie_override ? String(settings.calorie_override) : "",
          }}
          onSaved={onSaved}
        />
      )}
    </Card>
  );
}

function SettingsForm({
  userId,
  initial,
  onSaved,
}: {
  userId: number;
  initial: { activity: ActivityLevel; meals: string; protein: string; calories: string };
  onSaved: () => void;
}) {
  const [activity, setActivity] = useState<string>(initial.activity);
  const [meals, setMeals] = useState(initial.meals);
  const [protein, setProtein] = useState(initial.protein);
  const [calories, setCalories] = useState(initial.calories);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  /** Сохраняет настройки; пустые поля белка и калорий означают «считать автоматически». */
  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSaved(false);
    setSaving(true);
    try {
      await saveNutritionSettings(userId, {
        activity_level: activity as ActivityLevel,
        meals_per_day: Number(meals),
        protein_g_per_kg: optionalNumber(protein),
        calorie_override: optionalNumber(calories),
      });
      setSaved(true);
      onSaved();
    } catch (err) {
      setError(getErrorText(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="grid gap-3 sm:grid-cols-2">
      <div className="sm:col-span-2">
        <SelectField
          label="Активность вне тренировок"
          value={activity}
          onChange={setActivity}
          options={toOptions(ACTIVITY_LEVEL_LABELS)}
        />
      </div>
      <TextField label="Приёмов пищи в день" type="number" min={3} max={6} value={meals} onChange={setMeals} required />
      <TextField
        label="Белок, г на кг веса"
        type="number"
        min={0.8}
        max={3.5}
        step="0.1"
        value={protein}
        onChange={setProtein}
        hint="Пусто — подберём по цели"
      />
      <div className="sm:col-span-2">
        <TextField
          label="Своя калорийность, ккал"
          type="number"
          min={800}
          max={6000}
          step="50"
          value={calories}
          onChange={setCalories}
          hint="Пусто — считать автоматически. Тренировки и цель тогда не учитываются"
        />
      </div>
      <div className="sm:col-span-2">
        <Button type="submit" loading={saving}>
          Сохранить
        </Button>
      </div>
      {saved && (
        <div className="sm:col-span-2">
          <SuccessNotice message="Настройки сохранены." />
        </div>
      )}
      {error && (
        <div className="sm:col-span-2">
          <ErrorBanner message={error} />
        </div>
      )}
    </form>
  );
}

/** Карточка прогресса одной цели: полоса, вес, темп и прогноз. */
function ProgressCard({ item }: { item: GoalProgress }) {
  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <p className="font-semibold">{GOAL_TYPE_LABELS[item.goal_type]}</p>
        <Badge tone={GOAL_PROGRESS_TONES[item.status]}>{GOAL_PROGRESS_LABELS[item.status]}</Badge>
      </div>

      {item.progress_percent !== null && (
        <div className="mt-3">
          <div className="h-2 overflow-hidden rounded-full bg-slate-100">
            <div className="h-full rounded-full bg-brand-600" style={{ width: `${item.progress_percent}%` }} />
          </div>
          <p className="mt-1 text-xs text-slate-500">{item.progress_percent}% пути к цели</p>
        </div>
      )}

      <dl className="mt-3 grid grid-cols-2 gap-2 text-sm">
        <div>
          <dt className="text-slate-500">Старт</dt>
          <dd className="font-medium">{formatKg(item.start_weight_kg)}</dd>
        </div>
        <div>
          <dt className="text-slate-500">Сейчас</dt>
          <dd className="font-medium">{formatKg(item.current_weight_kg)}</dd>
        </div>
        <div>
          <dt className="text-slate-500">Цель</dt>
          <dd className="font-medium">{formatKg(item.target_weight_kg)}</dd>
        </div>
        <div>
          <dt className="text-slate-500">Темп</dt>
          <dd className="font-medium">
            {item.actual_rate_kg_per_week === null
              ? "—"
              : `${formatNumber(item.actual_rate_kg_per_week, 2)} кг/нед`}
            {item.desired_rate_kg_per_week && (
              <span className="text-xs text-slate-400"> (хотите {formatNumber(item.desired_rate_kg_per_week, 2)})</span>
            )}
          </dd>
        </div>
      </dl>

      <p className="mt-3 text-sm text-slate-600">{item.message}</p>
      {item.eta_date && (
        <p className="mt-1 text-xs text-slate-500">При таком темпе цель будет достигнута около {formatShortDate(item.eta_date)}.</p>
      )}
      {item.target_date && <p className="text-xs text-slate-500">Желаемая дата: {formatShortDate(item.target_date)}.</p>}
    </Card>
  );
}
