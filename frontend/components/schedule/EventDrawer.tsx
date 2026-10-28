"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Button, ErrorBanner, IconButton, Segmented, SelectField, TextField } from "@/components/ui";
import { getErrorText } from "@/lib/api";
import { createScheduleEvent, createScheduleSeries, deleteScheduleEvent, updateScheduleEvent } from "@/lib/endpoints";
import {
  dateInZone,
  EVENT_TYPE_LABELS,
  formatDateLong,
  formatTimeInZone,
  optionalText,
  toOptions,
  zonedToIso,
} from "@/lib/format";
import type { ScheduleEventType, ScheduleItem } from "@/lib/types";
import { WEEKDAY_SHORT } from "./WeekView";

/** Что открыто в панели: новое событие на дату или существующий элемент недели. */
export type DrawerState = { mode: "create"; date: string } | { mode: "edit"; item: ScheduleItem };

// Готовые шаблоны для повторяющихся событий. Работа — блок, внутри которого бывают обед и встречи
const PRESETS: { label: string; values: Partial<SeriesState> }[] = [
  {
    label: "Рабочая неделя 9–18",
    values: { eventType: "work", title: "Работа", weekdays: [0, 1, 2, 3, 4], startTime: "09:00", endTime: "18:00", location: "Офис", isContainer: true },
  },
  {
    label: "Сон 23–07 каждый день",
    values: { eventType: "sleep", title: "Сон", weekdays: [0, 1, 2, 3, 4, 5, 6], startTime: "23:00", endTime: "07:00", location: "", isContainer: false },
  },
  {
    label: "Работа из дома пн–пт",
    values: { eventType: "work", title: "Работа (удалённо)", weekdays: [0, 1, 2, 3, 4], startTime: "09:00", endTime: "18:00", location: "Дома", isContainer: true },
  },
];

/**
 * Панель, выезжающая сбоку: добавление события на выбранный день, изменение или удаление существующего.
 * На широком экране панель стоит рядом с неделей, и неделя остаётся на виду; на узком накрывает часть экрана.
 * userId и zone — владелец и часовой пояс профиля (время вводится и показывается по нему).
 * onSaved получает дату, на которую стоит перейти (начало сохранённого события); onClose закрывает панель.
 */
export default function EventDrawer({
  state,
  userId,
  zone,
  onSaved,
  onClose,
}: {
  state: DrawerState;
  userId: number;
  zone: string;
  onSaved: (date: string) => void;
  onClose: () => void;
}) {
  const [tab, setTab] = useState<"single" | "series">("single");

  // Esc закрывает панель
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const editing = state.mode === "edit" ? state.item : null;
  const title = editing ? (editing.kind === "training" ? "Тренировка" : "Событие") : "Новое событие";
  // Ключ пересоздаёт форму при выборе другого дня или события: поля не тянутся от прошлого выбора
  const formKey = state.mode === "create" ? `create-${state.date}` : `edit-${state.item.kind}-${state.item.id}`;

  return (
    <>
      {/* Затемнение только на узком экране: на широком панель стоит рядом с неделей */}
      <button type="button" aria-label="Закрыть панель" onClick={onClose} className="fixed inset-0 z-40 bg-brand-950/30 lg:hidden" />
      <aside
        role="dialog"
        aria-label={title}
        className="lad-slide-in fixed inset-y-0 right-0 z-50 flex w-full max-w-md flex-col bg-white shadow-xl lg:sticky lg:top-6 lg:z-auto lg:h-[calc(100dvh-3rem)] lg:w-[400px] lg:max-w-none lg:shrink-0 lg:rounded-2xl lg:border lg:border-slate-200 lg:shadow-none"
      >
        <div className="flex items-start justify-between gap-3 border-b border-slate-100 px-5 py-4">
          <div className="min-w-0">
            <h2 className="text-lg font-semibold text-slate-900">{title}</h2>
            {state.mode === "create" && <p className="text-sm capitalize text-slate-500">{formatDateLong(state.date)}</p>}
          </div>
          <IconButton icon="x" label="Закрыть" onClick={onClose} />
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4" style={{ paddingBottom: "max(1rem, env(safe-area-inset-bottom))" }}>
          {state.mode === "create" && (
            <div className="mb-4">
              <Segmented
                label="Как добавить"
                value={tab}
                onChange={(value) => setTab(value as "single" | "series")}
                options={[
                  ["single", "Одно событие"],
                  ["series", "Повторять по дням"],
                ]}
              />
            </div>
          )}

          {editing?.kind === "training" ? (
            <TrainingInfo item={editing} zone={zone} />
          ) : state.mode === "create" && tab === "series" ? (
            <SeriesForm key={formKey} userId={userId} zone={zone} fromDate={state.date} onSaved={onSaved} />
          ) : (
            <EventForm
              key={formKey}
              userId={userId}
              zone={zone}
              date={state.mode === "create" ? state.date : null}
              item={editing}
              onSaved={onSaved}
              onClose={onClose}
            />
          )}
        </div>
      </aside>
    </>
  );
}

