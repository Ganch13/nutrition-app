import type { Tone } from "@/components/ui";
import type {
  GoalStatus,
  GoalType,
  Intensity,
  LoadType,
  MealType,
  TrainingSessionStatus,
  FinanceKind,
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

/** "2026-10-23T17:00:00Z" → "23 окт., 17:00" (в часовом поясе устройства). */
export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString("ru-RU", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
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
  return Number(value).toLocaleString("ru-RU", { style: "currency", currency });
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