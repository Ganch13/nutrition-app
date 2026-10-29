"use client";

import Link from "next/link";
import { useCallback, type ReactNode } from "react";
import { BalanceAdjustButton } from "@/components/finance/BalanceAdjustDialog";
import { useFinanceChanged } from "@/components/finance/IncomePromptDialog";
import { TransactionButton } from "@/components/finance/TransactionDialog";
import { Badge, Button, Card, EmptyState, ErrorBanner, Loading, ProgressBar } from "@/components/ui";
import {
  getDailySummary,
  getFinanceGoals,
  getFinanceHome,
  getGoalProgress,
  getHouseholds,
  getLedgers,
  getMealPlanWeek,
  getTrainingSessions,
} from "@/lib/endpoints";
import {
  capitalizeFirst,
  formatDateLong,
  formatDateTime,
  formatDayMonth,
  formatKg,
  formatMoney,
  formatNumber,
  formatTime,
  GOAL_PROGRESS_LABELS,
  GOAL_PROGRESS_TONES,
  GOAL_TYPE_LABELS,
  isFuture,
  mondayOf,
  SESSION_STATUS_LABELS,
  SESSION_STATUS_TONES,
  todayInZone,
} from "@/lib/format";
import { HOME_BLOCK_LABELS, useHomeBlocks } from "@/lib/home-blocks";
import { useProfile } from "@/lib/profile-context";
import type { FinanceHomeLedger, HomeBlock } from "@/lib/types";
import { useAsyncData } from "@/lib/use-async-data";

// Где вернуть скрытый блок: подсказка для пустой главной
const RETURN_PLACES: Record<HomeBlock, string> = {
  money: "«Финансы»",
  finance_goal: "«Финансы» → «Цели»",
  nutrition: "«Питание»",
  training: "«Тренировки»",
  weight: "«Прогресс»",
};

/** Ссылка в углу карточки, например «Открыть». */
function CardLink({ href, children = "Открыть" }: { href: string; children?: ReactNode }) {
  return (
    <Link href={href} className="text-sm font-medium text-brand-700 underline-offset-2 hover:underline">
      {children}
    </Link>
  );
}

/** Действия в углу карточки: «Открыть» и «Скрыть». */
function BlockActions({ href, onHide }: { href: string; onHide: () => void }) {
  return (
    <div className="flex items-center gap-1">
      <CardLink href={href} />
      <Button size="sm" variant="ghost" onClick={onHide}>
        Скрыть
      </Button>
    </div>
  );
}

/** Крупная цифра с подписью: «48 500 ₽» и «всего». */
function Figure({ value, unit, caption, tone = "default" }: { value: string; unit?: string; caption?: string; tone?: "default" | "bad" }) {
  return (
    <div className="min-w-0">
      {caption && <p className="text-xs text-slate-500">{caption}</p>}
      <p className={`figure num mt-0.5 text-3xl ${tone === "bad" ? "text-red-600" : "text-slate-900"}`}>
        {value}
        {unit && <span className="ml-1.5 font-sans text-sm font-normal text-slate-500">{unit}</span>}
      </p>
    </div>
  );
}

/**
 * Главная страница. Блоки сверху вниз: деньги и финансовая цель (справа от денег), питание сегодня,
 * ближайшая тренировка, вес и цель по весу. Каждый блок можно скрыть; вернуть его можно в его разделе.
 * Если скрыты все, главная пустая и подсказывает, где блоки вернуть.
 * У каждого блока свои загрузка и ошибка: медленный блок не мешает остальным, а скрытый ничего не загружает.
 */
