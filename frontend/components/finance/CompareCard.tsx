import { Card } from "@/components/ui";
import { formatMoney } from "@/lib/format";
import type { Cycle, Ledger } from "@/lib/types";
import CycleStrip from "./CycleStrip";
import { CycleStatusBadge } from "./PeriodCard";
import { formatPeriod } from "./shared";

/**
 * «Периоды рядом»: текущий и следующий период на одинаковой шкале.
 * Нужна, чтобы заметить кассовый разрыв заранее: если в одном периоде платежи огромные,
 * а в другом почти нет, это видно по высоте тёмных столбиков.
 * Показываются только два периода (ТЗ 29.10.26(2), п. 1): даже если сервер прислал больше, лишние отбрасываются.
 */
export default function CompareCard({ ledger, cycles, maxAmount }: { ledger: Ledger; cycles: Cycle[]; maxAmount: number }) {
  const shown = cycles.slice(0, 2);

  return (
    <Card
      title="Периоды рядом"
      description="Текущий и следующий период на одной шкале: чем выше тёмный столбик, тем крупнее платёж. Так видно, какой период тяжелее."
    >
      <ul className="space-y-6">
        {shown.map((cycle) => (
          <li key={cycle.start}>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="font-medium text-slate-900">
                {cycle.is_current ? "Текущий" : "Следующий"}{" "}
                <span className="font-normal text-slate-500">{formatPeriod(cycle.start, cycle.end)}</span>
              </p>
              <CycleStatusBadge cycle={cycle} />
            </div>
            <div className="mt-2">
              <CycleStrip cycle={cycle} maxAmount={maxAmount} currency={ledger.currency} compact />
            </div>
            <p className="num mt-1 text-xs text-slate-500">
              Доход {formatMoney(cycle.income_total, ledger.currency)}, платежи{" "}
              {formatMoney(cycle.mandatory_total, ledger.currency)}, свободно{" "}
              <span className={Number(cycle.free_after_mandatory) < 0 ? "font-medium text-red-600" : undefined}>
                {formatMoney(cycle.free_after_mandatory, ledger.currency)}
              </span>
            </p>
          </li>
        ))}
      </ul>
    </Card>
  );
}
