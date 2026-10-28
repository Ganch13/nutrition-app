"use client";

import { useState } from "react";
import { Button, ErrorBanner, Segmented, SelectField, TextField } from "@/components/ui";
import { getErrorText } from "@/lib/api";
import { createRecurringRule, updateRecurringRule } from "@/lib/endpoints";
import { optionalText } from "@/lib/format";
import type { FinanceCategory, FinanceKind, Ledger, RecurringRule, RuleFrequency } from "@/lib/types";
import { describeSchedule, FREQUENCY_OPTIONS } from "./shared";

/** День месяца из даты "2026-11-10" → 10. */
function dayOf(date: string): number {
  return Number(date.slice(8, 10));
}

/**
 * Второй день «два раза в месяц» для формы изменения. Ближайшая дата может прийтись на любой из двух дней,
 * поэтому второй — тот из дней правила, что не совпадает с днём ближайшей даты.
 * Пример: правило 10-го и 25-го, ближайшая дата 25 ноября → 10.
 */
function otherDay(rule: RecurringRule | undefined, startOn: string): string {
  if (!rule || rule.frequency !== "semimonthly" || rule.second_day_of_month === null) return "";
  const days = [rule.day_of_month, rule.second_day_of_month];
  const other = days.find((day) => day !== dayOf(startOn));
  return String(other ?? rule.second_day_of_month);
}

/**
 * Форма повторяющегося дохода или обязательного платежа: создание (rule не передан) и изменение.
 *
 * Что человек задаёт: название, сумму, как часто повторяется и дату ближайшего срабатывания.
 * Для «два раза в месяц» — ещё второй день месяца (аванс 10-го и зарплата 25-го).
 * Основной или дополнительный: бюджетный период длится от одного основного дохода до следующего;
 * дополнительные (мелкие, нерегулярные) в границы не входят, но учитываются в сумме периода.
 * Доход сам не начисляется: приложение спросит «Поступил ли платёж?». Дату окончания и автосписание
 * можно задать только платежу (например, последний платёж по кредиту).
 * День месяца берётся из выбранной даты: для «каждый месяц» и даты 10 ноября платёж будет 10-го числа.
 * today — сегодняшняя дата; onDone — вызывается после сохранения; onCancel — закрыть форму.
 */