export default function DashboardPage() {
  const { profile } = useProfile();
  const today = todayInZone(profile.timezone);
  const { isHidden, setHidden, error } = useHomeBlocks();

  const hide = (block: HomeBlock) => () => void setHidden(block, true);
  const showMoney = !isHidden("money");
  const showGoal = !isHidden("finance_goal");
  const lower: HomeBlock[] = (["nutrition", "training", "weight"] as HomeBlock[]).filter((block) => !isHidden(block));
  const nothingShown = !showMoney && !showGoal && lower.length === 0;

  return (
    <>
      {/* Шапка: только сегодняшняя дата с днём недели, крупно («Четверг, 29 октября») — без приветствия и имени */}
      <header className="mb-8">
        <h1 className="text-3xl font-semibold tracking-tight text-slate-900 sm:text-4xl">
          {capitalizeFirst(formatDateLong(today))}
        </h1>
      </header>

      {error && (
        <div className="mb-6">
          <ErrorBanner message={error} />
        </div>
      )}

      {nothingShown && (
        <div className="rounded-2xl border border-dashed border-slate-300 px-5 py-10 text-center">
          <p className="font-medium text-slate-800">Все блоки главной скрыты</p>
          <p className="mx-auto mt-1 max-w-md text-sm text-slate-500">
            Вернуть их можно в разделах:{" "}
            {(Object.keys(RETURN_PLACES) as HomeBlock[])
              .map((block) => `${HOME_BLOCK_LABELS[block].toLowerCase()} — ${RETURN_PLACES[block]}`)
              .join(", ")}
            .
          </p>
        </div>
      )}

      {(showMoney || showGoal) && (
        <div className={`mb-4 grid gap-4 ${showMoney && showGoal ? "lg:grid-cols-[3fr_2fr]" : ""}`}>
          {showMoney && <MoneyBlock onHide={hide("money")} />}
          {showGoal && <FinanceGoalBlock onHide={hide("finance_goal")} />}
        </div>
      )}

      {lower.length > 0 && (
        <div className={`grid gap-4 ${lower.length === 3 ? "lg:grid-cols-3" : lower.length === 2 ? "lg:grid-cols-2" : ""}`}>
          {lower.includes("nutrition") && <NutritionBlock today={today} onHide={hide("nutrition")} />}
          {lower.includes("training") && <TrainingBlock onHide={hide("training")} />}
          {lower.includes("weight") && <WeightBlock onHide={hide("weight")} />}
        </div>
      )}
    </>
  );
}

/**
 * Деньги: личный и семейный разрезы независимо. В каждом — сколько денег всего и сколько свободно
 * в текущем бюджетном периоде. Личные деньги в семейный разрез не входят. Если пользователь не в семье,
 * семейного разреза нет. Разрезы стоят друг под другом, а не рядом, чтобы семейный не сжимал цифры личного.
 */
function MoneyBlock({ onHide }: { onHide: () => void }) {
  const load = useCallback(async () => {
    const [ledgers, households] = await Promise.all([getFinanceHome(), getHouseholds()]);
    return { ledgers, households };
  }, []);
  const { data, error, reload } = useAsyncData(load);
  useFinanceChanged(reload);

  const personal = data?.ledgers.find((item) => item.kind === "personal") ?? null;
  // Семейный разрез по каждой семье пользователя (обычно одна)
  const families = data?.households ?? [];

  return (
    <Card title="Деньги" action={<BlockActions href="/finance" onHide={onHide} />}>
      {error && <ErrorBanner message={error} onRetry={reload} />}
      {data === null && !error && <Loading />}
      {data && (
        // Разрезы всегда друг под другом (сначала «Личные», ниже семьи): ширина и размер цифр
        // в разрезе не зависят от того, есть ли семья
        <div className="space-y-4">
          <MoneySlice title="Личные" item={personal} />
          {families.map((household) => (
            <MoneySlice
              key={household.id}
              title={families.length > 1 ? `Семья: ${household.name}` : "Семья"}
              item={data.ledgers.find((ledger) => ledger.household_id === household.id) ?? null}
            />
          ))}
        </div>
      )}
    </Card>
  );
}

/**
 * Один разрез денег: баланс и свободно до следующего основного дохода. item = null — финансы этой книги не включены.
 * «Баланс» — кошелёк: только фактические операции и корректировки. «Свободно» = баланс − обязательные платежи
 * до следующего основного дохода (общий расчёт сервера, тот же, что во «Финансы → Обзор»).
 * Кнопка «Изменить баланс» открывает окно, где можно ввести фактический остаток без дохода и расхода.
 * Кнопка «Внести расход/доход» открывает форму операции этой книги во всплывающем окне; после сохранения
 * цифры блока перезагружаются (FINANCE_CHANGED_EVENT).
 */
