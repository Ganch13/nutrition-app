"use client";

import { useCallback, useMemo, useState } from "react";
import HomeBlockReturn from "@/components/HomeBlockReturn";
import { Button, Card, EmptyState, ErrorBanner, Loading } from "@/components/ui";
import { getFinanceGoals } from "@/lib/endpoints";
import { useProfile } from "@/lib/profile-context";
import { todayInZone } from "@/lib/format";
import type { FinanceGoal, Ledger } from "@/lib/types";
import { useAsyncData } from "@/lib/use-async-data";
import GoalCard from "./GoalCard";
import GoalWizard from "./GoalWizard";
import { useAutoRefresh } from "./shared";

/**
 * Вкладка «Цели»: личные и общие цели в одном списке.
 * Цели лежат в книгах (личной и семейных), поэтому вкладка загружает цели всех книг пользователя
 * и показывает их двумя группами: «Мои цели» и «Общие цели семьи».
 * Пока на экране есть общая цель, список раз в 20 секунд обновляется сам (и при возвращении на вкладку),
 * поэтому взнос второго участника появляется без перезагрузки страницы.
 * ledgers — все книги пользователя.
 */
export default function GoalsTab({ ledgers }: { ledgers: Ledger[] }) {
  const { profile } = useProfile();
  const today = todayInZone(profile.timezone);
  const [creating, setCreating] = useState(false);

  // Ключ из id книг: загрузка повторяется только если набор книг изменился
  const ledgerKey = ledgers.map((ledger) => ledger.id).join(",");
  const load = useCallback(async () => {
    const ids = ledgerKey === "" ? [] : ledgerKey.split(",").map(Number);
    const lists = await Promise.all(ids.map((id) => getFinanceGoals(id)));
    return lists.flat();
  }, [ledgerKey]);
  const { data, error, reload } = useAsyncData(load);

  const hasShared = data?.some((goal) => goal.shared) ?? false;
  useAutoRefresh(reload, hasShared && !creating);

  // Невыполненные цели выше выполненных; внутри группы новые выше старых
  const groups = useMemo(() => {
    const order = (a: FinanceGoal, b: FinanceGoal) =>
      Number(a.done) - Number(b.done) || b.created_at.localeCompare(a.created_at);
    const goals = data ?? [];
    return {
      personal: goals.filter((goal) => !goal.shared).sort(order),
      shared: goals.filter((goal) => goal.shared).sort(order),
    };
  }, [data]);

  if (ledgers.length === 0) {
    return (
      <Card>
        <EmptyState title="Сначала включите финансы">Цели хранятся в личных или семейных финансах. Включить их можно во вкладке «Настройки».</EmptyState>
      </Card>
    );
  }
  if (error && data === null) return <ErrorBanner message={error} onRetry={reload} />;
  if (data === null) return <Loading />;

  /** Мастер закрылся после создания: обновляем список. */
  function handleCreated() {
    setCreating(false);
    reload();
  }

  const empty = groups.personal.length === 0 && groups.shared.length === 0;

  return (
    <div className="space-y-6">
      <HomeBlockReturn block="finance_goal" />
      {error && <ErrorBanner message={error} onRetry={reload} />}

      {creating ? (
        <GoalWizard ledgers={ledgers} onCreated={handleCreated} onCancel={() => setCreating(false)} />
      ) : (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="max-w-xl text-sm text-slate-600">
            Копите на отпуск, возвращайте долги и гасите кредиты. Для общих целей видно, кто сколько внёс.
          </p>
          <Button onClick={() => setCreating(true)}>Новая цель</Button>
        </div>
      )}

      {empty && !creating && (
        <Card>
          <EmptyState
            title="Целей пока нет"
            action={<Button onClick={() => setCreating(true)}>Создать первую цель</Button>}
          >
            Начните с накопления: например, «Отпуск» на 200 000 ₽.
          </EmptyState>
        </Card>
      )}

      <GoalGroup title="Мои цели" goals={groups.personal} today={today} onChanged={reload} />
      <GoalGroup title="Общие цели семьи" goals={groups.shared} today={today} onChanged={reload} />
    </div>
  );
}

/** Группа карточек с заголовком; пустая группа не показывается. */
function GoalGroup({
  title,
  goals,
  today,
  onChanged,
}: {
  title: string;
  goals: FinanceGoal[];
  today: string;
  onChanged: () => void;
}) {
  if (goals.length === 0) return null;
  return (
    <section aria-label={title} className="space-y-4">
      <h2 className="font-display text-xl font-semibold text-slate-900">{title}</h2>
      <div className="grid items-start gap-4 lg:grid-cols-2">
        {goals.map((goal) => (
          <GoalCard key={goal.id} goal={goal} today={today} onChanged={onChanged} />
        ))}
      </div>
    </section>
  );
}
