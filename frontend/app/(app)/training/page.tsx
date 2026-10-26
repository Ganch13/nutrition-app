"use client";

import { useCallback, useState } from "react";
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
  createTrainingSession,
  createWorkout,
  getTrainingSessions,
  getWorkouts,
  updateTrainingSession,
  updateWorkout,
  deleteTrainingSession,
  deleteWorkout,
} from "@/lib/endpoints";
import {
  addHours,
  formatDateTime,
  formatTime,
  INTENSITY_LABELS,
  LOAD_TYPE_LABELS,
  localInputValue,
  nextFullHour,
  optionalText,
  SESSION_STATUS_LABELS,
  SESSION_STATUS_TONES,
  toIsoFromLocal,
  toOptions,
} from "@/lib/format";
import { useProfile } from "@/lib/profile-context";
import type { Intensity, LoadType, TrainingSession, TrainingSessionStatus } from "@/lib/types";
import { useAsyncData } from "@/lib/use-async-data";

/** Страница «Тренировки»: создание сессии и список сессий с блоками. */
export default function TrainingPage() {
  const { profile } = useProfile();
  const userId = profile.id;

  const load = useCallback(() => getTrainingSessions(userId), [userId]);
  const { data: sessions, loading, error, reload } = useAsyncData(load);

  // Начало по умолчанию — ближайший круглый час, конец — через час.
  // Значения полей datetime-local имеют вид "2026-10-26T17:00".
  const [name, setName] = useState("");
  const [start, setStart] = useState(() => localInputValue(nextFullHour()));
  const [end, setEnd] = useState(() => localInputValue(addHours(nextFullHour(), 1)));
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  /** Создаёт сессию (статус «Запланирована») и обновляет список. */
  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);

    if (new Date(end) <= new Date(start)) {
      setFormError("Окончание должно быть позже начала.");
      return;
    }

    setSaving(true);
    try {
      await createTrainingSession(userId, {
        name: name.trim(),
        start_at: toIsoFromLocal(start),
        end_at: toIsoFromLocal(end),
        notes: optionalText(notes),
      });
      setName("");
      setNotes("");
      reload();
    } catch (err) {
      setFormError(getErrorText(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <PageHeader title="Тренировки" subtitle="Сессии и их блоки" />

      <div className="grid gap-6 xl:grid-cols-2">
        <Card title="Новая тренировка">
          <form onSubmit={handleSubmit} className="grid gap-3 sm:grid-cols-2">
            <div className="sm:col-span-2">
              <TextField label="Название" value={name} onChange={setName} required maxLength={150} />
            </div>
            <TextField label="Начало" type="datetime-local" value={start} onChange={setStart} required />
            <TextField label="Окончание" type="datetime-local" value={end} onChange={setEnd} required />
            <div className="sm:col-span-2">
              <TextField label="Заметка (необязательно)" value={notes} onChange={setNotes} />
            </div>
            <div className="sm:col-span-2">
              <Button type="submit" loading={saving}>
                Добавить тренировку
              </Button>
            </div>
          </form>
          {formError && (
            <div className="mt-4">
              <ErrorBanner message={formError} />
            </div>
          )}
        </Card>

        <div className="space-y-4">
          {error && <ErrorBanner message={error} onRetry={reload} />}
          {loading && sessions === null && <Loading />}
          {sessions?.length === 0 && <p className="text-sm text-slate-500">Тренировок пока нет.</p>}
          {sessions?.map((session) => (
            <SessionCard key={session.id} session={session} userId={userId} onChanged={reload} />
          ))}
        </div>
      </div>
    </>
  );
}

/** Карточка сессии: статус, действия и раскрывающийся список блоков. */
function SessionCard({
  session,
  userId,
  onChanged,
}: {
  session: TrainingSession;
  userId: number;
  onChanged: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Для запланированной сессии — итоговые статусы, для остальных — возврат в план
  const actions: [TrainingSessionStatus, string][] =
    session.status === "planned"
      ? [["completed", "Выполнена"], ["skipped", "Пропущена"], ["cancelled", "Отменить"]]
      : [["planned", "Вернуть в план"]];

  /** Меняет статус сессии (PATCH) и просит страницу обновить список. */
  async function handleStatus(status: TrainingSessionStatus) {
    setError(null);
    try {
      await updateTrainingSession(userId, session.id, { status });
      onChanged();
    } catch (err) {
      setError(getErrorText(err));
    }
  }
    /** Удаляет сессию вместе со всеми её блоками после подтверждения. */
  async function handleDelete() {
    if (!window.confirm("Удалить тренировку вместе со всеми блоками? Это действие нельзя отменить.")) {
      return;
    }
    setError(null);
    try {
      await deleteTrainingSession(userId, session.id);
      onChanged();
    } catch (err) {
      setError(getErrorText(err));
    }
  }

  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="font-semibold">{session.name}</p>
          <p className="text-sm text-slate-500">
            {formatDateTime(session.start_at)} – {formatTime(session.end_at)}
          </p>
        </div>
        <Badge tone={SESSION_STATUS_TONES[session.status]}>{SESSION_STATUS_LABELS[session.status]}</Badge>
      </div>

      {session.notes && <p className="mt-2 text-sm text-slate-500">{session.notes}</p>}
      {error && (
        <div className="mt-3">
          <ErrorBanner message={error} />
        </div>
      )}

      <div className="mt-3 flex flex-wrap gap-2">
        {actions.map(([status, label]) => (
          <Button key={status} variant="secondary" onClick={() => handleStatus(status)}>
            {label}
          </Button>
        ))}
        <Button variant="secondary" onClick={() => setExpanded(!expanded)}>
          {expanded ? "Скрыть блоки" : "Блоки"}
        </Button>
        <Button variant="danger" onClick={handleDelete}>
          Удалить
        </Button>
      </div>

      {expanded && <WorkoutsPanel session={session} userId={userId} />}
    </Card>
  );
}

/** Блоки внутри сессии: список с фактической интенсивностью и форма добавления. */
function WorkoutsPanel({ session, userId }: { session: TrainingSession; userId: number }) {
  const load = useCallback(() => getWorkouts(userId, session.id), [userId, session.id]);
  const { data: workouts, loading, error, reload } = useAsyncData(load);

  // Время блока по умолчанию совпадает со временем сессии (блок обязан лежать внутри неё)
  const [name, setName] = useState("");
  const [loadType, setLoadType] = useState("strength");
  const [planned, setPlanned] = useState("moderate");
  const [start, setStart] = useState(() => localInputValue(new Date(session.start_at)));
  const [end, setEnd] = useState(() => localInputValue(new Date(session.end_at)));
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  /** Добавляет блок в сессию. Сервер проверяет, что время внутри сессии. */
  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);

    if (new Date(end) <= new Date(start)) {
      setFormError("Окончание должно быть позже начала.");
      return;
    }

    setSaving(true);
    try {
      await createWorkout(userId, session.id, {
        name: name.trim(),
        load_type: loadType as LoadType,
        planned_intensity: planned as Intensity,
        start_at: toIsoFromLocal(start),
        end_at: toIsoFromLocal(end),
        notes: null,
      });
      setName("");
      reload();
    } catch (err) {
      setFormError(getErrorText(err));
    } finally {
      setSaving(false);
    }
  }

  /** Сохраняет фактическую интенсивность блока; пустое значение очищает её. */
  async function handleActual(workoutId: number, value: string) {
    setFormError(null);
    try {
      await updateWorkout(userId, session.id, workoutId, {
        actual_intensity: value === "" ? null : (value as Intensity),
      });
      reload();
    } catch (err) {
      setFormError(getErrorText(err));
    }
  }
    /** Удаляет один блок после подтверждения. */
  async function handleDeleteWorkout(workoutId: number) {
    if (!window.confirm("Удалить блок?")) return;
    setFormError(null);
    try {
      await deleteWorkout(userId, session.id, workoutId);
      reload();
    } catch (err) {
      setFormError(getErrorText(err));
    }
  }

  // Варианты фактической интенсивности: «не указана» + три уровня
  const actualOptions: [string, string][] = [["", "Не указана"], ...toOptions(INTENSITY_LABELS)];

  return (
    <div className="mt-4 space-y-4 border-t border-slate-100 pt-4">
      {error && <ErrorBanner message={error} onRetry={reload} />}
      {loading && workouts === null && <Loading />}
      {workouts?.length === 0 && <p className="text-sm text-slate-500">Блоков пока нет.</p>}

      {workouts?.map((workout) => (
        <div key={workout.id} className="rounded-xl bg-slate-50 p-3">
          <p className="font-medium">{workout.name}</p>
          <p className="text-sm text-slate-500">
            {LOAD_TYPE_LABELS[workout.load_type]} · план: {INTENSITY_LABELS[workout.planned_intensity]} ·{" "}
            {formatTime(workout.start_at)}–{formatTime(workout.end_at)}
          </p>
          <div className="mt-2 max-w-xs">
            <SelectField
              label="Фактическая интенсивность"
              value={workout.actual_intensity ?? ""}
              onChange={(value) => handleActual(workout.id, value)}
              options={actualOptions}
            />
          </div>
          <div className="mt-2">
            <Button variant="danger" onClick={() => handleDeleteWorkout(workout.id)}>
              Удалить блок
            </Button>
          </div>
        </div>
      ))}

      <form onSubmit={handleSubmit} className="grid gap-3 sm:grid-cols-2">
        <div className="sm:col-span-2">
          <TextField label="Новый блок: название" value={name} onChange={setName} required maxLength={150} />
        </div>
        <SelectField label="Тип нагрузки" value={loadType} onChange={setLoadType} options={toOptions(LOAD_TYPE_LABELS)} />
        <SelectField
          label="Планируемая интенсивность"
          value={planned}
          onChange={setPlanned}
          options={toOptions(INTENSITY_LABELS)}
        />
        <TextField label="Начало" type="datetime-local" value={start} onChange={setStart} required />
        <TextField label="Окончание" type="datetime-local" value={end} onChange={setEnd} required />
        <div className="sm:col-span-2">
          <Button type="submit" loading={saving}>
            Добавить блок
          </Button>
        </div>
      </form>
      {formError && <ErrorBanner message={formError} />}
    </div>
  );
}