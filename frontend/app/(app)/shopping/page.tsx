"use client";

import Link from "next/link";
import { useCallback, useState } from "react";
import {
  Badge,
  Button,
  Card,
  ErrorBanner,
  Loading,
  PageHeader,
  SelectField,
  SuccessNotice,
} from "@/components/ui";
import PeriodNav from "@/components/PeriodNav";
import { getErrorText } from "@/lib/api";
import {
  clearFamilyShoppingChecks,
  clearShoppingChecks,
  getCookingPlan,
  getFamilyCookingPlan,
  getFamilyShoppingList,
  getHouseholds,
  getShoppingList,
  setFamilyShoppingCheck,
  setShoppingCheck,
} from "@/lib/endpoints";
import {
  FOOD_CATEGORY_LABELS,
  formatDayShort,
  formatNumber,
  MEAL_TYPE_LABELS,
  mondayOf,
  shiftDate,
  todayInZone,
} from "@/lib/format";
import { useProfile } from "@/lib/profile-context";
import type { CookingSession, ShoppingItem, ShoppingList } from "@/lib/types";
import { useAsyncData } from "@/lib/use-async-data";

/** Название порции без начальной единицы: "1 яйцо" → "яйцо", "1 ст. л." → "ст. л.". */
function servingLabel(name: string): string {
  return name.replace(/^1\s+/, "");
}

/** Строка с количеством: "480 г · ≈ 4 × шт. (без кожуры)". */
function amountText(item: ShoppingItem): string {
  const grams = `${formatNumber(item.amount_g, 0)} г`;
  if (item.servings !== null && item.serving_name) {
    return `${grams} · ≈ ${formatNumber(item.servings, 1)} × ${servingLabel(item.serving_name)}`;
  }
  return grams;
}

/** Текст списка для отправки в мессенджер: заголовки категорий и строки «• Банан — 480 г». */
function shoppingAsText(list: ShoppingList, isChecked: (item: ShoppingItem) => boolean): string {
  const lines: string[] = [`Закупки ${formatDayShort(list.start)} – ${formatDayShort(list.end)}`];
  let category = "";
  for (const item of list.items) {
    if (isChecked(item)) continue;
    if (item.category !== category) {
      category = item.category;
      lines.push("", `${FOOD_CATEGORY_LABELS[item.category]}:`);
    }
    lines.push(`• ${item.name} — ${amountText(item)}`);
  }
  return lines.join("\n");
}

