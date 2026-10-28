import { Card } from "@/components/ui";
import { formatMoney } from "@/lib/format";
import type { Cycle, Ledger } from "@/lib/types";
import CycleStrip from "./CycleStrip";
import { CycleStatusBadge } from "./PeriodCard";
import { formatPeriod } from "./shared";

/**
 * «Периоды рядом»: текущий и следующие периоды на одинаковой шкале.
 * Нужна, чтобы заметить кассовый разрыв заранее: если в одном периоде платежи огромные,
 * а в другом почти нет, это видно по высоте тёмных столбиков.
 */
export default function CompareCard({ ledger, cycles, maxAmount }: { ledger: Ledger; cycles: Cycle[]; maxAmount: number }) {
  const labels = ["Текущий", "Следующий", "Потом"];

  return (
    <Card
      title="Периоды рядом"
      description="Все периоды на одной шкале: чем выше тёмный столбик, тем крупнее платёж. Так видно, какой период тяжелее."
    >
      <ul className="space-y-6">
        {cycles.map((cycle, index) => (
          <li key={cycle.start}>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="font-medium text-slate-900">
                {cycle.is_current ? labels[0] : (labels[index] ?? "Потом")}{" "}
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