function MoneySlice({ title, item }: { title: string; item: FinanceHomeLedger | null }) {
  return (
    <div className="rounded-xl bg-slate-50 p-4">
      <p className="text-sm font-medium text-slate-700">{title}</p>
      {item === null ? (
        <p className="mt-2 text-sm text-slate-500">
          Финансы не включены.{" "}
          <Link href="/finance" className="font-medium text-brand-700 underline underline-offset-2">
            Включить
          </Link>
        </p>
      ) : (
        <div className="mt-2 grid grid-cols-2 gap-3">
          <Figure caption="Баланс" value={formatMoney(item.total, item.currency)} tone={Number(item.total) < 0 ? "bad" : "default"} />
          {item.free === null || item.free_until === null ? (
            // Нет следующего основного дохода: делить не на что, показываем подсказку вместо числа
            <div className="min-w-0">
              <p className="text-xs text-slate-500">Свободно</p>
              <p className="mt-1 text-sm text-slate-600">{item.spending_note}</p>
            </div>
          ) : (
            <div className="min-w-0">
              <Figure
                caption={`Свободно до ${formatDayMonth(item.free_until)}`}
                value={formatMoney(item.free, item.currency)}
                tone={Number(item.free) < 0 ? "bad" : "default"}
              />
              {item.spending_status === "gap" && <p className="mt-0.5 text-xs text-red-600">{item.spending_note}</p>}
            </div>
          )}
          <div className="col-span-2 flex flex-wrap items-center gap-2 pt-1">
            <TransactionButton ledgerId={item.ledger_id} title={title} />
            <BalanceAdjustButton ledgerId={item.ledger_id} title={title} currency={item.currency} />
          </div>
        </div>
      )}
    </div>
  );
}

/** Финансовая цель: первая невыполненная (сначала личные, затем общие). Без цели — предложение добавить. */
function FinanceGoalBlock({ onHide }: { onHide: () => void }) {
  const load = useCallback(async () => {
    const ledgers = await getLedgers();
    const lists = await Promise.all(ledgers.map((ledger) => getFinanceGoals(ledger.id)));
    const goals = lists.flat().filter((goal) => !goal.done);
    return goals.sort((a, b) => Number(a.shared) - Number(b.shared) || b.created_at.localeCompare(a.created_at))[0] ?? null;
  }, []);
  const { data: goal, error, loading, reload } = useAsyncData(load);
  useFinanceChanged(reload);

  return (
    // Пока цели нет, «Скрыть» стоит рядом с предложением добавить цель, а в углу только ссылка
    <Card
      title="Финансовая цель"
      action={goal === null && !loading ? <CardLink href="/finance?tab=goals" /> : <BlockActions href="/finance?tab=goals" onHide={onHide} />}
    >
      {error && <ErrorBanner message={error} onRetry={reload} />}
      {goal === null && loading && !error && <Loading />}
      {goal === null && !loading && !error && (
        <EmptyState
          title="Цели пока нет"
          action={
            <div className="flex flex-wrap justify-center gap-2">
              <Link
                href="/finance?tab=goals"
                className="inline-flex min-h-10 items-center rounded-xl bg-brand-700 px-4 text-sm font-medium text-white hover:bg-brand-800"
              >
                Добавить цель
              </Link>
              <Button variant="secondary" onClick={onHide}>
                Скрыть
              </Button>
            </div>
          }
        >
          Отпуск, подушка безопасности или кредит: здесь будет видно, сколько осталось.
        </EmptyState>
      )}
      {goal && (
        <>
          <p className="font-display text-xl font-semibold text-slate-900">{goal.name}</p>
          <p className="mt-0.5 text-xs text-slate-500">{goal.shared ? "Общая цель семьи" : "Личная цель"}</p>
          <div className="mt-4">
            <ProgressBar value={goal.progress} tone="good" label={`Цель «${goal.name}» выполнена на ${Math.round(goal.progress * 100)} %`} />
          </div>
          <div className="mt-3 flex flex-wrap items-baseline justify-between gap-2 text-sm">
            <span className="text-slate-600">
              {goal.kind === "savings" ? "Осталось накопить" : "Осталось выплатить"}{" "}
              <span className="num font-semibold text-slate-900">{formatMoney(goal.remaining, goal.currency)}</span>
            </span>
            <span className="num text-slate-500">{Math.round(goal.progress * 100)} %</span>
          </div>
        </>
      )}
    </Card>
  );
}

