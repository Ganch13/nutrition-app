import { Badge, Card } from "@/components/ui";
import { formatDayMonth, formatMoney, plural } from "@/lib/format";
import type { Cycle, Ledger } from "@/lib/types";
import CycleStrip from "./CycleStrip";
import { formatPeriod, Stat } from "./shared";

/** Метка состояния периода: хватает денег, туго или не хватает. */
export function CycleStatusBadge({ cycle }: { cycle: Cycle }) {
  if (cycle.status === "gap") return <Badge tone="red">Не хватает денег</Badge>;
  if (cycle.status === "tight") {
    const percent = cycle.mandatory_share === null ? "" : `: платежи ${Math.round(cycle.mandatory_share * 100)} % дохода`;
    return <Badge tone="amber">{`Туго${percent}`}</Badge>;
  }
  return <Badge tone="green">Хватает</Badge>;
}

/**
 * Карточка текущего бюджетного периода: главная цифра («сколько можно тратить в день»), лента периода
 * и четыре показателя. Периодом может быть календарный месяц или промежуток между поступлениями дохода,
 * это настраивается на вкладке «Настройки».
 */
export function PeriodCard({ ledger, cycle, maxAmount }: { ledger: Ledger; cycle: Cycle; maxAmount: number }) {
  const money = (value: string | number) => formatMoney(value, ledger.currency);
  const available = Number(cycle.available);
  const daysLeft = cycle.days_left;

  // Главная цифра: что важнее всего знать прямо сейчас
  let heroLabel: string;
  let heroValue: string;
  let heroNote: string | null = null;
  let heroBad = false;
  if (cycle.is_current && cycle.daily_allowance !== null) {
    heroLabel = "Можно тратить в день";
    heroValue = money(cycle.daily_allowance);
    if (daysLeft !== null) {
      heroNote = `до ${formatDayMonth(cycle.end)}, ${daysLeft} ${plural(daysLeft, ["день", "дня", "дней"])}`;
    }
  } else if (available < 0) {
    heroLabel = "Не хватает до конца периода";
    heroValue = money(-available);
    heroBad = true;
  } else if (cycle.is_current) {
    heroLabel = "Свободных денег в периоде не осталось";
    heroValue = money(0);
    heroBad = true;
  } else {
    heroLabel = "Останется после обязательных платежей";
    heroValue = money(cycle.free_after_mandatory);
  }

  return (
    <Card
      title={ledger.cycle_mode === "income" ? "Бюджетный период" : "Текущий месяц"}
      description={`${formatPeriod(cycle.start, cycle.end)}${
        daysLeft !== null ? `, осталось ${daysLeft} ${plural(daysLeft, ["день", "дня", "дней"])}` : ""
      }`}
      action={<CycleStatusBadge cycle={cycle} />}
    >
      <div className="mb-6">
        <p className="text-sm text-slate-500">{heroLabel}</p>
        <p className={`figure num mt-1 text-4xl sm:text-5xl ${heroBad ? "text-red-600" : "text-slate-900"}`}>{heroValue}</p>
        {heroNote && <p className="mt-1 text-sm text-slate-500">{heroNote}</p>}
      </div>

      <CycleStrip cycle={cycle} maxAmount={maxAmount} currency={ledger.currency} />

      <div className="mt-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat
          label="Доход"
          value={money(cycle.income_total)}
          note={Number(cycle.income_expected) > 0 ? `ещё ждём ${money(cycle.income_expected)}` : undefined}
        />
        <Stat
          label="Обязательные платежи"
          value={money(cycle.mandatory_total)}
          note={Number(cycle.mandatory_pending) > 0 ? `впереди ${money(cycle.mandatory_pending)}` : undefined}
        />
        <Stat label="Обычные траты" value={money(cycle.other_spent)} />
        <Stat label="Останется" value={money(cycle.available)} tone={available < 0 ? "bad" : "default"} />
      </div>
    </Card>
  );
}