export default function RuleForm({
  ledger,
  kind,
  rule,
  categories,
  today,
  onDone,
  onCancel,
}: {
  ledger: Ledger;
  kind: FinanceKind;
  rule?: RecurringRule;
  categories: FinanceCategory[];
  today: string;
  onDone: () => void;
  onCancel: () => void;
}) {
  const income = kind === "income";
  const initialStart = rule?.next_due_on ?? rule?.start_on ?? today;
  const [name, setName] = useState(rule?.name ?? "");
  const [amount, setAmount] = useState(rule ? String(Number(rule.amount)) : "");
  const [frequency, setFrequency] = useState<RuleFrequency>(rule?.frequency ?? "monthly");
  const [startOn, setStartOn] = useState(initialStart);
  const [secondDay, setSecondDay] = useState(() => otherDay(rule, initialStart));
  const [endOn, setEndOn] = useState(rule?.end_on ?? "");
  // Автосписание бывает только у платежей; по умолчанию выключено
  const [autoPost, setAutoPost] = useState(rule?.auto_post ?? false);
  const [primary, setPrimary] = useState(rule?.is_primary ?? true);
  const [categoryId, setCategoryId] = useState(rule ? String(rule.category_id) : "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const semimonthly = frequency === "semimonthly";

  // Категории этого вида; пустое значение значит «подобрать автоматически»
  const categoryOptions: [string, string][] = [
    ["", income ? "Автоматически («Зарплата»)" : "Автоматически («Обязательные платежи»)"],
    ...categories.filter((category) => category.kind === kind).map((category): [string, string] => [String(category.id), category.name]),
  ];

  // Как правило будет выглядеть словами, например «два раза в месяц, 10-го и 25-го»
  const preview =
    startOn === ""
      ? null
      : describeSchedule({
          frequency,
          start_on: startOn,
          day_of_month: frequency === "monthly" || semimonthly ? dayOf(startOn) : null,
          second_day_of_month: semimonthly && secondDay !== "" ? Number(secondDay) : null,
        });

  /** Создаёт или обновляет правило и сообщает странице, что данные изменились. */
  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    const value = Number(amount.replace(",", "."));
    if (!Number.isFinite(value) || value <= 0) {
      setError("Сумма должна быть больше нуля.");
      return;
    }
    const second = Number(secondDay);
    if (semimonthly && (!Number.isInteger(second) || second < 1 || second > 31)) {
      setError("Укажите второй день месяца: число от 1 до 31.");
      return;
    }
    if (semimonthly && second === dayOf(startOn)) {
      setError("Второй день месяца должен отличаться от дня ближайшей даты.");
      return;
    }
    if (!income && endOn !== "" && endOn < startOn) {
      setError("Дата окончания не может быть раньше даты начала.");
      return;
    }

    // День месяца указывается только для ежемесячных правил; для остальных его быть не должно
    const dayOfMonth = frequency === "monthly" || semimonthly ? dayOf(startOn) : null;
    const schedule = {
      name: name.trim(),
      amount: value,
      frequency,
      start_on: startOn,
      day_of_month: dayOfMonth,
      second_day_of_month: semimonthly ? second : null,
      is_primary: primary,
      // Доход: без даты окончания и без автоначисления
      end_on: income ? null : optionalText(endOn),
      auto_post: income ? false : autoPost,
    };

    setSaving(true);
    try {
      if (rule) {
        await updateRecurringRule(ledger.id, rule.id, {
          ...schedule,
          ...(categoryId !== "" ? { category_id: Number(categoryId) } : {}),
        });
      } else {
        await createRecurringRule(ledger.id, {
          kind,
          ...schedule,
          category_id: categoryId === "" ? null : Number(categoryId),
        });
      }
      onDone();
    } catch (err) {
      setError(getErrorText(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4 rounded-2xl border border-brand-100 bg-brand-50/40 p-4 sm:p-5">
      <p className="font-medium text-slate-900">
        {rule ? "Изменить" : income ? "Новый повторяющийся доход" : "Новый обязательный платёж"}
      </p>

      <div>
        <Segmented
          label={income ? "Вид дохода" : "Вид платежа"}
          value={primary ? "primary" : "extra"}
          onChange={(value) => setPrimary(value === "primary")}
          options={[
            ["primary", "Основной"],
            ["extra", "Дополнительный"],
          ]}
        />
        <p className="mt-1.5 text-xs text-slate-500">
          {income
            ? primary
              ? "Зарплата, аванс, пенсия. Бюджетный период длится от одного основного дохода до следующего."
              : "Мелкий, необязательный или нерегулярный доход (кэшбэк, подработка). Границ периода не задаёт, но входит в его сумму."
            : primary
              ? "Аренда, кредит, коммуналка: то, что нельзя пропустить."
              : "Небольшие или необязательные платежи: подписки, кружки, взносы."}
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <TextField
          label="Название"
          value={name}
          onChange={setName}
          required
          maxLength={100}
          placeholder={income ? "Аванс, зарплата, аренда квартиры" : "Аренда, кредит, коммуналка"}
        />
        <TextField label="Сумма" type="number" inputMode="decimal" min={0.01} step="0.01" value={amount} onChange={setAmount} required />
        <SelectField
          label="Как часто"
          value={frequency}
          onChange={(value) => setFrequency(value as RuleFrequency)}
          options={FREQUENCY_OPTIONS}
          hint={
            frequency === "biweekly"
              ? "Сумма в месяц не пересчитывается: в месяце бывает то две, то три выплаты."
              : semimonthly
                ? "Сумма указывается за одну выплату."
                : undefined
          }
        />
        <TextField
          label={semimonthly ? "Ближайшая дата (первый день)" : "Ближайшая дата"}
          type="date"
          value={startOn}
          onChange={setStartOn}
          required
          hint={
            startOn !== "" && startOn < today
              ? income
                ? "Дата в прошлом: Лад спросит, поступили ли деньги."
                : "Дата в прошлом: платёж появится среди неотмеченных."
              : (preview ?? undefined)
          }
        />
        {semimonthly && (
          <TextField
            label="Второй день месяца"
            type="number"
            inputMode="numeric"
            min={1}
            max={31}
            step={1}
            value={secondDay}
            onChange={setSecondDay}
            required
            hint="Например, 25. Если в месяце меньше дней, выплата придётся на последний день."
          />
        )}
        <SelectField label="Категория" value={categoryId} onChange={setCategoryId} options={categoryOptions} />
        {!income && (
          <TextField label="Закончить (необязательно)" type="date" value={endOn} onChange={setEndOn} hint="Например, последний платёж по кредиту" />
        )}
      </div>

      {preview && startOn < today && <p className="text-xs text-slate-500">Повторяется: {preview}.</p>}

      {income ? (
        <p className="text-xs text-slate-500">
          Доход не начисляется сам: за два дня до даты и до двух дней после неё Лад спросит, поступил ли платёж, и
          предложит указать фактическую дату и сумму.
        </p>
      ) : (
        <label className="flex items-start gap-3 text-sm text-slate-700">
          <input
            type="checkbox"
            checked={autoPost}
            onChange={(event) => setAutoPost(event.target.checked)}
            className="mt-0.5 size-5 shrink-0 accent-brand-700"
          />
          <span>
            Списывать автоматически в этот день
            <span className="block text-xs text-slate-500">
              Если выключить, платёж появится в ближайших платежах, и вы отметите «Оплачено», когда заплатите.
            </span>
          </span>
        </label>
      )}

      {error && <ErrorBanner message={error} />}

      <div className="flex flex-wrap gap-3">
        <Button type="submit" loading={saving}>
          {rule ? "Сохранить" : "Добавить"}
        </Button>
        <Button variant="secondary" onClick={onCancel} disabled={saving}>
          Отмена
        </Button>
      </div>
    </form>
  );
}