/** Тренировка из раздела «Тренировки»: здесь только смотрим, меняют её там. */
function TrainingInfo({ item, zone }: { item: ScheduleItem; zone: string }) {
  return (
    <div className="space-y-3 text-sm text-slate-700">
      <p className="font-medium text-slate-900">{item.title}</p>
      <p className="num">
        {formatDateLong(dateInZone(item.start_at, zone))}, {formatTimeInZone(item.start_at, zone)}–{formatTimeInZone(item.end_at, zone)}
      </p>
      <p className="text-slate-500">Тренировки планируются и меняются в разделе «Тренировки».</p>
      <Link href="/training" className="inline-block font-medium text-brand-700 underline underline-offset-2">
        Открыть в «Тренировки»
      </Link>
    </div>
  );
}

/** Галочка «Внутри этого блока могут быть другие события». */
function ContainerCheckbox({ checked, onChange }: { checked: boolean; onChange: (value: boolean) => void }) {
  return (
    <label className="flex items-start gap-3 text-sm text-slate-700">
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
        className="mt-0.5 size-5 shrink-0 accent-brand-700"
      />
      <span>
        Внутри этого блока могут быть другие события
        <span className="block text-xs text-slate-500">
          Например, «Работа 9–18» с обедом с 14 до 15. Вложенное событие должно целиком помещаться во время блока.
          Без этой отметки события не могут пересекаться по времени.
        </span>
      </span>
    </label>
  );
}

/**
 * Поле «дата + время» в одну строку. Поля широкие, чтобы дата и время с минутами читались целиком
 * и на телефоне: дата растягивается, время занимает не меньше 7 rem.
 */
function DateTimeRow({
  label,
  timeLabel,
  date,
  time,
  onDate,
  onTime,
  hint,
}: {
  label: string;
  // Подпись поля времени, например «Время начала»
  timeLabel: string;
  date: string;
  time: string;
  onDate: (value: string) => void;
  onTime: (value: string) => void;
  hint?: string;
}) {
  return (
    <div>
      <div className="grid grid-cols-[minmax(10.5rem,1fr)_minmax(7rem,8rem)] gap-2">
        <TextField label={label} type="date" value={date} onChange={onDate} required />
        <TextField label={timeLabel} type="time" value={time} onChange={onTime} required />
      </div>
      {hint && <p className="mt-1.5 text-xs text-slate-500">{hint}</p>}
    </div>
  );
}

/**
 * Форма одного события: создание (date задана, item нет) и изменение (item задан).
 * При создании подставляется только дата: время человек вводит сам, чтобы случайный клик
 * не создал событие с неверным временем.
 */
