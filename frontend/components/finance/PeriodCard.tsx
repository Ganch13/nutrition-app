import { Badge, Card } from "@/components/ui";
import { formatDayMonth, formatMoney, plural } from "@/lib/format";
import type { Cycle, Ledger, SpendingPlan } from "@/lib/types";
import { BalanceAdjustButton } from "./BalanceAdjustDialog";
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
 * Метка «хватает ли денег» по общему расчёту spending (как на главной): ожидаемый доход не считается,
 * поэтому «Хватает» показывается только если реальных денег хватает до следующего основного дохода.
 */
function SpendingStatusBadge({ spending, cycle }: { spending: SpendingPlan; cycle: Cycle }) {
  if (spending.status === "gap") return <Badge tone="red">Не хватает денег</Badge>;
  if (spending.status === "no_income") return <Badge tone="amber">Нет следующего дохода</Badge>;
  if (spending.status === "income_today") return <Badge tone="amber">Доход сегодня</Badge>;
  return <CycleStatusBadge cycle={cycle} />;
}

/**
 * Карточка текущего бюджетного периода: главная цифра («сколько можно тратить в день»), лента периода
 * и четыре показателя. Периодом может быть календарный месяц или промежуток между поступлениями дохода,
 * это настраивается на вкладке «Настройки».
 *
 * Главная цифра и плитка «Останется» берутся из spending — общего расчёта сервера (тот же, что на главной):
 *   Останется (свободно) = баланс − обязательные платежи до следующего основного дохода;
 *   Можно тратить в день = свободно ÷ дни до следующего основного дохода.
 * Ожидаемый, ещё не подтверждённый доход в эти цифры не входит. Пример: баланс 0, ждём зарплату 70 000 →
 * «Можно тратить в день: 0 ₽», а не 23 333 ₽.
 */
export function PeriodCard({
  ledger,
  cycle,
  spending,
  maxAmount,
}: {
  ledger: Ledger;
  cycle: Cycle;
  spending: SpendingPlan;
  maxAmount: number;
}) {
  const money = (value: string | number) => formatMoney(value, ledger.currency);
  const daysLeft = cycle.days_left;
  const free = spending.free === null ? null : Number(spending.free);

  // Главная цифра: что важнее всего знать прямо сейчас. heroValue = null — вместо числа текст из spending.note
  let heroLabel = "Можно тратить в день";
  let heroValue: string | null = null;
  let heroNote: string | null = spending.note;
  let heroBad = false;
  if (spending.daily_allowance !== null && spending.next_income_on !== null && spending.days_left !== null) {
    heroValue = money(spending.daily_allowance);
    heroNote = `до ${formatDayMonth(spending.next_income_on)}, ${spending.days_left} ${plural(spending.days_left, ["день", "дня", "дней"])}`;
  } else if (spending.status === "gap" && free !== null) {
    heroLabel = "Не хватает до следующего дохода";
    heroValue = money(-free);
    heroBad = true;
  }

  return (
    <Card
      title={ledger.cycle_mode === "income" ? "Бюджетный период" : "Текущий месяц"}
      description={`${formatPeriod(cycle.start, cycle.end)}${
        daysLeft !== null ? `, осталось ${daysLeft} ${plural(daysLeft, ["день", "дня", "дней"])}` : ""
      }`}
      action={<SpendingStatusBadge spending={spending} cycle={cycle} />}
    >
      <div className="mb-6">
        <p className="text-sm text-slate-500">{heroLabel}</p>
        {heroValue !== null && (
          <p className={`figure num mt-1 text-4xl sm:text-5xl ${heroBad ? "text-red-600" : "text-slate-900"}`}>{heroValue}</p>
        )}
        {heroNote && <p className={heroValue === null ? "mt-1 text-base font-medium text-slate-700" : "mt-1 text-sm text-slate-500"}>{heroNote}</p>}
        {/* Баланс книги и «Изменить баланс» — та же кнопка и то же окно, что на главной */}
        <div className="mt-3 flex flex-wrap items-center gap-x-2 text-sm text-slate-600">
          <span>
            Баланс{" "}
            <span className={`num font-semibold ${Number(spending.balance) < 0 ? "text-red-600" : "text-slate-900"}`}>
              {money(spending.balance)}
            </span>
          </span>
          <BalanceAdjustButton
            ledgerId={ledger.id}
            title={ledger.kind === "personal" ? "Личные" : `Семья: ${ledger.household_name}`}
            currency={ledger.currency}
          />
        </div>
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
        <Stat
          label="Останется"
          value={free === null ? "—" : money(free)}
          note={free === null ? "нет следующего дохода" : "из денег на счетах после платежей"}
          tone={free !== null && free < 0 ? "bad" : "default"}
        />
      </div>
    </Card>
  );
}
