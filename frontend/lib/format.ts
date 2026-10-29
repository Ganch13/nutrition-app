import type { Tone } from "@/components/ui";
import type {
  GoalStatus,
  GoalType,
  Intensity,
  LoadType,
  MealType,
  ScheduleEventType,
  TrainingSessionStatus,
  FinanceKind,
  FoodCategory,
  ActivityLevel,
  GoalProgressStatus,
  MealLocation,
  PlannedMealStatus,
  PhotoAngle,
} from "./types";

// ---------- Подписи для значений, которые приходят с backend ----------

export const MEAL_TYPE_LABELS: Record<MealType, string> = {
  breakfast: "Завтрак",
  lunch: "Обед",
  dinner: "Ужин",
  snack: "Перекус",
  other: "Другое",
};

export const GOAL_TYPE_LABELS: Record<GoalType, string> = {
  fat_loss: "Снижение жира",
  muscle_gain: "Набор мышц",
  weight_maintenance: "Поддержание веса",
  performance: "Результативность",
  general_health: "Общее здоровье",
};

export const GOAL_STATUS_LABELS: Record<GoalStatus, string> = {
  active: "Активна",
  paused: "На паузе",
  completed: "Достигнута",
  cancelled: "Отменена",
};

export const GOAL_STATUS_TONES: Record<GoalStatus, Tone> = {
  active: "green",
  paused: "amber",
  completed: "slate",
  cancelled: "red",
};

export const SESSION_STATUS_LABELS: Record<TrainingSessionStatus, string> = {
  planned: "Запланирована",
  completed: "Выполнена",
  skipped: "Пропущена",
  cancelled: "Отменена",
};

export const SESSION_STATUS_TONES: Record<TrainingSessionStatus, Tone> = {
  planned: "amber",
  completed: "green",
  skipped: "slate",
  cancelled: "red",
};

export const LOAD_TYPE_LABELS: Record<LoadType, string> = {
  strength: "Силовая",
  cardio: "Кардио",
  mixed: "Смешанная",
  other: "Другая",
};

export const INTENSITY_LABELS: Record<Intensity, string> = {
  low: "Низкая",
  moderate: "Средняя",
  high: "Высокая",
};

export const EVENT_TYPE_LABELS: Record<ScheduleEventType, string> = {
  sleep: "Сон",
  work: "Работа",
  meal: "Приём пищи",
  workout: "Тренировка",
  personal: "Личное",
  other: "Другое",
};

export const EVENT_TYPE_TONES: Record<ScheduleEventType, Tone> = {
  sleep: "slate",
  work: "amber",
  meal: "green",
  workout: "green",
  personal: "slate",
  other: "slate",
};

export const FOOD_CATEGORY_LABELS: Record<FoodCategory, string> = {
  meat: "Мясо и птица",
  fish: "Рыба и морепродукты",
  eggs: "Яйца",
  dairy: "Молочные продукты",
  grains: "Крупы и гарниры",
  bakery: "Хлеб и выпечка",
  vegetables: "Овощи",
  fruits: "Фрукты и ягоды",
  legumes: "Бобовые",
  nuts: "Орехи и семена",
  fats: "Масла и жиры",
  sweets: "Сладкое",
  drinks: "Напитки",
  sauces: "Соусы",
  supplements: "Спортивное питание",
  other: "Другое",
};

export const ACTIVITY_LEVEL_LABELS: Record<ActivityLevel, string> = {
  sedentary: "Сидячий день (офис, мало ходьбы)",
  light: "Немного ходьбы в течение дня",
  moderate: "Много ходьбы или работа на ногах",
  active: "Тяжёлый физический труд",
};

export const GOAL_PROGRESS_LABELS: Record<GoalProgressStatus, string> = {
  no_data: "Мало данных",
  reached: "Цель достигнута",
  on_track: "По плану",
  faster: "Быстрее плана",
  slower: "Медленнее плана",
  stalled: "Без изменений",
  wrong_direction: "Не в ту сторону",
};

export const GOAL_PROGRESS_TONES: Record<GoalProgressStatus, Tone> = {
  no_data: "slate",
  reached: "green",
  on_track: "green",
  faster: "amber",
  slower: "amber",
  stalled: "amber",
  wrong_direction: "red",
};

export const MEAL_LOCATION_LABELS: Record<MealLocation, string> = {
  home: "Дома",
  work: "На работе",
  away: "Вне дома",
};

export const PHOTO_ANGLE_LABELS: Record<PhotoAngle, string> = {
  front: "Спереди",
  side: "Сбоку",
  back: "Сзади",
  other: "Другое",
};

export const PLANNED_STATUS_LABELS: Record<PlannedMealStatus, string> = {
  planned: "В плане",
  eaten: "Съеден",
  skipped: "Пропущен",
};

export const PLANNED_STATUS_TONES: Record<PlannedMealStatus, Tone> = {
  planned: "slate",
  eaten: "green",
  skipped: "amber",
};

