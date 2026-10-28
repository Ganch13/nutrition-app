// Расчёт раскладки недельного календаря: какие куски событий попадают в какой день, какой диапазон часов
// показывать и как разложить по дорожкам события, которые всё-таки пересекаются (старые данные).
// Здесь нет React: только данные, чтобы логику было легко проверить глазами и переиспользовать.

import { dateInZone, formatTimeInZone } from "@/lib/format";
import type { ScheduleItem } from "@/lib/types";

const DAY_MINUTES = 24 * 60;

/**
 * Кусок события внутри одного дня, в минутах от полуночи по поясу профиля.
 * Сон 23:00–07:00 даёт два куска: 23:00–24:00 в первый день и 00:00–07:00 во второй.
 */
export type DaySegment = {
  item: ScheduleItem;
  day: string;
  start: number;
  end: number;
  // Событие началось в предыдущий день / продолжается в следующий
  fromPrevDay: boolean;
  toNextDay: boolean;
};

/** Минуты от полуночи момента iso в поясе zone: "2026-10-26T06:30:00Z", "Europe/Moscow" → 570 (09:30). */
function minutesOf(iso: string, zone: string): number {
  const [hours, minutes] = formatTimeInZone(iso, zone).split(":").map(Number);
  return hours * 60 + minutes;
}

/**
 * Раскладывает элементы недели по дням. days — семь дат недели ["2026-10-26", …].
 * Результат: { "2026-10-26": [кусок, …], … }, внутри дня по началу.
 */
export function segmentsByDay(items: ScheduleItem[], days: string[], zone: string): Record<string, DaySegment[]> {
  const result: Record<string, DaySegment[]> = Object.fromEntries(days.map((day) => [day, []]));
  for (const item of items) {
    const startDay = dateInZone(item.start_at, zone);
    const endDay = dateInZone(item.end_at, zone);
    for (const day of days) {
      if (day < startDay || day > endDay) continue;
      const start = day === startDay ? minutesOf(item.start_at, zone) : 0;
      const end = day === endDay ? minutesOf(item.end_at, zone) : DAY_MINUTES;
      // Событие, закончившееся ровно в полночь, в следующий день не попадает
      if (end <= start) continue;
      result[day].push({ item, day, start, end, fromPrevDay: day !== startDay, toNextDay: day !== endDay });
    }
  }
  for (const day of days) result[day].sort((a, b) => a.start - b.start || b.end - a.end);
  return result;
}

/**
 * Какие часы показывать, чтобы вся неделя поместилась на экран: от самого раннего начала до самого
 * позднего окончания, но не уже, чем 08:00–20:00. Границы округляются до часа.
 * Пример: работа 09–18 и ужин 19–20 → [480, 1200] (08:00–20:00); сон 23–07 → [0, 1440].
 */
export function hourRange(segments: DaySegment[]): [number, number] {
  let low = 8 * 60;
  let high = 20 * 60;
  for (const segment of segments) {
    low = Math.min(low, Math.floor(segment.start / 60) * 60);
    high = Math.max(high, Math.ceil(segment.end / 60) * 60);
  }
  return [low, high];
}

/** Кусок с дорожкой: lane — номер дорожки, lanes — сколько дорожек в группе пересекающихся кусков. */
export type PlacedSegment = DaySegment & { lane: number; lanes: number };

/**
 * Раскладывает куски по дорожкам: непересекающиеся занимают всю ширину, пересекающиеся встают рядом.
 * По новым правилам события не пересекаются (кроме вложенных), но старые данные и тренировки могут.
 */
export function placeInLanes(segments: DaySegment[]): PlacedSegment[] {
  const sorted = [...segments].sort((a, b) => a.start - b.start || b.end - a.end);
  const placed: PlacedSegment[] = [];
  let cluster: PlacedSegment[] = [];
  let clusterEnd = -1;
  let laneEnds: number[] = [];

  const closeCluster = () => {
    const lanes = Math.max(1, laneEnds.length);
    for (const segment of cluster) segment.lanes = lanes;
    placed.push(...cluster);
    cluster = [];
    laneEnds = [];
  };

  for (const segment of sorted) {
    if (cluster.length > 0 && segment.start >= clusterEnd) closeCluster();
    let lane = laneEnds.findIndex((end) => end <= segment.start);
    if (lane === -1) {
      lane = laneEnds.length;
      laneEnds.push(segment.end);
    } else {
      laneEnds[lane] = segment.end;
    }
    cluster.push({ ...segment, lane, lanes: 1 });
    clusterEnd = Math.max(clusterEnd, segment.end);
  }
  if (cluster.length > 0) closeCluster();
  return placed;
}

/**
 * Делит куски дня на верхний уровень и вложенные в контейнеры.
 * Результат: top — контейнеры и самостоятельные события; children — {id контейнера: [вложенные куски]}.
 * Вложенный, чей контейнер в этот день не виден, показывается на верхнем уровне.
 */
export function splitNested(segments: DaySegment[]): { top: DaySegment[]; children: Map<number, DaySegment[]> } {
  const containerIds = new Set(
    segments.filter((segment) => segment.item.kind === "event" && segment.item.is_container).map((segment) => segment.item.id),
  );
  const top: DaySegment[] = [];
  const children = new Map<number, DaySegment[]>();
  for (const segment of segments) {
    const parent = segment.item.parent_id;
    if (parent !== null && containerIds.has(parent)) {
      children.set(parent, [...(children.get(parent) ?? []), segment]);
    } else {
      top.push(segment);
    }
  }
  return { top, children };
}

/** Минуты → "09:30"; 1440 → "24:00". */
export function clock(minutes: number): string {
  return `${String(Math.floor(minutes / 60)).padStart(2, "0")}:${String(minutes % 60).padStart(2, "0")}`;
}

/** Ключ элемента для поиска конфликтов: ("event", 5) → "event:5". */
export function itemKey(kind: string, id: number): string {
  return `${kind}:${id}`;
}