/** Страница «Закупки и готовка»: список покупок на период и план приготовления блюд. */
export default function ShoppingPage() {
  const { profile } = useProfile();
  const userId = profile.id;
  const today = todayInZone(profile.timezone);

  // Чей список показываем: "me" — мой, число — id домохозяйства (общий список семьи, шаг 69)
  const [scope, setScope] = useState<"me" | number>("me");
  const households = useAsyncData(getHouseholds);

  const [weekStart, setWeekStart] = useState(() => mondayOf(todayInZone(profile.timezone)));
  const [tab, setTab] = useState<"shopping" | "cooking">("shopping");
  const [period, setPeriod] = useState<"week" | "from-today">("week");

  // Сколько дней недели прошло к сегодняшнему дню (для периода «с сегодняшнего дня»)
  const todayIndex = Math.round(
    (new Date(`${today}T00:00:00Z`).getTime() - new Date(`${weekStart}T00:00:00Z`).getTime()) / 86_400_000,
  );
  const fromToday = period === "from-today" && todayIndex >= 0 && todayIndex <= 6;
  const rangeStart = fromToday ? today : weekStart;
  const rangeDays = fromToday ? 7 - todayIndex : 7;

  const loadShopping = useCallback(
    () => (scope === "me" ? getShoppingList(userId, rangeStart, rangeDays) : getFamilyShoppingList(scope, rangeStart, rangeDays)),
    [scope, userId, rangeStart, rangeDays],
  );
  const loadCooking = useCallback(
    () => (scope === "me" ? getCookingPlan(userId, rangeStart, rangeDays) : getFamilyCookingPlan(scope, rangeStart, rangeDays)),
    [scope, userId, rangeStart, rangeDays],
  );
  const shopping = useAsyncData(loadShopping);
  const cooking = useAsyncData(loadCooking);

  // Отметки, поставленные на этом экране, но ещё не подтверждённые перезагрузкой списка
  const [overrides, setOverrides] = useState<Record<string, boolean>>({});
  const [message, setMessage] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const overrideKey = (item: ShoppingItem) => `${scope}|${rangeStart}|${item.key}`;
  const isChecked = (item: ShoppingItem) => overrides[overrideKey(item)] ?? item.checked;

  /** Ставит или снимает отметку «куплено»: экран обновляется сразу, при ошибке отметка возвращается. */
  async function toggle(item: ShoppingItem) {
    const next = !isChecked(item);
    setActionError(null);
    setOverrides((current) => ({ ...current, [overrideKey(item)]: next }));
    try {
      if (scope === "me") await setShoppingCheck(userId, rangeStart, item.key, next);
      else await setFamilyShoppingCheck(scope, rangeStart, item.key, next);
    } catch (err) {
      setOverrides((current) => ({ ...current, [overrideKey(item)]: !next }));
      setActionError(getErrorText(err));
    }
  }

  async function handleClear() {
    if (!window.confirm("Снять все отметки «куплено»?")) return;
    setActionError(null);
    try {
      if (scope === "me") await clearShoppingChecks(userId, rangeStart);
      else await clearFamilyShoppingChecks(scope, rangeStart);
      setOverrides({});
      shopping.reload();
    } catch (err) {
      setActionError(getErrorText(err));
    }
  }

  async function handleCopy(list: ShoppingList) {
    setActionError(null);
    try {
      await navigator.clipboard.writeText(shoppingAsText(list, isChecked));
      setMessage("Список скопирован — его можно вставить в сообщение.");
    } catch {
      setActionError("Не удалось скопировать: браузер не разрешил доступ к буферу обмена.");
    }
  }

  const list = shopping.data;
  const checkedCount = list ? list.items.filter(isChecked).length : 0;

  return (
    <>
      <PageHeader title="Закупки и готовка" subtitle="Что купить и что приготовить по плану питания" />

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <PeriodNav
          title={`${formatDayShort(rangeStart)} – ${formatDayShort(shiftDate(rangeStart, rangeDays - 1))}`}
          prevLabel="Предыдущая неделя"
          nextLabel="Следующая неделя"
          todayLabel="Эта неделя"
          onPrev={() => setWeekStart(shiftDate(weekStart, -7))}
          onNext={() => setWeekStart(shiftDate(weekStart, 7))}
          onToday={() => setWeekStart(mondayOf(today))}
          todayDisabled={weekStart === mondayOf(today)}
        />
      </div>

      {households.data && households.data.length > 0 && (
        <div className="mb-4 max-w-md">
          <SelectField
            label="Чей список"
            value={String(scope)}
            onChange={(value) => {
              setOverrides({});
              setMessage(null);
              setActionError(null);
              setScope(value === "me" ? "me" : Number(value));
            }}
            options={[
              ["me", "Мой личный"],
              ...households.data.map((household): [string, string] => [String(household.id), `Семья «${household.name}»`]),
            ]}
          />
        </div>
      )}

      <div className="mb-4 grid gap-3 sm:grid-cols-2">
        <SelectField
          label="Период"
          value={period}
          onChange={(value) => setPeriod(value as "week" | "from-today")}
          options={[
            ["week", "Вся неделя"],
            ...(todayIndex >= 0 && todayIndex <= 6
              ? ([["from-today", "С сегодняшнего дня до конца недели"]] as [string, string][])
              : []),
          ]}
        />
        <div className="flex items-end gap-2">
          <Button variant={tab === "shopping" ? "primary" : "secondary"} onClick={() => setTab("shopping")}>
            Закупки
          </Button>
          <Button variant={tab === "cooking" ? "primary" : "secondary"} onClick={() => setTab("cooking")}>
            Готовка
          </Button>
        </div>
      </div>

      <div className="space-y-4">
        {message && <SuccessNotice message={message} />}
        {actionError && <ErrorBanner message={actionError} />}

        {tab === "shopping" && (
          <>
            {shopping.error && <ErrorBanner message={shopping.error} onRetry={shopping.reload} />}
            {shopping.error && scope !== "me" && <FamilyHint />}
            {shopping.loading && list === null && <Loading />}
            {list && list.items.length === 0 && (
              <Card>
                <p className="text-sm text-slate-600">
                  В плане нет приёмов пищи за этот период (съеденные и пропущенные в закупки не попадают).{" "}
                  <Link href="/meal-plan" className="font-medium text-brand-700 underline underline-offset-2">
                    Составить меню
                  </Link>
                </p>
              </Card>
            )}
            {list && list.items.length > 0 && (
              <Card
                title={`Куплено ${checkedCount} из ${list.items.length}`}
                action={
                  <div className="flex flex-wrap gap-2">
                    <Button variant="secondary" onClick={() => handleCopy(list)}>
                      Скопировать
                    </Button>
                    <Button variant="secondary" onClick={handleClear} disabled={checkedCount === 0}>
                      Сбросить отметки
                    </Button>
                  </div>
                }
              >
                {list.members.length > 0 && (
                  <p className="mb-2 text-sm text-slate-700">Общий список на: {list.members.join(", ")}.</p>
                )}
                <p className="mb-3 text-xs text-slate-500">
                  Учтено приёмов пищи: {list.meals_count}. Количество округлено вверх до грамма; вес — в сыром или сухом виде,
                  как указано в названии.
                </p>
                <ShoppingGroups list={list} isChecked={isChecked} onToggle={toggle} />
              </Card>
            )}
          </>
        )}

        {tab === "cooking" && (
          <>
            {cooking.error && <ErrorBanner message={cooking.error} onRetry={cooking.reload} />}
            {cooking.error && scope !== "me" && <FamilyHint />}
            {cooking.loading && cooking.data === null && <Loading />}
            {cooking.data && cooking.data.sessions.length === 0 && (
              <Card>
                <p className="text-sm text-slate-600">
                  Готовить нечего: в плане нет блюд из рецептов.{" "}
                  <Link href="/meal-plan" className="font-medium text-brand-700 underline underline-offset-2">
                    Составить меню
                  </Link>
                </p>
              </Card>
            )}
            {cooking.data && cooking.data.sessions.length > 0 && (
              <CookingDays sessions={cooking.data.sessions} totalMinutes={cooking.data.total_minutes} />
            )}
          </>
        )}
      </div>
    </>
  );
}

