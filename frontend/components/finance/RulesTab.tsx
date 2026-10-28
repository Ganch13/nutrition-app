"use client";

import { useCallback, useState } from "react";
import { Badge, Button, Card, EmptyState, ErrorBanner, Loading } from "@/components/ui";
import { getErrorText } from "@/lib/api";
import { deleteRecurringRule, getFinanceCategories, getRecurringRules, updateRecurringRule } from "@/lib/endpoints";
import { formatMoney, formatWeekdayDayMonth, todayInZone } from "@/lib/format";
import { useProfile } from "@/lib/profile-context";
import type { FinanceKind, Ledger, RecurringRule } from "@/lib/types";
import { useAsyncData } from "@/lib/use-async-data";
import RuleForm from "./RuleForm";
import { describeSchedule } from "./shared";

/**
 * Вкладка «Платежи и доходы»: повторяющиеся поступления (зарплата, аванс, аренда) и обязательные платежи
 * (аренда жилья, кредиты, коммуналка, подписки). Их даты используются в бюджете: из них складываются
 * бюджетные периоды, ближайшие платежи и оценка финансовой нагрузки.
 * В каждом разделе сначала основные, затем дополнительные: границы периода задают только основные доходы.
 * Менять правила может тот, кто их создал, а также владелец и администратор семьи.
 */
