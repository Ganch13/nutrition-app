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
} from "@/components/ui";
import PeriodNav from "@/components/PeriodNav";
import { getErrorText } from "@/lib/api";
import {
  generateFamilyPlan,
  getFamilyPlanning,
  getFamilyPlanWeek,
  getHouseholds,
  setMyFamilyPlanning,
} from "@/lib/endpoints";
import {
  formatDayShort,
  formatNumber,
  formatTimeInZone,
  MEAL_LOCATION_LABELS,
  MEAL_TYPE_LABELS,
  mondayOf,
  PLANNED_STATUS_LABELS,
  PLANNED_STATUS_TONES,
  shiftDate,
  todayInZone,
} from "@/lib/format";
import { useProfile } from "@/lib/profile-context";
import type { FamilyPlanDay, FamilyPlanningState, PlanMealType } from "@/lib/types";
import { useAsyncData } from "@/lib/use-async-data";

// Какие приёмы пищи можно сделать общими (порядок как в течение дня)
const SHARED_CHOICES: PlanMealType[] = ["breakfast", "lunch", "dinner", "snack"];

const BATCH_OPTIONS: [string, string][] = [
  ["1", "Каждый день разные обеды и ужины"],
  ["2", "Повторять обед и ужин до 2 дней подряд"],
  ["3", "Повторять обед и ужин до 3 дней подряд"],
];

/** Страница «Семейное меню»: согласие на общий план, общий ужин, меню всей семьи на неделю. */
export default function FamilyMenuPage() {
  const households = useAsyncData(getHouseholds);
  // Выбранная семья; пока не выбрана вручную, показываем первую
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const list = households.data;
  const householdId = selectedId ?? list?.[0]?.id ?? null;

  return (
    <>
      <PageHeader
        title="Семейное меню"
        subtitle="Общий ужин, общий список закупок и готовка для всей семьи"
      />

      {households.error && <ErrorBanner message={households.error} onRetry={households.reload} />}
      {households.loading && list === null && <Loading />}

      {list && list.length === 0 && (
        <Card>
          <p className="text-sm text-slate-600">
            Семейное меню работает внутри домохозяйства. Создайте семью или присоединитесь по коду приглашения на странице{" "}
            <Link href="/family" className="font-medium text-brand-700 underline underline-offset-2">
              «Семья»
            </Link>
            .
          </p>
        </Card>
      )}

      {list && list.length > 1 && (
        <div className="mb-4 max-w-md">
          <SelectField
            label="Семья"
            value={String(householdId)}
            onChange={(value) => setSelectedId(Number(value))}
            options={list.map((household): [string, string] => [String(household.id), household.name])}
          />
        </div>
      )}

      {householdId !== null && <FamilyMenu key={householdId} householdId={householdId} />}
    </>
  );
}

