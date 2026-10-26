"use client";

import Link from "next/link";
import { useCallback } from "react";
import { Badge, Card, ErrorBanner, Loading } from "@/components/ui";
import {
  getDailyEntries,
  getDailySummary,
  getGoals,
  getTrainingSessions,
  getWeightRecords,
} from "@/lib/endpoints";
import {
  formatDateLong,
  formatDateTime,
  formatKg,
  formatNumber,
  formatTime,
  GOAL_TYPE_LABELS,
  isFuture,
  MEAL_TYPE_LABELS,
  SESSION_STATUS_LABELS,
  SESSION_STATUS_TONES,
  todayInZone,
} from "@/lib/format";
import { useProfile } from "@/lib/profile-context";
import { useAsyncData } from "@/lib/use-async-data";

/** Главная страница: вес и цель, питание сегодня, ближайшая тренировка. */
export default function DashboardPage() {
  const { profile } = useProfile();
  const userId = profile.id;
  // Сегодня в часовом поясе профиля, например "2026-10-26"
  const today = todayInZone(profile.timezone);

  // Три независимых блока данных: у каждого свои загрузка и ошибка
  const loadStats = useCallback(async () => {
    const [weights, goals] = await Promise.all([getWeightRecords(userId), getGoals(userId)]);
    return { weights, goals };
  }, [userId]);
  const loadNutrition = useCallback(
    () => Promise.all([getDailySummary(userId, today), getDailyEntries(userId, today)]),
    [userId, today],
  );
  const loadSessions = useCallback(() => getTrainingSessions(userId), [userId]);

  const stats = useAsyncData(loadStats);
  const nutrition = useAsyncData(loadNutrition);
  const sessions = useAsyncData(loadSessions);

  // Backend отдаёт вес от новых записей к старым, а цели — активные первыми
  // и по возрастанию приоритета (1 — высший), поэтому берём первые подходящие
  const latestWeight = stats.data?.weights[0] ?? null;
  const activeGoal = stats.data?.goals.find((goal) => goal.status === "active") ?? null;

  // Ближайшая запланированная тренировка, которая ещё не закончилась
  const nextSession =
    sessions.data
      ?.filter((session) => session.status === "planned" && isFuture(session.end_at))
      .sort((a, b) => new Date(a.start_at).getTime() - new Date(b.start_at).getTime())[0] ?? null;

  const summary = nutrition.data?.[0] ?? null;
  const meals = nutrition.data?.[1] ?? null;

  return (
    <>
      <header className="mb-6">
        <p className="text-sm text-slate-500">{formatDateLong(today)}</p>
        <h1 className="mt-1 text-2xl font-bold tracking-tight sm:text-3xl">Привет, {profile.name}! 👋</h1>
      </header>

      <div className="mb-6 rounded-3xl bg-emerald-700 p-6 text-white sm:p-8">
        <p className="text-sm text-emerald-100">Твоя главная цель</p>
        <h2 className="mt-2 text-2xl font-bold sm:text-3xl">
          {activeGoal ? GOAL_TYPE_LABELS[activeGoal.goal_type] : "Цель не задана"}
        </h2>
        {!activeGoal && !stats.loading && (
          <Link href="/progress" className="mt-3 inline-block text-sm underline">
            Добавить цель
          </Link>
        )}

        <div className="mt-6 grid grid-cols-2 gap-3 sm:max-w-lg">
          <div className="rounded-2xl bg-white/10 p-4">
            <p className="text-xs text-emerald-100">Текущий вес</p>
            <p className="mt-1 text-2xl font-bold">
              {stats.data ? formatKg(latestWeight?.weight_kg ?? null) : "…"}
            </p>
          </div>
          <div className="rounded-2xl bg-white/10 p-4">
            <p className="text-xs text-emerald-100">Целевой вес</p>
            <p className="mt-1 text-2xl font-bold">
              {stats.data ? formatKg(activeGoal?.target_weight_kg ?? null) : "…"}
            </p>
          </div>
        </div>
        {stats.error && (
          <div className="mt-4 sm:max-w-lg">
            <ErrorBanner message={stats.error} onRetry={stats.reload} />
          </div>
        )}
      </div>

      <div className="mb-6 grid gap-4 sm:grid-cols-2">
        <Card title="Калории сегодня" action={<Link href="/nutrition" className="text-sm text-emerald-700 underline">Открыть</Link>}>
          {nutrition.error && <ErrorBanner message={nutrition.error} onRetry={nutrition.reload} />}
          {summary === null && !nutrition.error && <Loading />}
          {summary && (
            <>
              <p className="text-3xl font-bold">
                {formatNumber(summary.calories, 0)}
                <span className="ml-2 text-sm font-normal text-slate-400">ккал</span>
              </p>
              <p className="mt-2 text-sm text-slate-500">
                Б {formatNumber(summary.protein_g, 0)} · Ж {formatNumber(summary.fat_g, 0)} · У{" "}
                {formatNumber(summary.carbs_g, 0)}
              </p>
            </>
          )}
        </Card>

        <Card title="Ближайшая тренировка" action={<Link href="/training" className="text-sm text-emerald-700 underline">Открыть</Link>}>
          {sessions.error && <ErrorBanner message={sessions.error} onRetry={sessions.reload} />}
          {sessions.data === null && !sessions.error && <Loading />}
          {sessions.data && !nextSession && <p className="text-sm text-slate-500">Запланированных тренировок нет.</p>}
          {nextSession && (
            <>
              <p className="text-xl font-bold">{nextSession.name}</p>
              <p className="mt-2 text-sm text-slate-500">
                {formatDateTime(nextSession.start_at)} – {formatTime(nextSession.end_at)}
              </p>
              <div className="mt-3">
                <Badge tone={SESSION_STATUS_TONES[nextSession.status]}>
                  {SESSION_STATUS_LABELS[nextSession.status]}
                </Badge>
              </div>
            </>
          )}
        </Card>
      </div>

      <Card title="Питание на сегодня">
        {meals === null && !nutrition.error && <Loading />}
        {meals?.length === 0 && <p className="text-sm text-slate-500">Сегодня записей пока нет.</p>}
        <ul className="divide-y divide-slate-100">
          {meals?.map((meal) => (
            <li key={meal.id} className="flex items-center justify-between gap-3 py-3">
              <div className="min-w-0">
                <p className="font-medium">
                  {formatTime(meal.eaten_at)} · {MEAL_TYPE_LABELS[meal.meal_type]}
                </p>
                <p className="truncate text-sm text-slate-500">{meal.description}</p>
              </div>
              <p className="shrink-0 text-sm font-semibold">{formatNumber(meal.calories, 0)} ккал</p>
            </li>
          ))}
        </ul>
      </Card>
    </>
  );
}