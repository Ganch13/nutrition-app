"use client";

import { formatDayShort, SESSION_STATUS_LABELS } from "@/lib/format";
import type { ScheduleItem, TrainingSessionStatus } from "@/lib/types";
import { clock, hourRange, itemKey, placeInLanes, splitNested, type DaySegment } from "./layout";

// Подписи дней недели; индекс совпадает с нумерацией backend (0 — понедельник)
export const WEEKDAY_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];

// Цвет события по типу. Тренировки из раздела «Тренировки» окрашены как workout
const ITEM_STYLES: Record<string, string> = {
  work: "bg-brand-100 border-brand-300 text-brand-900",
  sleep: "bg-slate-100 border-slate-300 text-slate-700",
  meal: "bg-amber-50 border-amber-200 text-amber-800",
  workout: "bg-good-50 border-good-100 text-good-800",
  personal: "bg-brand-50 border-brand-200 text-brand-800",
  other: "bg-white border-slate-300 text-slate-700",
};

// Контейнер светлее и с пунктирной рамкой: видно, что это блок, внутри которого лежат другие события
const CONTAINER_STYLES: Record<string, string> = {
  work: "bg-brand-50/70 border-brand-300 text-brand-900",
  sleep: "bg-slate-50 border-slate-300 text-slate-700",
  meal: "bg-amber-50/60 border-amber-200 text-amber-800",
  workout: "bg-good-50/60 border-good-100 text-good-800",
  personal: "bg-brand-50/50 border-brand-200 text-brand-800",
  other: "bg-slate-50 border-slate-300 text-slate-700",
};

/** Классы оформления элемента: цвет, рамка, отметка конфликта и неактивной тренировки. */
export function itemClasses(item: ScheduleItem, conflict: boolean): string {
  const base = item.is_container
    ? `${CONTAINER_STYLES[item.category] ?? CONTAINER_STYLES.other} border-dashed`
    : (ITEM_STYLES[item.category] ?? ITEM_STYLES.other);
  const inactive = item.kind === "training" && (item.status === "skipped" || item.status === "cancelled");
  return `${base} ${conflict ? "ring-2 ring-red-500" : ""} ${inactive ? "opacity-50 line-through" : ""}`;
}

/** Подпись времени куска: "09:00–18:00", для продолжения с прошлого дня "…–07:00". */
export function segmentTime(segment: DaySegment): string {
  return `${segment.fromPrevDay ? "…" : clock(segment.start)}–${segment.toNextDay ? "…" : clock(segment.end)}`;
}

/** Подпись тренировки со статусом: «Силовая · пропущена». */
export function itemTitle(item: ScheduleItem): string {
  if (item.kind === "training" && item.status && item.status !== "planned") {
    return `${item.title} · ${SESSION_STATUS_LABELS[item.status as TrainingSessionStatus]?.toLowerCase() ?? item.status}`;
  }
  return item.title;
}

/**
 * Недельная сетка для компьютера: семь колонок от понедельника до воскресенья, вся неделя на одном экране
 * без прокрутки вниз (часы сжимаются под высоту окна). Вложенные события рисуются внутри блока контейнера.
 * Нажатие на день (заголовок или пустое место колонки) открывает форму с этой датой; нажатие на событие —
 * его изменение. selected — день, для которого открыта форма; conflictKeys — элементы с пересечениями.
 */