/** Содержимое страницы для одной семьи: переключатель согласия и, если можно, меню недели. */
function FamilyMenu({ householdId }: { householdId: number }) {
  const load = useCallback(() => getFamilyPlanning(householdId), [householdId]);
  const planning = useAsyncData(load);
  const [saving, setSaving] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const state = planning.data;
  const me = state?.members.find((member) => member.is_me);

  async function handleToggle(next: boolean) {
    setSaving(true);
    setActionError(null);
    try {
      await setMyFamilyPlanning(householdId, next);
      planning.reload();
    } catch (err) {
      setActionError(getErrorText(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-4">
      {planning.error && <ErrorBanner message={planning.error} onRetry={planning.reload} />}
      {actionError && <ErrorBanner message={actionError} />}
      {planning.loading && state === null && <Loading />}

      {state && me && <ConsentCard state={state} plansTogether={me.plans_together} saving={saving} onToggle={handleToggle} />}

      {state && me?.plans_together && state.together_count < 2 && (
        <Card>
          <p className="text-sm text-slate-600">
            Вы включили «Планировать вместе». Общий план появится, как только это сделает ещё хотя бы один участник семьи
            и у него будут заполнены вес и дата рождения.
          </p>
        </Card>
      )}

      {state && me?.plans_together && state.together_count >= 2 && <FamilyWeek householdId={householdId} />}
    </div>
  );
}

/** Карточка согласия: кто планирует вместе и кнопка «включить / выключить» для себя. */
function ConsentCard({
  state,
  plansTogether,
  saving,
  onToggle,
}: {
  state: FamilyPlanningState;
  plansTogether: boolean;
  saving: boolean;
  onToggle: (next: boolean) => void;
}) {
  return (
    <Card
      title="Планировать вместе"
      action={
        <Button variant={plansTogether ? "secondary" : "primary"} loading={saving} onClick={() => onToggle(!plansTogether)}>
          {plansTogether ? "Выключить" : "Включить"}
        </Button>
      }
    >
      <ul className="mb-3 flex flex-wrap gap-2">
        {state.members.map((member) => (
          <li key={member.user_id}>
            <Badge tone={member.plans_together ? "green" : "slate"}>
              {member.name}
              {member.is_me ? " (вы)" : ""}: {member.plans_together ? "вместе" : "не включено"}
            </Badge>
          </li>
        ))}
      </ul>
      <p className="text-sm text-slate-600">
        Каждый решает за себя. Если вы включите этот режим, остальные участники, которые тоже его включили, увидят названия
        ваших блюд, время и размер порций, а ваши продукты попадут в общий список закупок. Вес, нормы и калории никому не
        показываются. У каждого остаются свои нормы, расписание и тренировки. Выключить режим можно в любой момент —
        личный план при этом не удаляется.
      </p>
    </Card>
  );
}

/** Неделя семьи: панель «Составить» и дни с меню каждого участника. */
function FamilyWeek({ householdId }: { householdId: number }) {
  const { profile } = useProfile();
  const zone = profile.timezone;
  const today = todayInZone(zone);

  const [weekStart, setWeekStart] = useState(() => mondayOf(todayInZone(profile.timezone)));
  const load = useCallback(() => getFamilyPlanWeek(householdId, weekStart), [householdId, weekStart]);
  const week = useAsyncData(load);
  const [message, setMessage] = useState<string | null>(null);

  return (
    <>
      <div className="flex flex-wrap items-center gap-2">
        <PeriodNav
          title={`${formatDayShort(weekStart)} – ${formatDayShort(shiftDate(weekStart, 6))}`}
          prevLabel="Предыдущая неделя"
          nextLabel="Следующая неделя"
          todayLabel="Эта неделя"
          onPrev={() => setWeekStart(shiftDate(weekStart, -7))}
          onNext={() => setWeekStart(shiftDate(weekStart, 7))}
          onToday={() => setWeekStart(mondayOf(today))}
          todayDisabled={weekStart === mondayOf(today)}
        />
        <span className="ml-auto flex gap-2">
          <Link
            href="/shopping"
            className="rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            Общие закупки и готовка
          </Link>
        </span>
      </div>

      {message && <SuccessNotice message={message} />}
      {week.error && <ErrorBanner message={week.error} onRetry={week.reload} />}
      {week.loading && week.data === null && <Loading />}

      <FamilyGeneratePanel
        householdId={householdId}
        weekStart={weekStart}
        today={today}
        onDone={(text) => {
          setMessage(text);
          week.reload();
        }}
      />

      {week.data?.days.map((day) => (
        <FamilyDayCard key={day.date} day={day} isToday={day.date === today} zone={zone} />
      ))}
    </>
  );
}

/** Панель «Составить семейное меню»: период, общие приёмы пищи, повторы блюд, замена готовых дней. */
function FamilyGeneratePanel({
  householdId,
  weekStart,
  today,
  onDone,
}: {
  householdId: number;
  weekStart: string;
  today: string;
  onDone: (text: string) => void;
}) {
  const todayIndex = Math.round(
    (new Date(`${today}T00:00:00Z`).getTime() - new Date(`${weekStart}T00:00:00Z`).getTime()) / 86_400_000,
  );
  const todayInWeek = todayIndex >= 0 && todayIndex <= 6;

  const [period, setPeriod] = useState<"week" | "from-today">("week");
  const [batchDays, setBatchDays] = useState("2");
  const [shared, setShared] = useState<PlanMealType[]>(["dinner"]);
  const [overwrite, setOverwrite] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);

  function toggleShared(type: PlanMealType) {
    setShared((current) => (current.includes(type) ? current.filter((item) => item !== type) : [...current, type]));
  }

  async function handleGenerate() {
    setSaving(true);
    setError(null);
    setWarnings([]);
    const fromToday = period === "from-today" && todayInWeek;
    try {
      const result = await generateFamilyPlan(householdId, {
        start: fromToday ? today : weekStart,
        days: fromToday ? 7 - todayIndex : 7,
        overwrite,
        batch_days: Number(batchDays),
        shared_meal_types: shared,
      });
      const created = result.members.map((member) => `${member.name} — ${member.created_meals}`).join(", ");
      const parts = [`Добавлено приёмов пищи: ${created}.`, `Общих приёмов пищи: ${result.shared_meals}.`];
      const skipped = result.members.reduce((sum, member) => sum + member.skipped_days.length, 0);
      if (skipped > 0) parts.push(`Дней с готовым планом пропущено: ${skipped} (включите замену, чтобы составить заново).`);
      setWarnings(result.warnings);
      onDone(parts.join(" "));
    } catch (err) {
      setError(getErrorText(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card title="Составить семейное меню">
      {error && (
        <div className="mb-3">
          <ErrorBanner message={error} />
        </div>
      )}
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

      <fieldset className="mt-3">
        <legend className="text-sm font-medium text-slate-700">Едим одно блюдо вместе</legend>
        <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1">
          {SHARED_CHOICES.map((type) => (
            <label key={type} className="flex items-center gap-2 text-sm text-slate-700">
              <input type="checkbox" checked={shared.includes(type)} onChange={() => toggleShared(type)} />
              {MEAL_TYPE_LABELS[type]}
            </label>
          ))}
        </div>
        <p className="mt-1 text-xs text-slate-500">
          Блюдо у всех одно, порции у каждого свои — под его норму. Время — по тому, кто ест позже; кто в это время на
          работе, берёт блюдо с собой отдельно.
        </p>
      </fieldset>

      <label className="mt-3 flex items-start gap-2 text-sm text-slate-700">
        <input type="checkbox" className="mt-1" checked={overwrite} onChange={(event) => setOverwrite(event.target.checked)} />
        <span>
          Заменить уже составленные дни у всех участников (съеденное и пропущенное сохранится)
        </span>
      </label>

      <div className="mt-4">
        <Button onClick={handleGenerate} loading={saving}>
          {saving ? "Составляем..." : "Составить для всех"}
        </Button>
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

/** Один день семьи: у каждого участника свой столбец с блюдами; общие блюда помечены. */
function FamilyDayCard({ day, isToday, zone }: { day: FamilyPlanDay; isToday: boolean; zone: string }) {
  return (
    <Card title={formatDayShort(day.date)} action={isToday ? <Badge tone="green">сегодня</Badge> : undefined}>
      <div className="grid gap-4 sm:grid-cols-2">
        {day.members.map((member) => (
          <section key={member.user_id}>
            <h3 className="mb-2 text-sm font-bold text-slate-700">{member.name}</h3>
            {member.meals.length === 0 && <p className="text-sm text-slate-400">Пока нет плана</p>}
            <ul className="space-y-2">
              {member.meals.map((meal) => (
                <li key={meal.id} className="rounded-xl border border-slate-200 px-3 py-2">
                  <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-slate-500">
                    <span className="font-medium text-slate-700">{formatTimeInZone(meal.planned_at, zone)}</span>
                    <span>{MEAL_TYPE_LABELS[meal.meal_type]}</span>
                    {meal.shared && <Badge tone="green">вместе</Badge>}
                    {meal.location !== "home" && <Badge tone="slate">{MEAL_LOCATION_LABELS[meal.location]}</Badge>}
                    {meal.status !== "planned" && (
                      <Badge tone={PLANNED_STATUS_TONES[meal.status]}>{PLANNED_STATUS_LABELS[meal.status]}</Badge>
                    )}
                  </div>
                  <p className="mt-1 text-sm font-medium">{meal.title}</p>
                  {Number(meal.portion_scale) !== 1 && (
                    <p className="text-xs text-slate-500">порция ×{formatNumber(meal.portion_scale, 2)}</p>
                  )}
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </Card>
  );
}