/** Варианты пола для выпадающего списка; пустое значение означает «не задан». */
export const SEX_OPTIONS: [string, string][] = [
  ["", "—"],
  ["male", "Мужской"],
  ["female", "Женский"],
  ["unspecified", "Не указывать"],
];

/** Превращает словарь подписей в список вариантов: { low: "Низкая" } → [["low", "Низкая"]]. */
export function toOptions(labels: Record<string, string>): [string, string][] {
  return Object.entries(labels);
}

// ---------- Числа ----------

/** Форматирует число или строку с числом по-русски: ("100.50", 2) → "100,5". */
export function formatNumber(value: string | number, maxDigits = 1): string {
  return Number(value).toLocaleString("ru-RU", { maximumFractionDigits: maxDigits });
}

/** Вес для показа: "100.00" → "100 кг"; null → "—". */
export function formatKg(value: string | null): string {
  return value === null ? "—" : `${formatNumber(value, 2)} кг`;
}

/** Калории для показа без дробной части: "331.50" → "332 ккал". */
export function formatKcal(value: string | number | null): string {
  return value === null ? "—" : `${formatNumber(value, 0)} ккал`;
}

/** Пустое поле формы → null, иначе число: "" → null, "80.5" → 80.5. */
export function optionalNumber(value: string): number | null {
  return value.trim() === "" ? null : Number(value);
}

/** Пустое поле формы → null, иначе обрезанный текст. */
export function optionalText(value: string): string | null {
  return value.trim() === "" ? null : value.trim();
}

// ---------- Даты и время ----------
// Даты без времени хранятся строками "ГГГГ-ММ-ДД". Моменты времени приходят
// в формате ISO ("2026-10-23T17:00:00Z") и показываются в часовом поясе устройства.

/** Сегодняшняя дата в часовом поясе пользователя: "Europe/Berlin" → "2026-10-26". */
export function todayInZone(timeZone: string): string {
  // Формат "en-CA" даёт именно ГГГГ-ММ-ДД
  return new Intl.DateTimeFormat("en-CA", { timeZone }).format(new Date());
}

/** Сдвигает дату на days дней: ("2026-10-31", 1) → "2026-11-01". */
export function shiftDate(date: string, days: number): string {
  const shifted = new Date(`${date}T00:00:00Z`);
  shifted.setUTCDate(shifted.getUTCDate() + days);
  return shifted.toISOString().slice(0, 10);
}

/** Делает первую букву заглавной: «четверг, 29 октября» → «Четверг, 29 октября». Пустая строка остаётся пустой. */
export function capitalizeFirst(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/** "2026-10-26" → "понедельник, 26 октября". */
export function formatDateLong(date: string): string {
  return new Date(`${date}T12:00:00Z`).toLocaleDateString("ru-RU", {
    weekday: "long",
    day: "numeric",
    month: "long",
    timeZone: "UTC",
  });
}

/** "2026-10-26" → "26 окт. 2026 г.". */
export function formatShortDate(date: string): string {
  return new Date(`${date}T12:00:00Z`).toLocaleDateString("ru-RU", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
}

/** "2026-10-23T17:00:00Z" → "17:00" (в часовом поясе устройства). */
export function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
}

/** Дата момента iso в часовом поясе timeZone: ("2026-10-26T22:30:00Z", "Europe/Moscow") → "2026-10-27". */
export function dateInZone(iso: string, timeZone: string): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone }).format(new Date(iso));
}

/** Время момента iso в часовом поясе timeZone: ("2026-10-26T06:00:00Z", "Europe/Moscow") → "09:00". */
export function formatTimeInZone(iso: string, timeZone: string): string {
  return new Date(iso).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit", timeZone });
}

/** Понедельник недели, в которую попадает дата: "2026-10-28" (среда) → "2026-10-26". */
export function mondayOf(date: string): string {
  // getUTCDay: 0 — воскресенье … 6 — суббота; нам нужно число дней после понедельника
  const dayOfWeek = new Date(`${date}T00:00:00Z`).getUTCDay();
  return shiftDate(date, -((dayOfWeek + 6) % 7));
}

/** "2026-10-26" → "пн, 26 окт." */
export function formatDayShort(date: string): string {
  return new Date(`${date}T12:00:00Z`).toLocaleDateString("ru-RU", {
    weekday: "short",
    day: "numeric",
    month: "short",
    timeZone: "UTC",
  });
}