function EventForm({
  userId,
  zone,
  date,
  item,
  onSaved,
  onClose,
}: {
  userId: number;
  zone: string;
  date: string | null;
  item: ScheduleItem | null;
  onSaved: (date: string) => void;
  onClose: () => void;
}) {
  const [eventType, setEventType] = useState<string>(item?.category ?? "personal");
  const [title, setTitle] = useState(item?.title ?? "");
  const [startDate, setStartDate] = useState(item ? dateInZone(item.start_at, zone) : (date ?? ""));
  const [startTime, setStartTime] = useState(item ? formatTimeInZone(item.start_at, zone) : "");
  const [endDate, setEndDate] = useState(item ? dateInZone(item.end_at, zone) : (date ?? ""));
  const [endTime, setEndTime] = useState(item ? formatTimeInZone(item.end_at, zone) : "");
  const [location, setLocation] = useState(item?.location ?? "");
  const [isContainer, setIsContainer] = useState(item?.is_container ?? false);
  const [saving, setSaving] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /** Меняет дату начала; дата окончания, совпадавшая с ней, едет следом. */
  function changeStartDate(value: string) {
    if (endDate === startDate) setEndDate(value);
    setStartDate(value);
  }

  /** Проверяет поля и сохраняет событие. Ошибку пересечения сервер объясняет словами. */
  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    if (startTime === "" || endTime === "") {
      setError("Укажите время начала и окончания.");
      return;
    }
    const startAt = zonedToIso(startDate, startTime, zone);
    const endAt = zonedToIso(endDate, endTime, zone);
    if (new Date(endAt) <= new Date(startAt)) {
      setError("Окончание должно быть позже начала. Если событие заканчивается после полуночи, укажите следующий день в дате окончания.");
      return;
    }
    const data = {
      event_type: eventType as ScheduleEventType,
      title: title.trim(),
      start_at: startAt,
      end_at: endAt,
      location: optionalText(location),
      is_container: isContainer,
    };
    setSaving(true);
    try {
      if (item) await updateScheduleEvent(userId, item.id, data);
      else await createScheduleEvent(userId, { ...data, notes: null });
      onSaved(startDate);
    } catch (err) {
      setError(getErrorText(err));
    } finally {
      setSaving(false);
    }
  }

  /** Удаляет событие: только это или это и все следующие из серии. */
  async function handleDelete(scope: "one" | "following") {
    if (!item) return;
    setSaving(true);
    setError(null);
    try {
      await deleteScheduleEvent(userId, item.id, scope);
      onSaved(startDate);
    } catch (err) {
      setError(getErrorText(err));
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <TextField label="Название" value={title} onChange={setTitle} required maxLength={150} placeholder="Работа, обед, встреча" />
      <SelectField label="Тип" value={eventType} onChange={setEventType} options={toOptions(EVENT_TYPE_LABELS)} />
      <DateTimeRow label="Начало" timeLabel="Время начала" date={startDate} time={startTime} onDate={changeStartDate} onTime={setStartTime} />
      <DateTimeRow
        label="Окончание"
        timeLabel="Время окончания"
        date={endDate}
        time={endTime}
        onDate={setEndDate}
        onTime={setEndTime}
        hint={`Время по поясу профиля: ${zone}. Если событие заканчивается после полуночи, поменяйте дату окончания.`}
      />
      <TextField label="Место (необязательно)" value={location} onChange={setLocation} maxLength={200} list="schedule-places" />
      <datalist id="schedule-places">
        <option value="Офис" />
        <option value="Дома" />
        <option value="Зал" />
      </datalist>
      <ContainerCheckbox checked={isContainer} onChange={setIsContainer} />

      {error && <ErrorBanner message={error} />}

      <div className="flex flex-wrap gap-3">
        <Button type="submit" loading={saving && !confirmDelete}>
          {item ? "Сохранить" : "Добавить"}
        </Button>
        <Button variant="secondary" onClick={onClose} disabled={saving}>
          Отмена
        </Button>
        {item && !confirmDelete && (
          <Button variant="danger" onClick={() => setConfirmDelete(true)} disabled={saving}>
            Удалить
          </Button>
        )}
      </div>

      {item && confirmDelete && (
        <div className="space-y-3 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">
          <p>Удалить «{item.title}»?{item.is_container && " Вложенные события останутся."}</p>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="danger-solid" loading={saving} onClick={() => void handleDelete("one")}>
              {item.series_id ? "Только это" : "Удалить"}
            </Button>
            {item.series_id && (
              <Button size="sm" variant="danger" disabled={saving} onClick={() => void handleDelete("following")}>
                Это и следующие
              </Button>
            )}
            <Button size="sm" variant="secondary" disabled={saving} onClick={() => setConfirmDelete(false)}>
              Отмена
            </Button>
          </div>
        </div>
      )}
    </form>
  );
}

// Состояние формы серии. Время хранится строками "09:00".
type SeriesState = {
  eventType: ScheduleEventType;
  title: string;
  weekdays: number[];
  startTime: string;
  endTime: string;
  location: string;
  isContainer: boolean;
};

