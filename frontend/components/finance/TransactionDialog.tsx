"use client";

import { useCallback, useState } from "react";
import { Button, Dialog, ErrorBanner, Loading } from "@/components/ui";
import { getFinanceCategories, getFinanceGoals } from "@/lib/endpoints";
import { todayInZone } from "@/lib/format";
import { useProfile } from "@/lib/profile-context";
import { useAsyncData } from "@/lib/use-async-data";
import { notifyFinanceChanged } from "./IncomePromptDialog";
import TransactionForm from "./TransactionForm";

/**
 * Окно «Внести расход/доход»: та же форма операции, что во «Финансы → Операции» (TransactionForm),
 * только во всплывающем окне — без перехода на другую страницу.
 *
 * Путь данных: кнопка на главной → окно загружает категории и цели книги
 * (GET /finance/ledgers/1/categories и /goals) → «Добавить» → POST /finance/ledgers/1/transactions
 * {category_id: 3, amount: 350, occurred_on: "2026-10-29", description: null, goal_id: null}
 * → окно рассылает FINANCE_CHANGED_EVENT и закрывается → блоки «Деньги» и «Финансовая цель» перезагружаются.
 *
 * ledgerId — книга (личная или семейная), title — «Личные» или «Семья», onClose — закрыть окно.
 */
export default function TransactionDialog({
  ledgerId,
  title,
  onClose,
}: {
  ledgerId: number;
  title: string;
  onClose: () => void;
}) {
  const { profile } = useProfile();
  const today = todayInZone(profile.timezone);
  // Категории и цели этой книги — варианты полей «Категория» и «Цель»
  const load = useCallback(async () => {
    const [categories, goals] = await Promise.all([getFinanceCategories(ledgerId), getFinanceGoals(ledgerId)]);
    return { categories, goals };
  }, [ledgerId]);
  const { data, error, reload } = useAsyncData(load);

  return (
    <Dialog title={title} heading="Новая операция" onClose={onClose}>
      <div className="mt-4">
        {error && <ErrorBanner message={error} onRetry={reload} />}
        {data === null && !error && <Loading />}
        {data && (
          <TransactionForm
            ledgerId={ledgerId}
            categories={data.categories}
            goals={data.goals}
            today={today}
            framed={false}
            onDone={() => {
              notifyFinanceChanged();
              onClose();
            }}
            onCancel={onClose}
          />
        )}
      </div>
    </Dialog>
  );
}

/**
 * Кнопка «Внести расход/доход» вместе с окном. Пример: <TransactionButton ledgerId={1} title="Личные" />.
 * className — сдвиг под соседнюю вёрстку.
 */
export function TransactionButton({ ledgerId, title, className }: { ledgerId: number; title: string; className?: string }) {
  const [open, setOpen] = useState(false);
  const close = useCallback(() => setOpen(false), []);
  return (
    <>
      <Button size="sm" variant="secondary" className={className} onClick={() => setOpen(true)}>
        Внести расход/доход
      </Button>
      {open && <TransactionDialog ledgerId={ledgerId} title={title} onClose={close} />}
    </>
  );
}