export default function RulesTab({ ledger }: { ledger: Ledger }) {
  const { profile } = useProfile();
  const today = todayInZone(profile.timezone);

  const load = useCallback(async () => {
    const [rules, categories] = await Promise.all([getRecurringRules(ledger.id), getFinanceCategories(ledger.id)]);
    return { rules, categories };
  }, [ledger.id]);
  const { data, error, reload } = useAsyncData(load);

  // Какая форма открыта: «добавить доход», «добавить платёж» или «изменить правило с таким id»
  const [adding, setAdding] = useState<FinanceKind | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  if (error && data === null) return <ErrorBanner message={error} onRetry={reload} />;
  if (data === null) return <Loading />;

  /** Выполняет действие над правилом и обновляет список. */
  async function run(ruleId: number, action: () => Promise<unknown>) {
    setActionError(null);
    setBusyId(ruleId);
    try {
      await action();
      setDeletingId(null);
      reload();
    } catch (err) {
      setActionError(getErrorText(err));
    } finally {
      setBusyId(null);
    }
  }

  /** Закрывает формы и обновляет список после сохранения. */
  function finished() {
    setAdding(null);
    setEditingId(null);
    reload();
  }

  const money = (value: string | number) => formatMoney(value, ledger.currency);

  /** Карточка одного вида: «Доходы» или «Обязательные платежи». Вызывается как функция, а не как компонент: так поля форм не сбрасываются при обновлении страницы. */
  const renderSection = ({ kind, title, description, emptyTitle, emptyText }: {
    kind: FinanceKind;
    title: string;
    description: string;
    emptyTitle: string;
    emptyText: string;
  }) => {
    // Основные первыми, дополнительные следом; внутри порядок сервера (по ближайшей дате)
    const rules = data.rules
      .filter((rule) => rule.kind === kind)
      .sort((a, b) => Number(b.is_primary) - Number(a.is_primary));
    const active = rules.filter((rule) => rule.is_active);
    // Сумма в месяц по действующим правилам: «140 000 ₽ в месяц». Выплаты раз в две недели не пересчитываются
    const monthly = active.reduce((sum, rule) => sum + Number(rule.monthly_amount ?? 0), 0);
    const hasBiweekly = active.some((rule) => rule.monthly_amount === null);
    const firstExtraId = rules.find((rule) => !rule.is_primary)?.id ?? null;

    return (
      <Card
        title={title}
        description={description}
        action={
          adding !== kind && (
            <Button size="sm" variant="secondary" onClick={() => { setAdding(kind); setEditingId(null); }}>
              Добавить
            </Button>
          )
        }
      >
        {monthly > 0 && (
          <p className="mb-4 text-sm text-slate-600">
            <span className="num font-semibold text-slate-900">{money(monthly)}</span> в месяц
            {hasBiweekly && " без учёта выплат раз в две недели"}
          </p>
        )}

        {adding === kind && (
          <div className="mb-4">
            <RuleForm ledger={ledger} kind={kind} categories={data.categories} today={today} onDone={finished} onCancel={() => setAdding(null)} />
          </div>
        )}

        {rules.length === 0 && adding !== kind && <EmptyState title={emptyTitle}>{emptyText}</EmptyState>}

        <ul className="divide-y divide-slate-100">
          {rules.map((rule) => {
            // Подзаголовок перед первым дополнительным правилом
            const extraHeading =
              rule.id === firstExtraId ? (
                <p className="pb-1 pt-5 text-xs font-medium uppercase tracking-wide text-slate-500">Дополнительные</p>
              ) : null;
            if (editingId === rule.id) {
              return (
                <li key={rule.id} className="py-4">
                  {extraHeading}
                  <RuleForm ledger={ledger} kind={kind} rule={rule} categories={data.categories} today={today} onDone={finished} onCancel={() => setEditingId(null)} />
                </li>
              );
            }
            return (
              <li key={rule.id} className="py-4">
                {extraHeading}
                <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
                  <div className="min-w-0">
                    <p className="font-medium text-slate-900">{rule.name}</p>
                    <p className="mt-0.5 text-sm text-slate-500">{describeSchedule(rule)}</p>
                    {rule.is_active && (
                      <p className="text-sm text-slate-500">
                        {rule.next_due_on ? `Ближайшая дата: ${formatWeekdayDayMonth(rule.next_due_on)}` : "Больше не повторяется"}
                      </p>
                    )}
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {!rule.is_active && <Badge tone="amber">На паузе</Badge>}
                      {rule.is_primary ? <Badge tone="green">Основной</Badge> : <Badge>Дополнительный</Badge>}
                      {kind === "income" && rule.is_primary && <Badge>Начинает новый период</Badge>}
                      {rule.auto_post && <Badge>Списывается само</Badge>}
                    </div>
                  </div>
                  <div className="text-right">
                    <p className={`num text-lg font-semibold ${kind === "income" ? "text-good-700" : "text-slate-900"}`}>{money(rule.amount)}</p>
                    {rule.frequency !== "monthly" && rule.monthly_amount !== null && (
                      <p className="num text-xs text-slate-500">
                        {rule.frequency === "semimonthly" ? "" : "≈ "}
                        {money(rule.monthly_amount)} в месяц
                      </p>
                    )}
                  </div>
                </div>

                {rule.can_edit && (
                  deletingId === rule.id ? (
                    <div className="mt-3 flex flex-wrap items-center gap-3 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">
                      <span>Удалить «{rule.name}»? Уже отмеченные операции останутся в списке.</span>
                      <Button size="sm" variant="danger-solid" loading={busyId === rule.id} onClick={() => run(rule.id, () => deleteRecurringRule(ledger.id, rule.id))}>
                        Удалить
                      </Button>
                      <Button size="sm" variant="secondary" onClick={() => setDeletingId(null)}>
                        Отмена
                      </Button>
                    </div>
                  ) : (
                    <div className="-ml-3 mt-1 flex flex-wrap gap-1">
                      <Button size="sm" variant="ghost" onClick={() => { setEditingId(rule.id); setAdding(null); }}>
                        Изменить
                      </Button>
                      <Button size="sm" variant="ghost" loading={busyId === rule.id} onClick={() => run(rule.id, () => updateRecurringRule(ledger.id, rule.id, { is_active: !rule.is_active }))}>
                        {rule.is_active ? "Пауза" : "Возобновить"}
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => setDeletingId(rule.id)}>
                        Удалить
                      </Button>
                    </div>
                  )
                )}
              </li>
            );
          })}
        </ul>
      </Card>
    );
  };

  return (
    <div className="space-y-6">
      {(error || actionError) && <ErrorBanner message={(actionError ?? error) as string} onRetry={error ? reload : undefined} />}
      {renderSection({
        kind: "income",
        title: "Повторяющиеся доходы",
        description:
          "Зарплата, аванс, пенсия. Бюджетный период длится от одного основного дохода до следующего. Поступление нужно подтвердить: Лад спросит о нём сам.",
        emptyTitle: "Доходов пока нет",
        emptyText: "Добавьте зарплату или аванс: по ним считается, сколько можно тратить.",
      })}
      {renderSection({
        kind: "expense",
        title: "Обязательные платежи",
        description: "Аренда, кредиты, коммуналка — основные; подписки и мелкие взносы — дополнительные. Их даты учитываются в бюджете.",
        emptyTitle: "Обязательных платежей пока нет",
        emptyText: "Добавьте платежи, которые нельзя пропустить: так видно, сколько денег действительно свободно.",
      })}
    </div>
  );
}
