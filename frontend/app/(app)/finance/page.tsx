"use client";

import Link from "next/link";
import { useCallback, useState } from "react";
import GoalsTab from "@/components/finance/GoalsTab";
import HomeBlockReturn from "@/components/HomeBlockReturn";
import CreateLedgerCard from "@/components/finance/LedgerSetup";
import OperationsTab from "@/components/finance/OperationsTab";
import OverviewTab from "@/components/finance/OverviewTab";
import RulesTab from "@/components/finance/RulesTab";
import SettingsTab, { type CreatableLedger } from "@/components/finance/SettingsTab";
import type { FinanceTab } from "@/components/finance/shared";
import { Card, ErrorBanner, Loading, Notice, PageHeader, Segmented } from "@/components/ui";
import { getHouseholds, getLedgers } from "@/lib/endpoints";
import type { Ledger } from "@/lib/types";
import { useAsyncData } from "@/lib/use-async-data";

const TABS: [FinanceTab, string][] = [
  ["overview", "Обзор"],
  ["operations", "Операции"],
  ["rules", "Платежи и доходы"],
  ["goals", "Цели"],
  ["settings", "Настройки"],
];

/** Вкладка из адреса страницы: /finance?tab=goals → "goals"; без параметра или на сервере — «Обзор». */
function requestedTab(): FinanceTab {
  if (typeof window === "undefined") return "overview";
  const requested = new URLSearchParams(window.location.search).get("tab");
  return TABS.find(([value]) => value === requested)?.[0] ?? "overview";
}

/** Название книги для переключателя: «Личные» или «Семья: Дом». */
function ledgerTitle(ledger: Ledger): string {
  return ledger.kind === "personal" ? "Личные" : `Семья: ${ledger.household_name}`;
}

/**
 * Страница «Финансы».
 * Сверху вкладки: Обзор, Операции, Платежи и доходы, Цели, Настройки.
 * Все вкладки, кроме «Целей», работают с одной книгой (личной или семейной), её выбирают переключателем ниже.
 * «Цели» показывают цели всех книг сразу: личные и общие.
 * Если книг нет, вместо вкладок показывается приглашение включить финансы.
 */
export default function FinancePage() {
  // Книги пользователя и его семьи (чтобы предложить включить недостающие)
  const loadLedgers = useCallback(async () => {
    const [ledgers, households] = await Promise.all([getLedgers(), getHouseholds()]);
    return { ledgers, households };
  }, []);
  const { data, error, reload } = useAsyncData(loadLedgers);

  // Ссылка вида /finance?tab=goals (например, с главной) открывает сразу нужную вкладку.
  // Вкладки появляются только после загрузки книг, поэтому первый показ на сервере и в браузере одинаковый
  const [tab, setTab] = useState<FinanceTab>(requestedTab);
  const [selectedId, setSelectedId] = useState<number | null>(null);

  if (error && data === null) {
    return (
      <>
        <PageHeader title="Финансы" subtitle="Деньги, платежи и цели" />
        <ErrorBanner message={error} onRetry={reload} />
      </>
    );
  }
  if (data === null) {
    return (
      <>
        <PageHeader title="Финансы" subtitle="Деньги, платежи и цели" />
        <Loading />
      </>
    );
  }

  const { ledgers, households } = data;
  // Показываем выбранную книгу, а если выбора ещё не было, первую (личную)
  const current = ledgers.find((ledger) => ledger.id === selectedId) ?? ledgers[0] ?? null;

  // Книги, которые ещё не включены: личная и семейные книги семей, где пользователь владелец или администратор
  const creatable: CreatableLedger[] = [];
  if (!ledgers.some((ledger) => ledger.kind === "personal")) {
    creatable.push({ key: "personal", title: "Включить личные финансы", kind: "personal", householdId: null });
  }
  for (const household of households) {
    const canCreate = household.role === "owner" || household.role === "admin";
    if (canCreate && !ledgers.some((ledger) => ledger.household_id === household.id)) {
      creatable.push({
        key: `household-${household.id}`,
        title: `Включить финансы семьи «${household.name}»`,
        kind: "household",
        householdId: household.id,
      });
    }
  }

  // Нет ни одной книги: объясняем, что здесь будет, и предлагаем включить
  if (current === null) {
    return (
      <>
        <PageHeader title="Финансы" subtitle="Деньги, платежи и цели" />
        <HomeBlockReturn block="money" />
        <HomeBlockReturn block="finance_goal" />
        <div className="max-w-2xl space-y-6">
          <Card>
            <p className="text-slate-700">
              Здесь будут ваши доходы, обязательные платежи и цели. Лад покажет, сколько можно тратить в день и хватит ли
              денег до следующей зарплаты.
            </p>
          </Card>
          {creatable.map((item) => (
            <CreateLedgerCard key={item.key} title={item.title} kind={item.kind} householdId={item.householdId} onCreated={reload} />
          ))}
          {households.length === 0 && (
            <Notice>
              Чтобы вести общие деньги, нужна семья. Создайте её или присоединитесь по коду на странице{" "}
              <Link href="/family" className="font-medium underline underline-offset-2">
                «Семья»
              </Link>
              .
            </Notice>
          )}
        </div>
      </>
    );
  }

  // Переключатель книг нужен, когда книг больше одной, и не нужен на вкладке «Цели»
  const showSwitcher = ledgers.length > 1 && tab !== "goals";

  return (
    <>
      <PageHeader title="Финансы" subtitle="Деньги, платежи и цели" />
      <HomeBlockReturn block="money" />

      <div className="space-y-6">
        <div className="flex flex-wrap items-center gap-3">
          <Segmented label="Раздел финансов" value={tab} onChange={(value) => setTab(value as FinanceTab)} options={TABS} />
          {showSwitcher && (
            <Segmented
              label="Книга"
              value={String(current.id)}
              onChange={(value) => setSelectedId(Number(value))}
              options={ledgers.map((ledger): [string, string] => [String(ledger.id), ledgerTitle(ledger)])}
            />
          )}
        </div>

        {tab === "overview" && <OverviewTab key={current.id} ledger={current} goTo={setTab} />}
        {tab === "operations" && <OperationsTab key={current.id} ledger={current} />}
        {tab === "rules" && <RulesTab key={current.id} ledger={current} />}
        {tab === "goals" && <GoalsTab ledgers={ledgers} />}
        {tab === "settings" && (
          <SettingsTab key={current.id} ledger={current} creatable={creatable} onLedgersChanged={reload} />
        )}
      </div>
    </>
  );
}