/** Список покупок, сгруппированный по категориям (порядок категорий задаёт сервер). */
function ShoppingGroups({
  list,
  isChecked,
  onToggle,
}: {
  list: ShoppingList;
  isChecked: (item: ShoppingItem) => boolean;
  onToggle: (item: ShoppingItem) => void;
}) {
  const groups: { category: ShoppingItem["category"]; items: ShoppingItem[] }[] = [];
  for (const item of list.items) {
    const last = groups[groups.length - 1];
    if (last && last.category === item.category) last.items.push(item);
    else groups.push({ category: item.category, items: [item] });
  }

  return (
    <div className="space-y-5">
      {groups.map((group) => (
        <section key={group.category}>
          <h3 className="mb-1 text-sm font-bold text-slate-700">{FOOD_CATEGORY_LABELS[group.category]}</h3>
          <ul className="divide-y divide-slate-100">
            {group.items.map((item) => {
              const checked = isChecked(item);
              return (
                <li key={item.key}>
                  <label className="flex cursor-pointer items-start gap-3 py-2.5">
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => onToggle(item)}
                      className="mt-1 h-5 w-5 shrink-0"
                    />
                    <span className={`min-w-0 ${checked ? "text-slate-400 line-through" : ""}`}>
                      <span className="block text-sm font-medium">{item.name}</span>
                      <span className="block text-xs">{amountText(item)}</span>
                      <span className="block text-xs text-slate-400">{item.used_in.join(", ")}</span>
                      {item.members.length > 0 && (
                        <span className="block text-xs text-slate-400">Едят: {item.members.join(", ")}</span>
                      )}
                      {item.checked_by && <span className="block text-xs text-good-700">Отметил: {item.checked_by}</span>}
                    </span>
                  </label>
                </li>
              );
            })}
          </ul>
        </section>
      ))}
    </div>
  );
}

