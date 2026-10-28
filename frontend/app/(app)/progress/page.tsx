"use client";

import { useCallback, useState } from "react";
import ProgressPhotos from "@/components/ProgressPhotos";
import HomeBlockReturn from "@/components/HomeBlockReturn";
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
import {
  createGoal,
  createWeightRecord,
  deleteWeightRecord,
  getGoals,
  getWeightRecords,
  updateGoalStatus,
  deleteGoal,
} from "@/lib/endpoints";
import {
  formatKg,
  formatNumber,
  formatShortDate,
  GOAL_STATUS_LABELS,
  GOAL_STATUS_TONES,
  GOAL_TYPE_LABELS,
  optionalNumber,
  optionalText,
  todayInZone,
  toOptions,
} from "@/lib/format";
import { useProfile } from "@/lib/profile-context";
import type { GoalStatus, GoalType } from "@/lib/types";
import { useAsyncData } from "@/lib/use-async-data";

// Какие кнопки смены статуса показывать для каждого статуса цели
const GOAL_ACTIONS: Record<GoalStatus, [GoalStatus, string][]> = {
  active: [["paused", "Пауза"], ["completed", "Достигнута"], ["cancelled", "Отменить"]],
  paused: [["active", "Возобновить"], ["cancelled", "Отменить"]],
  completed: [["active", "Вернуть в активные"]],
  cancelled: [["active", "Вернуть в активные"]],
};

const PRIORITY_OPTIONS: [string, string][] = [
  ["1", "1 — самый высокий"],
  ["2", "2"],
  ["3", "3 — обычный"],
  ["4", "4"],
  ["5", "5 — самый низкий"],
];

/** Страница «Прогресс»: история веса и цели. */
export default function ProgressPage() {
  const { profile } = useProfile();
  // Сегодняшняя дата в часовом поясе профиля, например "2026-10-26"
  const today = todayInZone(profile.timezone);

  return (
    <>
      <PageHeader title="Прогресс" subtitle="Вес, цели и фото" />
      <HomeBlockReturn block="weight" />
      <div className="grid gap-6 xl:grid-cols-2">
        <WeightSection userId={profile.id} today={today} />
        <GoalsSection userId={profile.id} today={today} />
      </div>
      <h2 className="mb-3 mt-8 text-xl font-bold">Фото прогресса</h2>
      <ProgressPhotos userId={profile.id} today={today} />
    </>
  );
}

