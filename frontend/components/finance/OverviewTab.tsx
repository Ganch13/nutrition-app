"use client";

import { useCallback } from "react";
import { Button, Card, EmptyState, ErrorBanner, Loading } from "@/components/ui";
import { getCycles, getLoad, getPeriodSummary, getUpcoming } from "@/lib/endpoints";
import type { Ledger } from "@/lib/types";
import { useAsyncData } from "@/lib/use-async-data";
import CompareCard from "./CompareCard";
import LimitsCard from "./LimitsCard";
import LoadCard from "./LoadCard";
import OccurrenceList from "./OccurrenceList";
import { PeriodCard } from "./PeriodCard";
import { AdviceList, type FinanceTab } from "./shared";

/**
 * Вкладка «Обзор»: всё, что нужно знать о деньгах прямо сейчас.
 * Сверху текущий период с главной цифрой, ниже ближайшие платежи, сравнение периодов, советы,
 * финансовая нагрузка и лимиты. Данные приходят пятью запросами, которые выполняются одновременно.
 * goTo — переключить вкладку (например, чтобы добавить первый доход).
 */
export default function OverviewTab({ ledger, goTo }: { ledger: Ledger; goTo: (tab: FinanceTab) => void }) {
  const load = useCallback(async () => {
    const [cycles, upcoming, loadReport, summary] = await Promise.all([
      getCycles(ledger.id, 0, 3),
      getUpcoming(ledger.id, 30),
      getLoad(ledger.id),
      getPeriodSummary(ledger.id),
    ]);
    return { cycles, upcoming, loadReport, summary };
  }, [ledger.id, ledger.cycle_mode]);
  const { data, error, reload } = useAsyncData(load);

  if (error && data === null) return <ErrorBanner message={error} onRetry={reload} />;
  if (data === null) return <Loading />;

  const { cycles, upcoming, loadReport, summary } = data;
  const current = cycles.cycles.find((cycle) => cycle.is_current) ?? cycles.cycles[0];
  // Общий масштаб для всех лент: самая крупная выплата среди показанных периодов
  const maxAmount = Math.max(
    1,
    ...cycles.cycles.flatMap((cycle) => cycle.items.map((item) => Number(item.amount))),
  );
  const nothingPlanned = Number(loadReport.income_monthly) === 0 && Number(loadReport.mandatory_monthly) === 0;
  // Выплаты, требующие действия, и недавно отмеченные, чтобы можно было отменить ошибку
  const actionable = upcoming.filter((item) => item.status === "pending");

  return (
    <div className="space-y-6">
      {error && <ErrorBanner message={error} onRetry={reload} />}

      {nothingPlanned && (
        <Card>
          <EmptyState
            title="Добавьте зарплату и обязательные платежи"
            action={<Button onClick={() => goTo("rules")}>Добавить доход и платежи</Button>}
          >
            Тогда здесь появится, сколько можно тратить в день, как платежи распределены по периодам и можно ли брать
            ещё кредиты.
          </EmptyState>
        </Card>
      )}

      {current && <PeriodCard ledger={ledger} cycle={current} spending={cycles.spending} maxAmount={maxAmount} />}

      {actionable.length > 0 && (
        <Card title="Ближайшие платежи и поступления" description="Отметьте, когда заплатили или получили: операция появится в списке, а цифры периода обновятся.">
          <OccurrenceList ledger={ledger} items={actionable} today={cycles.today} onChanged={reload} />
        </Card>
      )}

      {cycles.cycles.length > 1 && <CompareCard ledger={ledger} cycles={cycles.cycles} maxAmount={maxAmount} />}

      {cycles.advice.length > 0 && (
        <Card title="Советы по периодам">
          <AdviceList items={cycles.advice} />
        </Card>
      )}

      <LoadCard ledger={ledger} load={loadReport} onAddRules={() => goTo("rules")} />

      <LimitsCard ledger={ledger} categories={summary.categories} onChanged={reload} />
    </div>
  );
}