export function WeekGrid({
  days,
  today,
  segments,
  selected,
  conflictKeys,
  onDayClick,
  onItemClick,
}: {
  days: string[];
  today: string;
  segments: Record<string, DaySegment[]>;
  selected: string | null;
  conflictKeys: Set<string>;
  onDayClick: (day: string) => void;
  onItemClick: (item: ScheduleItem) => void;
}) {
  const [low, high] = hourRange(Object.values(segments).flat());
  const span = high - low;
  // Подписи часов: каждый час на коротком диапазоне, через час на длинном
  const step = span > 14 * 60 ? 120 : 60;
  const marks: number[] = [];
  for (let minute = low; minute <= high; minute += step) marks.push(minute);

  /** Положение по вертикали в процентах высоты колонки. */
  const topOf = (minute: number) => `${((minute - low) / span) * 100}%`;
  const heightOf = (start: number, end: number) => `${((end - start) / span) * 100}%`;

  return (
    <div className="flex h-[calc(100dvh-15rem)] min-h-[26rem] flex-col rounded-2xl border border-slate-200 bg-white">
      {/* Заголовки дней */}
      <div className="grid grid-cols-[3rem_repeat(7,minmax(0,1fr))] border-b border-slate-200">
        <span />
        {days.map((day, index) => {
          const isToday = day === today;
          const isSelected = day === selected;
          return (
            <button
              key={day}
              type="button"
              onClick={() => onDayClick(day)}
              aria-label={`Добавить событие: ${formatDayShort(day)}`}
              className={`flex flex-col items-center gap-0.5 py-2 transition hover:bg-slate-50 ${isSelected ? "bg-brand-50" : ""}`}
            >
              <span className="text-xs text-slate-500">{WEEKDAY_SHORT[index]}</span>
              <span
                className={`num flex size-8 items-center justify-center rounded-full text-sm font-semibold ${
                  isToday ? "bg-brand-700 text-white" : "text-slate-800"
                }`}
              >
                {Number(day.slice(8, 10))}
              </span>
              {isToday && <span className="size-1 rounded-full bg-saffron" aria-hidden="true" />}
            </button>
          );
        })}
      </div>

      {/* Сетка часов */}
      <div className="grid min-h-0 flex-1 grid-cols-[3rem_repeat(7,minmax(0,1fr))]">
        <div className="relative">
          {marks.map((minute) => (
            <span
              key={minute}
              className="num absolute right-2 -translate-y-1/2 text-[11px] text-slate-400"
              style={{ top: topOf(minute) }}
            >
              {minute < high ? clock(minute) : ""}
            </span>
          ))}
        </div>

        {days.map((day) => {
          const { top, children } = splitNested(segments[day] ?? []);
          return (
            <div
              key={day}
              role="button"
              tabIndex={0}
              aria-label={`Добавить событие: ${formatDayShort(day)}`}
              onClick={() => onDayClick(day)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  onDayClick(day);
                }
              }}
              className={`relative cursor-pointer border-l border-slate-100 ${day === selected ? "bg-brand-50/50" : day === today ? "bg-slate-50/60" : ""}`}
            >
              {marks.map((minute) => (
                <span key={minute} className="absolute inset-x-0 border-t border-slate-100" style={{ top: topOf(minute) }} />
              ))}

              {placeInLanes(top).map((segment) => {
                const { item } = segment;
                const key = itemKey(item.kind, item.id);
                const nested = item.kind === "event" ? (children.get(item.id) ?? []) : [];
                const blockSpan = segment.end - segment.start;
                return (
                  <div
                    key={`${key}-${day}`}
                    className="absolute px-0.5"
                    style={{
                      top: topOf(segment.start),
                      height: heightOf(segment.start, segment.end),
                      left: `${(segment.lane / segment.lanes) * 100}%`,
                      width: `${100 / segment.lanes}%`,
                    }}
                  >
                    <button
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        onItemClick(item);
                      }}
                      title={`${itemTitle(item)}, ${segmentTime(segment)}`}
                      className={`absolute inset-0 overflow-hidden rounded-lg border px-1.5 py-0.5 text-left text-[11px] leading-tight ${itemClasses(item, conflictKeys.has(key))}`}
                    >
                      <span className="block truncate font-medium">
                        {conflictKeys.has(key) && <span className="mr-0.5 text-red-600">⚠</span>}
                        {itemTitle(item)}
                      </span>
                      {blockSpan >= 45 && <span className="num block truncate opacity-75">{segmentTime(segment)}</span>}
                    </button>

                    {/* Вложенные события внутри блока: положение считается от начала и конца контейнера */}
                    {placeInLanes(nested).map((child) => {
                      const childKey = itemKey(child.item.kind, child.item.id);
                      const inner = (child.start - segment.start) / blockSpan;
                      const size = (child.end - child.start) / blockSpan;
                      return (
                        <button
                          key={`${childKey}-${day}`}
                          type="button"
                          onClick={(event) => {
                            event.stopPropagation();
                            onItemClick(child.item);
                          }}
                          title={`${itemTitle(child.item)}, ${segmentTime(child)}`}
                          className={`absolute overflow-hidden rounded-md border px-1 text-left text-[10px] leading-tight shadow-sm ${itemClasses(child.item, conflictKeys.has(childKey))}`}
                          style={{
                            top: `${inner * 100}%`,
                            height: `${size * 100}%`,
                            left: `calc(0.5rem + ${(child.lane / child.lanes) * 100}% - ${(child.lane / child.lanes) * 0.75}rem)`,
                            width: `calc(${100 / child.lanes}% - ${0.75 / child.lanes}rem)`,
                          }}
                        >
                          <span className="block truncate font-medium">
                            {conflictKeys.has(childKey) && <span className="mr-0.5 text-red-600">⚠</span>}
                            {itemTitle(child.item)}
                          </span>
                        </button>
                      );
                    })}
                  </div>
                );
              })}
            </div>
          );
        })}
      </div>
    </div>
  );
}

