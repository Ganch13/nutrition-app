"use client";

import { useCallback, useState } from "react";
import { Card, ErrorBanner, Loading, Notice, Segmented } from "@/components/ui";
import { getErrorText } from "@/lib/api";
import { getFinanceCategories, setCycleMode } from "@/lib/endpoints";
import type { CycleMode, Ledger } from "@/lib/types";
import { useAsyncData } from "@/lib/use-async-data";
import CategoriesCard from "./CategoriesCard";
import CreateLedgerCard from "./LedgerSetup";

/** Книга, которую можно включить: личная или семейная. */
export type CreatableLedger = { key: string; title: string; kind: "personal" | "household"; householdId: number | null };

const MODE_OPTIONS: [CycleMode, string][] = [
  ["calendar", "Календарный месяц"],
  ["income", "От дохода до дохода"],
];

/**
 * Вкладка «Настройки»: как считать бюджетный период, категории и подключение других книг.
 * Режим периода меняют владелец и администратор; остальные видят его, но не меняют.
 * creatable — книги, которые ещё не включены; onLedgersChanged — перечитать список книг после изменения.
 */
export default function SettingsTab({
  ledger,
  creatable,
  onLedgersChanged,
}: {
  ledger: Ledger;
  creatable: CreatableLedger[];
  onLedgersChanged: () => void;
}) {
  const loadCategories = useCallback(() => getFinanceCategories(ledger.id), [ledger.id]);
  const categories = useAsyncData(loadCategories);

  const [savingMode, setSavingMode] = useState(false);
  const [modeError, setModeError] = useState<string | null>(null);

  /** Переключает режим периода: PATCH /finance/ledgers/{id} { cycle_mode }. */
  async function handleMode(mode: string) {
    if (mode === ledger.cycle_mode) return;
    setModeError(null);
    setSavingMode(true);
    try {
      await setCycleMode(ledger.id, mode as CycleMode);
      onLedgersChanged();
    } catch (err) {
      setModeError(getErrorText(err));
    } finally {
      setSavingMode(false);
    }
  }

  return (
    <div className="space-y-6">
      <Card
        title="Бюджетный период"
        description="С какого дня считать месяц. От этого зависят лимиты, остаток на день и разбивка платежей."
      >
        <Segmented
          label="Бюджетный период"
          value={ledger.cycle_mode}
          onChange={ledger.can_manage && !savingMode ? handleMode : () => {}}
          options={MODE_OPTIONS}
        />
        <div className="mt-4 space-y-3 text-sm text-slate-600">
          {ledger.cycle_mode === "calendar" ? (
            <p>Период начинается 1-го числа и заканчивается в последний день месяца.</p>
          ) : (
            <p>
              Период начинается в день основного дохода и заканчивается накануне следующего основного дохода. Так аванс и
              зарплата не складываются в один месяц, и в конце периода не остаётся пустого кошелька.
            </p>
          )}
          <Notice>
            «От дохода до дохода» работает, когда есть основной повторяющийся доход. Основной или дополнительный, выбирают
            во вкладке «Платежи и доходы»; дополнительные доходы границ периода не задают. Без основных доходов мы
            считаем по календарным месяцам.
          </Notice>
          {!ledger.can_manage && <p className="text-slate-500">Режим меняют владелец и администратор семьи.</p>}
        </div>
        {modeError && (
          <div className="mt-4">
            <ErrorBanner message={modeError} />
          </div>
        )}
      </Card>

      {categories.error && categories.data === null ? (
        <ErrorBanner message={categories.error} onRetry={categories.reload} />
      ) : categories.data === null ? (
        <Loading />
      ) : (
        <CategoriesCard
          ledgerId={ledger.id}
          categories={categories.data}
          canManage={ledger.can_manage}
          onChanged={categories.reload}
        />
      )}

      {creatable.map((item) => (
        <CreateLedgerCard
          key={item.key}
          title={item.title}
          kind={item.kind}
          householdId={item.householdId}
          onCreated={onLedgersChanged}
        />
      ))}
    </div>
  );
}