/** "2026-10-23T17:00:00Z" → "23 окт., 17:00" (в часовом поясе устройства). */
export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString("ru-RU", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/**
 * Дата и время в часовом поясе timeZone → момент времени в формате ISO (UTC).
 * Пример: ("2026-10-27", "13:30", "Europe/Moscow") → "2026-10-27T10:30:00.000Z".
 * Нужен, чтобы время приёма пищи считалось по часовому поясу профиля, а не устройства.
 */
export function zonedToIso(date: string, time: string, timeZone: string): string {
  const [year, month, day] = date.split("-").map(Number);
  const [hour, minute] = time.split(":").map(Number);
  const asUtc = Date.UTC(year, month - 1, day, hour, minute);

  // Насколько местное время пояса опережает UTC в момент ms (в миллисекундах)
  const offsetAt = (ms: number): number => {
    const parts = new Intl.DateTimeFormat("en-CA", {
      timeZone,
      hourCycle: "h23",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    }).formatToParts(new Date(ms));
    const part = (type: string) => Number(parts.find((item) => item.type === type)?.value);
    const local = Date.UTC(part("year"), part("month") - 1, part("day"), part("hour"), part("minute"), part("second"));
    return local - ms;
  };

  // Второй проход уточняет смещение, если рядом переход на летнее/зимнее время
  const first = asUtc - offsetAt(asUtc);
  return new Date(asUtc - offsetAt(first)).toISOString();
}

/** Date → значение для поля datetime-local: "2026-10-23T17:00". */
export function localInputValue(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}`
  );
}

/** Значение datetime-local (локальное время устройства) → ISO с часовым поясом. */
export function toIsoFromLocal(value: string): string {
  return new Date(value).toISOString();
}

/** Текущее время устройства для поля time: "17:05". */
export function currentTimeValue(): string {
  const now = new Date();
  return `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;
}

/** Ближайший круглый час: в 16:20 вернёт 17:00. */
export function nextFullHour(): Date {
  const date = new Date();
  date.setMinutes(0, 0, 0);
  date.setHours(date.getHours() + 1);
  return date;
}

/** Прибавляет часы к дате и возвращает новую дату. */
export function addHours(date: Date, hours: number): Date {
  return new Date(date.getTime() + hours * 3_600_000);
}

/** Момент iso ещё не наступил? */
export function isFuture(iso: string): boolean {
  return new Date(iso).getTime() > Date.now();
}


// ---------- Финансы ----------

export const FINANCE_KIND_LABELS: Record<FinanceKind, string> = {
  expense: "Расход",
  income: "Доход",
};

/** Валюты для выбора при создании книги (backend принимает любой код из трёх букв). */
export const CURRENCY_OPTIONS: [string, string][] = [
  ["RUB", "RUB — российский рубль"],
  ["EUR", "EUR — евро"],
  ["USD", "USD — доллар США"],
  ["GBP", "GBP — фунт стерлингов"],
  ["CHF", "CHF — швейцарский франк"],
  ["SEK", "SEK — шведская крона"],
  ["PLN", "PLN — злотый"],
  ["UAH", "UAH — гривна"],
];

/** Сумма с валютой по-русски: (120.5, "EUR") → "120,50 €". */
export function formatMoney(value: string | number, currency: string): string {
  const amount = Number(value);
  // Целые суммы без копеек: "35 000 ₽"; дробные с двумя знаками: "1 250,50 ₽"
  const whole = Number.isInteger(amount);
  return amount.toLocaleString("ru-RU", {
    style: "currency",
    currency,
    minimumFractionDigits: whole ? 0 : 2,
    maximumFractionDigits: 2,
  });
}

/** "2026-10-28" → "28 окт." (день и месяц, без года). */
export function formatDayMonth(date: string): string {
  return new Date(`${date}T12:00:00Z`).toLocaleDateString("ru-RU", {
    day: "numeric",
    month: "short",
    timeZone: "UTC",
  });
}

/** "2026-10-28" → "ср, 28 окт." (с днём недели). */
export function formatWeekdayDayMonth(date: string): string {
  return new Date(`${date}T12:00:00Z`).toLocaleDateString("ru-RU", {
    weekday: "short",
    day: "numeric",
    month: "short",
    timeZone: "UTC",
  });
}

/** Сколько дней от a до b: ("2026-10-10", "2026-10-13") → 3. Отрицательное, если b раньше a. */
export function daysBetween(a: string, b: string): number {
  return Math.round((Date.parse(`${b}T00:00:00Z`) - Date.parse(`${a}T00:00:00Z`)) / 86_400_000);
}

/** Склонение по числу: plural(1, ["день", "дня", "дней"]) → "день"; 3 → "дня"; 11 → "дней"; 21 → "день". */
export function plural(count: number, forms: [string, string, string]): string {
  const n = Math.abs(count) % 100;
  const last = n % 10;
  if (n > 10 && n < 20) return forms[2];
  if (last === 1) return forms[0];
  if (last >= 2 && last <= 4) return forms[1];
  return forms[2];
}

/** Сдвигает месяц: ("2026-12", 1) → "2027-01". */
export function shiftMonth(month: string, delta: number): string {
  const [year, monthNumber] = month.split("-").map(Number);
  return new Date(Date.UTC(year, monthNumber - 1 + delta, 1)).toISOString().slice(0, 7);
}

/** "2026-10" → "октябрь 2026 г.". */
export function formatMonthLabel(month: string): string {
  return new Date(`${month}-01T12:00:00Z`).toLocaleDateString("ru-RU", {
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  });
}