import { daysBetween, formatDayMonth, formatMoney } from "@/lib/format";
import type { Cycle, Occurrence } from "@/lib/types";

/**
 * «Лента периода»: бюджетный период в виде горизонтальной шкалы по дням.
 *   * зелёные кружки над шкалой — поступления (пустой кружок: ещё не пришло);
 *   * столбики под шкалой — обязательные платежи, чем платёж больше, тем столбик выше
 *     (тёмный: впереди, серый: оплачен, красный: просрочен);
 *   * шафрановая точка — сегодня; закрашенная часть шкалы — уже прошедшие дни.
 * С одного взгляда видно, где в периоде сосредоточены крупные платежи и когда придут деньги.
 *
 * maxAmount — самая крупная сумма среди показываемых периодов: общий масштаб делает ленты сравнимыми.
 * compact — уменьшенный вариант для списка сравнения периодов.
 */
export default function CycleStrip({
  cycle,
  maxAmount,
  currency,
  compact = false,
}: {
  cycle: Cycle;
  maxAmount: number;
  currency: string;
  compact?: boolean;
}) {
  const total = Math.max(1, cycle.days_total);
  // Размеры в пикселях: зона над шкалой (доходы), шкала, зона под шкалой (платежи)
  const above = compact ? 16 : 28;
  const track = compact ? 6 : 8;
  const below = compact ? 26 : 46;
  const barWidth = compact ? 4 : 6;

  /** Положение дня в процентах ширины: центр дневной «клетки». */
  const position = (date: string) => {
    const index = Math.min(total - 1, Math.max(0, daysBetween(cycle.start, date)));
    return ((index + 0.5) / total) * 100;
  };
  /** Размер маркера от суммы: корень смягчает разницу между мелкими и крупными суммами. */
  const ratio = (amount: string) => Math.sqrt(Math.min(1, Math.max(0, Number(amount) / (maxAmount || 1))));

  // Сколько процентов шкалы уже прошло (только для текущего периода). days_left считает и сегодняшний день,
  // поэтому номер сегодняшнего дня внутри периода: всего дней минус оставшиеся
  const todayIndex =
    cycle.is_current && cycle.days_left !== null ? Math.min(total - 1, Math.max(0, total - cycle.days_left)) : null;
  const elapsed = todayIndex === null ? null : ((todayIndex + 0.5) / total) * 100;

  const incomes = cycle.items.filter((item) => item.kind === "income" && item.status !== "skipped");
  const payments = cycle.items.filter((item) => item.kind === "expense" && item.status !== "skipped");

  const description =
    `Период с ${formatDayMonth(cycle.start)} по ${formatDayMonth(cycle.end)}: ` +
    `доходы ${formatMoney(cycle.income_total, currency)}, обязательные платежи ${formatMoney(cycle.mandatory_total, currency)}`;

  return (
    <div>
      <div
        role="img"
        aria-label={description}
        className="relative"
        style={{ height: above + track + below + 6 }}
      >
        {/* Шкала и прошедшая часть */}
        <div className="absolute inset-x-0 rounded-full bg-slate-200" style={{ top: above, height: track }} />
        {elapsed !== null && (
          <div className="absolute left-0 rounded-full bg-brand-300" style={{ top: above, height: track, width: `${elapsed}%` }} />
        )}

        {/* Поступления: кружки над шкалой */}
        {incomes.map((item) => {
          const size = (compact ? 8 : 12) + ratio(item.amount) * (compact ? 6 : 10);
          return (
            <span
              key={`${item.rule_id}-${item.due_on}`}
              title={markerTitle(item, currency)}
              className={`absolute rounded-full border-2 border-good-500 ${item.status === "posted" ? "bg-good-500" : "bg-white"}`}
              style={{ left: `${position(item.due_on)}%`, top: above - 3 - size, width: size, height: size, transform: "translateX(-50%)" }}
            />
          );
        })}

        {/* Платежи: столбики под шкалой */}
        {payments.map((item) => {
          const height = (compact ? 8 : 12) + ratio(item.amount) * (compact ? 16 : 32);
          const color = item.status === "posted" ? "bg-slate-300" : item.overdue ? "bg-red-500" : "bg-brand-800";
          return (
            <span
              key={`${item.rule_id}-${item.due_on}`}
              title={markerTitle(item, currency)}
              className={`absolute rounded-full ${color}`}
              style={{ left: `${position(item.due_on)}%`, top: above + track + 3, width: barWidth, height, transform: "translateX(-50%)" }}
            />
          );
        })}

        {/* Сегодня: линия и шафрановая точка на шкале */}
        {elapsed !== null && (
          <>
            <span
              className="absolute w-px bg-saffron/60"
              style={{ left: `${elapsed}%`, top: 0, height: above + track + below }}
              aria-hidden="true"
            />
            <span
              className="absolute size-3.5 rounded-full bg-saffron ring-2 ring-white"
              style={{ left: `${elapsed}%`, top: above + track / 2 - 7, transform: "translateX(-50%)" }}
              title="Сегодня"
              aria-hidden="true"
            />
          </>
        )}
      </div>

      <div className="mt-1 flex justify-between text-xs text-slate-500">
        <span>{formatDayMonth(cycle.start)}</span>
        <span>{formatDayMonth(cycle.end)}</span>
      </div>

      {!compact && (
        <ul className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-xs text-slate-500">
          <li className="flex items-center gap-1.5">
            <span className="size-2.5 rounded-full border-2 border-good-500 bg-good-500" /> Доход
          </li>
          <li className="flex items-center gap-1.5">
            <span className="h-3 w-1.5 rounded-full bg-brand-800" /> Платёж
          </li>
          {elapsed !== null && (
            <li className="flex items-center gap-1.5">
              <span className="size-2.5 rounded-full bg-saffron" /> Сегодня
            </li>
          )}
        </ul>
      )}
    </div>
  );
}

/** Подсказка при наведении на маркер: «Аренда: 35 000 ₽, 3 нояб.». */
function markerTitle(item: Occurrence, currency: string): string {
  return `${item.rule_name}: ${formatMoney(item.amount, currency)}, ${formatDayMonth(item.due_on)}`;
}