/** План готовки: подходы к плите, сгруппированные по дню приготовления. */
function CookingDays({ sessions, totalMinutes }: { sessions: CookingSession[]; totalMinutes: number }) {
  const days: { date: string; sessions: CookingSession[] }[] = [];
  for (const session of sessions) {
    const last = days[days.length - 1];
    if (last && last.date === session.cook_date) last.sessions.push(session);
    else days.push({ date: session.cook_date, sessions: [session] });
  }

  return (
    <>
      <p className="text-sm text-slate-600">
        Подходов к плите: {sessions.length}, примерно {totalMinutes} мин. Время ориентировочное: время рецепта плюс 5 минут
        на каждую следующую порцию.
      </p>
      {days.map((day) => (
        <Card
          key={day.date}
          title={formatDayShort(day.date)}
          action={<Badge>{day.sessions.reduce((sum, session) => sum + session.estimated_minutes, 0)} мин</Badge>}
        >
          <ul className="space-y-4">
            {day.sessions.map((session) => (
              <CookingSessionCard key={`${session.recipe_id}-${session.meals[0].id}`} session={session} />
            ))}
          </ul>
        </Card>
      ))}
    </>
  );
}

function CookingSessionCard({ session }: { session: CookingSession }) {
  const [open, setOpen] = useState(false);

  return (
    <li className="rounded-xl border border-slate-200 p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="font-medium">{session.recipe_name}</p>
          <p className="text-xs text-slate-500">
            {formatNumber(session.portions, 2)} порц. · {session.estimated_minutes} мин ·{" "}
            {session.cook_when === "evening_before" ? "вечером накануне" : "в день приёма пищи"}
          </p>
        </div>
        <Badge tone="slate">хранится {session.keeps_days} дн.</Badge>
      </div>
      <p className="mt-2 text-xs text-slate-600">
        Для:{" "}
        {session.meals
          .map(
            (meal) =>
              (meal.user_name ? `${meal.user_name}: ` : "") +
              `${formatDayShort(meal.plan_date)}, ${MEAL_TYPE_LABELS[meal.meal_type].toLowerCase()}` +
              (Number(meal.portion_scale) !== 1 ? ` ×${formatNumber(meal.portion_scale, 2)}` : ""),
          )
          .join(" · ")}
      </p>
      <button type="button" onClick={() => setOpen(!open)} className="mt-2 text-xs text-slate-500 underline">
        {open ? "Скрыть" : "Продукты и приготовление"}
      </button>
      {open && (
        <div className="mt-2 space-y-2 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-600">
          <ul className="space-y-0.5">
            {session.ingredients.map((ingredient) => (
              <li key={ingredient.name} className="flex justify-between gap-3">
                <span>{ingredient.name}</span>
                <span className="shrink-0">{formatNumber(ingredient.amount_g, 0)} г</span>
              </li>
            ))}
          </ul>
          {session.instructions && <p className="text-slate-700">{session.instructions}</p>}
        </div>
      )}
    </li>
  );
}

/** Подсказка под ошибкой общего списка: общий план открывается только тем, кто сам включил «Планировать вместе». */
function FamilyHint() {
  return (
    <p className="text-sm text-slate-600">
      Общий список строится по планам тех, кто включил «Планировать вместе».{" "}
      <Link href="/family-menu" className="font-medium text-brand-700 underline underline-offset-2">
        Открыть семейное меню
      </Link>
    </p>
  );
}
