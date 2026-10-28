"use client";

import { useCallback, useState } from "react";
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
import type { Intensity, LoadType, TrainingSession, TrainingSessionStatus, Workout } from "@/lib/types";
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
      <HomeBlockReturn block="training" />

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

      {expanded && (
        <WorkoutsPanel
          session={session}
          userId={userId}
          onCompleteSession={() => handleStatus("completed")}
        />
      )}
    </Card>
  );
}

// Длительность нового блока по умолчанию, минут
const DEFAULT_BLOCK_MINUTES = 15;

/**
 * Предлагает время нового блока: начало — конец последнего блока сессии
 * (или начало сессии, если блоков нет), длительность 15 минут, но не позже конца сессии.
 * Пример: блоки заканчиваются в 22:45, сессия до 23:30 → { start: 22:45, end: 23:00 }.
 */
function suggestBlockTimes(session: TrainingSession, workouts: Workout[] | null): { start: Date; end: Date } {
  const sessionEnd = new Date(session.end_at);
  let start = new Date(session.start_at);
  for (const workout of workouts ?? []) {
    const workoutEnd = new Date(workout.end_at);
    if (workoutEnd > start) start = workoutEnd;
  }
  const end = new Date(Math.min(start.getTime() + DEFAULT_BLOCK_MINUTES * 60_000, sessionEnd.getTime()));
  return { start, end };
}

/**
 * Блоки внутри сессии: список, кнопка «Выполнил упражнение» и форма добавления.
 * Правило времени: новый блок не может начаться раньше окончания предыдущего,
 * кроме блоков одного суперсета (их выполняют вперемежку). Проверку делает backend,
 * а форма заранее подставляет правильное время.
 */
function WorkoutsPanel({
  session,
  userId,
  onCompleteSession,
}: {
  session: TrainingSession;
  userId: number;
  onCompleteSession: () => void;
}) {
  const load = useCallback(() => getWorkouts(userId, session.id), [userId, session.id]);
  const { data: workouts, loading, error, reload } = useAsyncData(load);

  const [name, setName] = useState("");
  const [loadType, setLoadType] = useState("strength");
  const [planned, setPlanned] = useState("moderate");
  // Значения, которые пользователь изменил вручную; null — берём подсказку
  const [startInput, setStartInput] = useState<string | null>(null);
  const [endInput, setEndInput] = useState<string | null>(null);
  // id блока, с которым объединяем в суперсет ("" — не объединяем)
  const [supersetWith, setSupersetWith] = useState("");
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const suggested = suggestBlockTimes(session, workouts);
  const start = startInput ?? localInputValue(suggested.start);
  const end = endInput ?? localInputValue(suggested.end);

  /** Выбор партнёра по суперсету: время нового блока берём таким же, как у партнёра. */
  function handleSupersetChange(value: string) {
    setSupersetWith(value);
    const partner = workouts?.find((workout) => String(workout.id) === value);
    if (partner) {
      setStartInput(localInputValue(new Date(partner.start_at)));
      setEndInput(localInputValue(new Date(partner.end_at)));
    } else {
      setStartInput(null);
      setEndInput(null);
    }
  }

  /** Добавляет блок в сессию. Если время занято другим блоком, backend ответит 409 с подсказкой. */
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
        superset_with_workout_id: supersetWith === "" ? null : Number(supersetWith),
      });
      // Сбрасываем форму: следующий блок снова предложит время после только что добавленного
      setName("");
      setStartInput(null);
      setEndInput(null);
      setSupersetWith("");
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

  /**
   * Кнопка «Выполнил упражнение» (done = true) или «Снять отметку» (done = false).
   * Если фактическая интенсивность не выбрана, backend ставит плановую.
   */
  async function handleDone(workoutId: number, done: boolean) {
    setFormError(null);
    try {
      await updateWorkout(userId, session.id, workoutId, { completed: done });
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

  // Варианты для суперсета: «нет» + все блоки сессии
  const supersetOptions: [string, string][] = [
    ["", "Не объединять"],
    ...(workouts ?? []).map((workout): [string, string] => [
      String(workout.id),
      `${workout.name} (${formatTime(workout.start_at)}–${formatTime(workout.end_at)})`,
    ]),
  ];

  // Все блоки выполнены, а сама тренировка ещё «запланирована» — предлагаем закрыть её
  const allDone =
    session.status === "planned" && !!workouts && workouts.length > 0 && workouts.every((w) => w.completed_at);

  return (
    <div className="mt-4 space-y-4 border-t border-slate-100 pt-4">
      {error && <ErrorBanner message={error} onRetry={reload} />}
      {loading && workouts === null && <Loading />}
      {workouts?.length === 0 && <p className="text-sm text-slate-500">Блоков пока нет.</p>}

      {allDone && (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-good-50 px-4 py-3 text-sm text-good-700">
          <span>Все блоки выполнены. Отметить тренировку выполненной?</span>
          <Button onClick={onCompleteSession}>Тренировка выполнена</Button>
        </div>
      )}

      {workouts?.map((workout) => (
        <div
          key={workout.id}
          className={`rounded-xl p-3 ${workout.completed_at ? "bg-good-50" : "bg-slate-50"}`}
        >
          <div className="flex flex-wrap items-start justify-between gap-2">
            <p className="font-medium">{workout.name}</p>
            <div className="flex flex-wrap gap-1.5">
              {workout.superset_group !== null && <Badge tone="amber">Суперсет {workout.superset_group}</Badge>}
              {workout.completed_at && <Badge tone="green">Выполнено в {formatTime(workout.completed_at)}</Badge>}
            </div>
          </div>
          <p className="text-sm text-slate-500">
            {LOAD_TYPE_LABELS[workout.load_type]} · план: {INTENSITY_LABELS[workout.planned_intensity]} ·{" "}
            {formatTime(workout.start_at)}–{formatTime(workout.end_at)}
          </p>
          <div className="mt-2 flex flex-wrap items-end gap-3">
            <div className="w-full max-w-xs">
              <SelectField
                label="Фактическая интенсивность"
                value={workout.actual_intensity ?? ""}
                onChange={(value) => handleActual(workout.id, value)}
                options={actualOptions}
              />
            </div>
            {workout.completed_at ? (
              <Button variant="secondary" onClick={() => handleDone(workout.id, false)}>
                Снять отметку
              </Button>
            ) : (
              <Button onClick={() => handleDone(workout.id, true)}>Выполнил упражнение</Button>
            )}
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
        <TextField label="Начало" type="datetime-local" value={start} onChange={setStartInput} required />
        <TextField label="Окончание" type="datetime-local" value={end} onChange={setEndInput} required />
        {(workouts?.length ?? 0) > 0 && (
          <div className="sm:col-span-2">
            <SelectField
              label="Суперсет (выполняется вперемежку с другим блоком)"
              value={supersetWith}
              onChange={handleSupersetChange}
              options={supersetOptions}
            />
            <p className="mt-1 text-xs text-slate-500">
              Без суперсета блок не может начаться раньше окончания предыдущего: если один идёт до 22:45, следующий —
              с 22:45 или позже.
            </p>
          </div>
        )}
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