/** Блок веса: форма добавления и история с изменением относительно предыдущей записи. */
function WeightSection({ userId, today }: { userId: number; today: string }) {
  const load = useCallback(() => getWeightRecords(userId), [userId]);
  const { data: records, loading, error, reload } = useAsyncData(load);

  const [date, setDate] = useState(today);
  const [weight, setWeight] = useState("");
  const [fat, setFat] = useState("");
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  /** Добавляет запись веса и обновляет список. */
  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);
    setSaving(true);
    try {
      await createWeightRecord(userId, {
        measurement_date: date,
        weight_kg: Number(weight),
        body_fat_percent: optionalNumber(fat),
        notes: optionalText(notes),
      });
      setWeight("");
      setFat("");
      setNotes("");
      reload();
    } catch (err) {
      setFormError(getErrorText(err));
    } finally {
      setSaving(false);
    }
  }

  /** Удаляет запись после подтверждения. */
  async function handleDelete(recordId: number) {
    if (!window.confirm("Удалить запись веса?")) return;
    setFormError(null);
    try {
      await deleteWeightRecord(userId, recordId);
      reload();
    } catch (err) {
      setFormError(getErrorText(err));
    }
  }

  return (
    <Card title="Вес">
      <form onSubmit={handleSubmit} className="mb-6 grid gap-3 sm:grid-cols-2">
        <TextField label="Дата" type="date" value={date} onChange={setDate} required />
        <TextField
          label="Вес, кг"
          type="number"
          step="0.1"
          min={1}
          max={500}
          value={weight}
          onChange={setWeight}
          required
        />
        <TextField
          label="Процент жира (необязательно)"
          type="number"
          step="0.1"
          min={0}
          max={100}
          value={fat}
          onChange={setFat}
        />
        <TextField label="Заметка (необязательно)" value={notes} onChange={setNotes} />
        <div className="sm:col-span-2">
          <Button type="submit" loading={saving}>
            Добавить запись
          </Button>
        </div>
      </form>

      {formError && <ErrorBanner message={formError} />}
      {error && <ErrorBanner message={error} onRetry={reload} />}
      {loading && records === null && <Loading />}
      {records?.length === 0 && <p className="text-sm text-slate-500">Записей пока нет.</p>}

      <ul className="divide-y divide-slate-100">
        {records?.map((record, index) => {
          // Записи идут от новых к старым, поэтому предыдущая по времени — следующая в списке
          const previous = records[index + 1];
          const delta = previous ? Number(record.weight_kg) - Number(previous.weight_kg) : null;

          return (
            <li key={record.id} className="flex items-center justify-between gap-3 py-3">
              <div className="min-w-0">
                <p className="font-medium">
                  {formatKg(record.weight_kg)}
                  {delta !== null && delta !== 0 && (
                    <span className={`ml-2 text-sm ${delta > 0 ? "text-amber-600" : "text-good-600"}`}>
                      {delta > 0 ? "+" : ""}
                      {formatNumber(delta, 2)}
                    </span>
                  )}
                </p>
                <p className="truncate text-sm text-slate-500">
                  {formatShortDate(record.measurement_date)}
                  {record.body_fat_percent !== null && ` · жир ${formatNumber(record.body_fat_percent)} %`}
                  {record.notes && ` · ${record.notes}`}
                </p>
              </div>
              <Button variant="danger" onClick={() => handleDelete(record.id)}>
                Удалить
              </Button>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

/** Блок целей: список со сменой статуса и форма создания. */
function GoalsSection({ userId, today }: { userId: number; today: string }) {
  const load = useCallback(() => getGoals(userId), [userId]);
  const { data: goals, loading, error, reload } = useAsyncData(load);

  const [goalType, setGoalType] = useState("fat_loss");
  const [priority, setPriority] = useState("3");
  const [targetWeight, setTargetWeight] = useState("");
  const [targetFat, setTargetFat] = useState("");
  const [rate, setRate] = useState("");
  const [startDate, setStartDate] = useState(today);
  const [targetDate, setTargetDate] = useState("");
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  /** Создаёт цель и обновляет список. */
  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);
    setSaving(true);
    try {
      await createGoal(userId, {
        goal_type: goalType as GoalType,
        priority: Number(priority),
        target_weight_kg: optionalNumber(targetWeight),
        target_body_fat_percent: optionalNumber(targetFat),
        desired_rate_kg_per_week: optionalNumber(rate),
        start_date: startDate,
        target_date: targetDate === "" ? null : targetDate,
        notes: optionalText(notes),
      });
      setTargetWeight("");
      setTargetFat("");
      setRate("");
      setTargetDate("");
      setNotes("");
      reload();
    } catch (err) {
      setFormError(getErrorText(err));
    } finally {
      setSaving(false);
    }
  }

  /** Меняет статус цели, например active → paused. */
  async function handleStatus(goalId: number, status: GoalStatus) {
    setFormError(null);
    try {
      await updateGoalStatus(userId, goalId, status);
      reload();
    } catch (err) {
      setFormError(getErrorText(err));
    }
  }
    /** Удаляет цель навсегда после подтверждения. */
  async function handleDelete(goalId: number) {
    if (!window.confirm("Удалить цель навсегда? Это действие нельзя отменить.")) return;
    setFormError(null);
    try {
      await deleteGoal(userId, goalId);
      reload();
    } catch (err) {
      setFormError(getErrorText(err));
    }
  }

  return (
    <Card title="Цели">
      <form onSubmit={handleSubmit} className="mb-6 grid gap-3 sm:grid-cols-2">
        <SelectField label="Тип цели" value={goalType} onChange={setGoalType} options={toOptions(GOAL_TYPE_LABELS)} />
        <SelectField label="Приоритет" value={priority} onChange={setPriority} options={PRIORITY_OPTIONS} />
        <TextField
          label="Целевой вес, кг"
          type="number"
          step="0.1"
          min={1}
          value={targetWeight}
          onChange={setTargetWeight}
        />
        <TextField
          label="Целевой процент жира"
          type="number"
          step="0.1"
          min={0}
          max={100}
          value={targetFat}
          onChange={setTargetFat}
        />
        <TextField
          label="Темп, кг в неделю"
          type="number"
          step="0.05"
          min={0.05}
          max={5}
          value={rate}
          onChange={setRate}
        />
        <TextField label="Дата начала" type="date" value={startDate} onChange={setStartDate} required />
        <TextField label="Желаемая дата достижения" type="date" value={targetDate} onChange={setTargetDate} />
        <TextField label="Заметка" value={notes} onChange={setNotes} />
        <div className="sm:col-span-2">
          <Button type="submit" loading={saving}>
            Добавить цель
          </Button>
        </div>
      </form>

      {formError && <ErrorBanner message={formError} />}
      {error && <ErrorBanner message={error} onRetry={reload} />}
      {loading && goals === null && <Loading />}
      {goals?.length === 0 && <p className="text-sm text-slate-500">Целей пока нет.</p>}

      <ul className="space-y-3">
        {goals?.map((goal) => (
          <li key={goal.id} className="rounded-xl border border-slate-100 p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="font-medium">{GOAL_TYPE_LABELS[goal.goal_type]}</p>
              <Badge tone={GOAL_STATUS_TONES[goal.status]}>{GOAL_STATUS_LABELS[goal.status]}</Badge>
            </div>
            <p className="mt-2 text-sm text-slate-500">
              Приоритет {goal.priority}
              {goal.target_weight_kg !== null && ` · цель ${formatKg(goal.target_weight_kg)}`}
              {goal.target_body_fat_percent !== null &&
                ` · жир ${formatNumber(goal.target_body_fat_percent)} %`}
              {goal.desired_rate_kg_per_week !== null &&
                ` · ${formatNumber(goal.desired_rate_kg_per_week, 2)} кг/нед`}
            </p>
            <p className="text-sm text-slate-500">
              С {formatShortDate(goal.start_date)}
              {goal.target_date && ` до ${formatShortDate(goal.target_date)}`}
            </p>
            {goal.notes && <p className="mt-1 text-sm text-slate-500">{goal.notes}</p>}
            <div className="mt-3 flex flex-wrap gap-2">
              {GOAL_ACTIONS[goal.status].map(([status, label]) => (
                <Button key={status} variant="secondary" onClick={() => handleStatus(goal.id, status)}>
                  {label}
                </Button>
              ))}
              <Button variant="danger" onClick={() => handleDelete(goal.id)}>
                                  Удалить навсегда
              </Button>
            </div>
          </li>
        ))}
      </ul>
    </Card>
  );
}