/**
 * Неделя на телефоне: полоса с днями сверху и события выбранного дня под ней.
 * Нажатие на день выбирает его, нажатие на событие открывает его для изменения. Вложенные события
 * показаны внутри карточки своего блока с отступом.
 */
export function WeekStrip({
  days,
  today,
  selected,
  segments,
  conflictKeys,
  onSelect,
  onItemClick,
}: {
  days: string[];
  today: string;
  selected: string;
  segments: Record<string, DaySegment[]>;
  conflictKeys: Set<string>;
  onSelect: (day: string) => void;
  onItemClick: (item: ScheduleItem) => void;
}) {
  const daySegments = segments[selected] ?? [];
  const { top, children } = splitNested(daySegments);

  /** Строка события: время, название, место. */
  const row = (segment: DaySegment, nested: boolean) => {
    const key = itemKey(segment.item.kind, segment.item.id);
    return (
      <button
        type="button"
        onClick={() => onItemClick(segment.item)}
        className={`flex w-full items-start gap-3 rounded-xl border px-3 py-2.5 text-left ${itemClasses(segment.item, conflictKeys.has(key))} ${nested ? "py-2" : ""}`}
      >
        <span className="num w-[5.5rem] shrink-0 text-xs font-medium opacity-80">{segmentTime(segment)}</span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-medium">
            {conflictKeys.has(key) && <span className="mr-1 text-red-600">⚠</span>}
            {itemTitle(segment.item)}
          </span>
          {segment.item.location && <span className="block truncate text-xs opacity-75">{segment.item.location}</span>}
        </span>
      </button>
    );
  };

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-7 gap-1 rounded-2xl border border-slate-200 bg-white p-1.5">
        {days.map((day, index) => {
          const isSelected = day === selected;
          const busy = (segments[day] ?? []).length > 0;
          return (
            <button
              key={day}
              type="button"
              onClick={() => onSelect(day)}
              aria-pressed={isSelected}
              aria-label={formatDayShort(day)}
              className={`flex flex-col items-center gap-0.5 rounded-xl py-1.5 ${isSelected ? "bg-brand-700 text-white" : "text-slate-700"}`}
            >
              <span className={`text-[11px] ${isSelected ? "text-brand-100" : "text-slate-500"}`}>{WEEKDAY_SHORT[index]}</span>
              <span className={`num text-base font-semibold ${day === today && !isSelected ? "text-brand-700" : ""}`}>
                {Number(day.slice(8, 10))}
              </span>
              {/* Точка: шафрановая — сегодня, иначе есть ли в этот день события */}
              <span
                className={`size-1 rounded-full ${
                  day === today ? "bg-saffron" : busy ? (isSelected ? "bg-white" : "bg-brand-400") : "bg-transparent"
                }`}
                aria-hidden="true"
              />
            </button>
          );
        })}
      </div>

      <div>
        <p className="mb-2 text-sm font-medium capitalize text-slate-700">{formatDayShort(selected)}</p>
        {top.length === 0 && <p className="rounded-xl bg-slate-50 px-4 py-6 text-center text-sm text-slate-500">В этот день событий нет</p>}
        <ul className="space-y-2">
          {top.map((segment) => {
            const nested = segment.item.kind === "event" ? (children.get(segment.item.id) ?? []) : [];
            return (
              <li key={itemKey(segment.item.kind, segment.item.id)}>
                {row(segment, false)}
                {nested.length > 0 && (
                  <ul className="ml-5 mt-1.5 space-y-1.5 border-l-2 border-dashed border-slate-200 pl-3">
                    {nested.map((child) => (
                      <li key={itemKey(child.item.kind, child.item.id)}>{row(child, true)}</li>
                    ))}
                  </ul>
                )}
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}