/** Питание сегодня: калории и БЖУ — сколько съедено и сколько запланировано в плане питания. */
function NutritionBlock({ today, onHide }: { today: string; onHide: () => void }) {
  const { profile } = useProfile();
  const userId = profile.id;
  const load = useCallback(async () => {
    const [eaten, week] = await Promise.all([getDailySummary(userId, today), getMealPlanWeek(userId, mondayOf(today))]);
    return { eaten, plan: week.days.find((day) => day.date === today) ?? null };
  }, [userId, today]);
  const { data, error, reload } = useAsyncData(load);

  // План есть, если на сегодня в нём хоть один приём пищи (пропущенные в сумму плана не входят)
  const plan = data?.plan && data.plan.meals.length > 0 ? data.plan : null;
  const hasPlan = plan !== null;
  const rows: { label: string; unit: string; eaten: string; planned: string | null }[] = data
    ? [
        { label: "Калории", unit: "ккал", eaten: data.eaten.calories, planned: plan?.planned_calories ?? null },
        { label: "Белки", unit: "г", eaten: data.eaten.protein_g, planned: plan?.planned_protein_g ?? null },
        { label: "Жиры", unit: "г", eaten: data.eaten.fat_g, planned: plan?.planned_fat_g ?? null },
        { label: "Углеводы", unit: "г", eaten: data.eaten.carbs_g, planned: plan?.planned_carbs_g ?? null },
      ]
    : [];

  return (
    <Card title="Питание сегодня" action={<BlockActions href="/nutrition" onHide={onHide} />}>
      {error && <ErrorBanner message={error} onRetry={reload} />}
      {data === null && !error && <Loading />}
      {data && (
        <>
          <dl className="space-y-3">
            {rows.map((row) => {
              const planned = row.planned === null ? 0 : Number(row.planned);
              return (
                <div key={row.label}>
                  <div className="flex items-baseline justify-between gap-3 text-sm">
                    <dt className="text-slate-600">{row.label}</dt>
                    <dd className="num text-slate-900">
                      <span className="font-semibold">{formatNumber(row.eaten, 0)}</span>
                      {row.planned !== null && <span className="text-slate-500"> из {formatNumber(row.planned, 0)}</span>}{" "}
                      <span className="text-slate-500">{row.unit}</span>
                    </dd>
                  </div>
                  {planned > 0 && (
                    <div className="mt-1.5">
                      <ProgressBar
                        value={Number(row.eaten) / planned}
                        tone={Number(row.eaten) > planned * 1.1 ? "amber" : "brand"}
                        label={`${row.label}: съедено ${formatNumber(row.eaten, 0)} из ${formatNumber(planned, 0)} ${row.unit}`}
                      />
                    </div>
                  )}
                </div>
              );
            })}
          </dl>
          <p className="mt-4 text-xs text-slate-500">
            {hasPlan ? (
              "Съедено фактически из запланированного на сегодня."
            ) : (
              <>
                На сегодня плана нет: показано, сколько съедено.{" "}
                <Link href="/meal-plan" className="font-medium text-brand-700 underline underline-offset-2">
                  Составить план
                </Link>
              </>
            )}
          </p>
        </>
      )}
    </Card>
  );
}

