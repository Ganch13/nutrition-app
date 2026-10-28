"use client";

import { useEffect, useRef } from "react";
import { Icon } from "@/components/icons";
import { formatDayMonth, formatMonthLabel } from "@/lib/format";
import type { AdviceItem, RecurringRule, RuleFrequency } from "@/lib/types";

/** Вкладки раздела «Финансы». */
export type FinanceTab = "overview" | "operations" | "rules" | "goals" | "settings";

/** Варианты периодичности для списка выбора: [значение, подпись]. */
export const FREQUENCY_OPTIONS: [RuleFrequency, string][] = [
  ["monthly", "Каждый месяц"],
  ["semimonthly", "Два раза в месяц"],
  ["biweekly", "Раз в две недели"],
  ["weekly", "Каждую неделю"],
  ["yearly", "Раз в год"],
];

// "по пятницам": индекс — номер дня недели по JavaScript (0 — воскресенье)
const WEEKDAY_EACH = ["по воскресеньям", "по понедельникам", "по вторникам", "по средам", "по четвергам", "по пятницам", "по субботам"];

/** День недели даты в виде "по пятницам". Пример: "2026-10-30" → "по пятницам". */
function weekdayEach(date: string): string {
  return WEEKDAY_EACH[new Date(`${date}T12:00:00Z`).getUTCDay()];
}

/**
 * Расписание правила словами.
 * Примеры: monthly, день 10 → "каждый месяц, 10-го числа"; semimonthly 10 и 25 → "два раза в месяц, 10-го и 25-го";
 * biweekly от пятницы → "раз в две недели, по пятницам".
 */
export function describeSchedule(
  rule: Pick<RecurringRule, "frequency" | "day_of_month" | "start_on"> & { second_day_of_month?: number | null },
): string {
  const day = rule.day_of_month ?? Number(rule.start_on.slice(8, 10));
  switch (rule.frequency) {
    case "monthly":
      return `каждый месяц, ${day}-го числа`;
    case "semimonthly": {
      const days = [day, rule.second_day_of_month ?? day].sort((a, b) => a - b);
      return days[0] === days[1] ? `два раза в месяц, ${day}-го числа` : `два раза в месяц, ${days[0]}-го и ${days[1]}-го`;
    }
    case "biweekly":
      return `раз в две недели, ${weekdayEach(rule.start_on)}`;
    case "weekly":
      return `каждую неделю, ${weekdayEach(rule.start_on)}`;
    case "yearly":
      return `раз в год, ${formatDayMonth(rule.start_on)}`;
  }
}

/** Последний день месяца для даты "2026-10-28" → "2026-10-31". */
function lastDayOfMonth(date: string): string {
  const [year, month] = date.split("-").map(Number);
  return new Date(Date.UTC(year, month, 0)).toISOString().slice(0, 10);
}

/**
 * Название периода. Если период совпадает с календарным месяцем, пишем месяц ("Октябрь 2026"),
 * иначе даты ("28 окт. — 9 нояб.").
 */
export function formatPeriod(start: string, end: string): string {
  if (start.endsWith("-01") && end === lastDayOfMonth(start)) {
    const label = formatMonthLabel(start.slice(0, 7)).replace(/\sг\.$/, "");
    return label.charAt(0).toUpperCase() + label.slice(1);
  }
  return `${formatDayMonth(start)} — ${formatDayMonth(end)}`;
}

const ADVICE_STYLES = {
  info: { box: "bg-brand-50 text-brand-900", icon: "bulb" as const },
  warning: { box: "bg-amber-50 text-amber-800", icon: "alert" as const },
  danger: { box: "bg-red-50 text-red-700", icon: "alert" as const },
};

/** Список советов, написанных сервером: цвет и значок зависят от серьёзности. */
export function AdviceList({ items }: { items: AdviceItem[] }) {
  if (items.length === 0) return null;
  return (
    <ul className="space-y-2">
      {items.map((item, index) => {
        const style = ADVICE_STYLES[item.severity];
        return (
          <li key={`${item.code}-${index}`} className={`flex items-start gap-3 rounded-xl px-4 py-3 text-sm ${style.box}`}>
            <Icon name={style.icon} size={18} className="mt-0.5 shrink-0" />
            <span>{item.text}</span>
          </li>
        );
      })}
    </ul>
  );
}

/**
 * Периодически обновляет данные, пока человек смотрит на страницу, и при возвращении на вкладку.
 * Так общая цель семьи показывает новые взносы второго участника без перезагрузки страницы.
 * refresh — функция обновления (обычно reload из useAsyncData); enabled — включено ли; intervalMs — как часто.
 */
export function useAutoRefresh(refresh: () => void, enabled: boolean, intervalMs = 20_000) {
  // Хранит самую свежую функцию, чтобы не пересоздавать таймер при каждом обновлении
  const latest = useRef(refresh);
  useEffect(() => {
    latest.current = refresh;
  }, [refresh]);

  useEffect(() => {
    if (!enabled) return;
    const tick = () => {
      if (document.visibilityState === "visible") latest.current();
    };
    const timer = window.setInterval(tick, intervalMs);
    document.addEventListener("visibilitychange", tick);
    window.addEventListener("focus", tick);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", tick);
      window.removeEventListener("focus", tick);
    };
  }, [enabled, intervalMs]);
}

/** Строка вида «подпись — значение» для итогов. */
export function Stat({
  label,
  value,
  note,
  tone = "default",
}: {
  label: string;
  value: string;
  note?: string;
  tone?: "default" | "good" | "bad";
}) {
  const color = tone === "good" ? "text-good-700" : tone === "bad" ? "text-red-600" : "text-slate-900";
  return (
    <div className="rounded-xl bg-slate-50 p-4">
      <p className="text-xs text-slate-500">{label}</p>
      <p className={`num mt-1 text-lg font-semibold ${color}`}>{value}</p>
      {note && <p className="num mt-0.5 text-xs text-slate-500">{note}</p>}
    </div>
  );
}