/**
 * Форма повторяющегося события: дни недели, время и число недель. Начинается с выбранного дня.
 * Кнопки-шаблоны заполняют поля одним нажатием.
 */
function SeriesForm({
  userId,
  zone,
  fromDate: initialFrom,
  onSaved,
}: {
  userId: number;
  zone: string;
  fromDate: string;
  onSaved: (date: string) => void;
}) {
  const [state, setState] = useState<SeriesState>({
    eventType: "work",
    title: "Работа",
    weekdays: [0, 1, 2, 3, 4],
    startTime: "09:00",
    endTime: "18:00",
    location: "Офис",
    isContainer: true,
  });
  const [fromDate, setFromDate] = useState(initialFrom);
  const [weeks, setWeeks] = useState("4");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /** Меняет часть состояния формы: patch({ title: "Сон" }). */
  function patch(values: Partial<SeriesState>) {
    setState((current) => ({ ...current, ...values }));
  }

  /** Включает или выключает день недели: toggleDay(5) добавляет субботу. */
  function toggleDay(day: number) {
    patch({
      weekdays: state.weekdays.includes(day)
        ? state.weekdays.filter((value) => value !== day)
        : [...state.weekdays, day].sort(),
    });
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    if (state.weekdays.length === 0) {
      setError("Выберите хотя бы один день недели.");
      return;
    }
    setSaving(true);
    try {
      await createScheduleSeries(userId, {
        event_type: state.eventType,
        title: state.title.trim(),
        weekdays: state.weekdays,
        start_time: state.startTime,
        end_time: state.endTime,
        from_date: fromDate,
        weeks: Number(weeks),
        location: optionalText(state.location),
        notes: null,
        is_container: state.isContainer,
      });
      onSaved(fromDate);
    } catch (err) {
      setError(getErrorText(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="flex flex-wrap gap-2">
        {PRESETS.map((preset) => (
          <Button key={preset.label} size="sm" variant="secondary" onClick={() => patch(preset.values)}>
            {preset.label}
          </Button>
        ))}
      </div>

      <TextField label="Название" value={state.title} onChange={(value) => patch({ title: value })} required maxLength={150} />
      <SelectField
        label="Тип"
        value={state.eventType}
        onChange={(value) => patch({ eventType: value as ScheduleEventType })}
        options={toOptions(EVENT_TYPE_LABELS)}
      />

      <fieldset>
        <legend className="mb-1.5 text-sm font-medium text-slate-700">Дни недели</legend>
        <div className="flex flex-wrap gap-2">
          {WEEKDAY_SHORT.map((label, day) => (
            <label
              key={label}
              className={`cursor-pointer rounded-lg border px-3 py-1.5 text-sm ${
                state.weekdays.includes(day) ? "border-brand-600 bg-brand-50 text-brand-700" : "border-slate-200 text-slate-600"
              }`}
            >
              <input type="checkbox" className="sr-only" checked={state.weekdays.includes(day)} onChange={() => toggleDay(day)} />
              {label}
            </label>
          ))}
        </div>
      </fieldset>

      <div className="grid grid-cols-2 gap-3">
        <TextField label="С" type="time" value={state.startTime} onChange={(value) => patch({ startTime: value })} required />
        <TextField label="До" type="time" value={state.endTime} onChange={(value) => patch({ endTime: value })} required />
      </div>
      <p className="-mt-2 text-xs text-slate-500">Если время окончания раньше начала, событие закончится на следующий день.</p>
      <div className="grid grid-cols-[minmax(10.5rem,1fr)_minmax(6rem,8rem)] gap-3">
        <TextField label="Начиная с даты" type="date" value={fromDate} onChange={setFromDate} required />
        <TextField label="Недель" type="number" min={1} max={26} value={weeks} onChange={setWeeks} required />
      </div>
      <TextField
        label="Место (необязательно)"
        value={state.location}
        onChange={(value) => patch({ location: value })}
        maxLength={200}
        hint={`Время считается по поясу профиля: ${zone}`}
      />
      <ContainerCheckbox checked={state.isContainer} onChange={(value) => patch({ isContainer: value })} />

      {error && <ErrorBanner message={error} />}
      <Button type="submit" loading={saving}>
        Создать серию
      </Button>
    </form>
  );
}