/** Ближайшая запланированная тренировка, которая ещё не закончилась. */
function TrainingBlock({ onHide }: { onHide: () => void }) {
  const { profile } = useProfile();
  const userId = profile.id;
  const load = useCallback(() => getTrainingSessions(userId), [userId]);
  const { data, error, reload } = useAsyncData(load);

  const next =
    data
      ?.filter((session) => session.status === "planned" && isFuture(session.end_at))
      .sort((a, b) => new Date(a.start_at).getTime() - new Date(b.start_at).getTime())[0] ?? null;

  return (
    <Card title="Ближайшая тренировка" action={<BlockActions href="/training" onHide={onHide} />}>
      {error && <ErrorBanner message={error} onRetry={reload} />}
      {data === null && !error && <Loading />}
      {data && !next && (
        <EmptyState title="Тренировок в плане нет">
          <Link href="/training" className="font-medium text-brand-700 underline underline-offset-2">
            Запланировать
          </Link>
          , и она появится здесь.
        </EmptyState>
      )}
      {next && (
        <>
          <p className="font-display text-xl font-semibold text-slate-900">{next.name}</p>
          <p className="num mt-2 text-sm text-slate-600">
            {formatDateTime(next.start_at)} – {formatTime(next.end_at)}
          </p>
          <div className="mt-3">
            <Badge tone={SESSION_STATUS_TONES[next.status]}>{SESSION_STATUS_LABELS[next.status]}</Badge>
          </div>
        </>
      )}
    </Card>
  );
}

/** Темп словами: −0,5 → «−0,5 кг в неделю». */
function formatRate(value: string): string {
  const number = Number(value);
  const sign = number > 0 ? "+" : number < 0 ? "−" : "";
  return `${sign}${formatNumber(Math.abs(number), 2)} кг в неделю`;
}

/**
 * Вес и цель по весу: текущий вес, целевой, намеченный темп и короткий статус — держится ли человек темпа.
 * Темп здесь не считается: статус и цифры приходят из раздела «Нормы и цели» (GET /goals/progress).
 */
function WeightBlock({ onHide }: { onHide: () => void }) {
  const { profile } = useProfile();
  const userId = profile.id;
  const load = useCallback(() => getGoalProgress(userId), [userId]);
  const { data, error, reload } = useAsyncData(load);

  // Первая активная цель с целевым весом, а если такой нет — первая активная
  const progress = data?.find((item) => item.target_weight_kg !== null) ?? data?.[0] ?? null;

  return (
    <Card title="Вес" action={<BlockActions href="/progress" onHide={onHide} />}>
      {error && <ErrorBanner message={error} onRetry={reload} />}
      {data === null && !error && <Loading />}
      {data && !progress && (
        <EmptyState title="Цель по весу не задана">
          <Link href="/norms" className="font-medium text-brand-700 underline underline-offset-2">
            Задать цель
          </Link>
          , и здесь появятся темп и прогресс.
        </EmptyState>
      )}
      {progress && (
        <>
          <p className="text-sm text-slate-500">{GOAL_TYPE_LABELS[progress.goal_type]}</p>
          <div className="mt-3 grid grid-cols-2 gap-3">
            <div className="rounded-xl bg-slate-50 px-4 py-3">
              <p className="text-xs text-slate-500">Сейчас</p>
              <p className="num mt-0.5 text-xl font-semibold text-slate-900">{formatKg(progress.current_weight_kg)}</p>
            </div>
            <div className="rounded-xl bg-slate-50 px-4 py-3">
              <p className="text-xs text-slate-500">Цель</p>
              <p className="num mt-0.5 text-xl font-semibold text-slate-900">{formatKg(progress.target_weight_kg)}</p>
            </div>
          </div>
          <p className="mt-3 text-sm text-slate-600">
            Намеченный темп:{" "}
            <span className="num font-medium text-slate-900">
              {progress.desired_rate_kg_per_week !== null
                ? `${formatNumber(Number(progress.desired_rate_kg_per_week), 2)} кг в неделю`
                : "не задан"}
            </span>
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <Badge tone={GOAL_PROGRESS_TONES[progress.status]}>{GOAL_PROGRESS_LABELS[progress.status]}</Badge>
            {progress.actual_rate_kg_per_week !== null && (
              <span className="num text-xs text-slate-500">сейчас {formatRate(progress.actual_rate_kg_per_week)}</span>
            )}
          </div>
        </>
      )}
    </Card>
  );
}
