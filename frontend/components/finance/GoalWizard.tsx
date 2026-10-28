"use client";

import Link from "next/link";
import { useState } from "react";
import { Icon, type IconName } from "@/components/icons";
import { Button, Card, ErrorBanner, Notice, TextField } from "@/components/ui";
import { getErrorText } from "@/lib/api";
import { createFinanceGoal } from "@/lib/endpoints";
import type { FinanceGoalKind, Ledger } from "@/lib/types";

// Три механики цели: что человек делает и как это считается
const KINDS: { value: FinanceGoalKind; title: string; text: string; icon: IconName }[] = [
  { value: "savings", title: "Накопление", text: "Копите на отпуск, технику или подушку безопасности.", icon: "piggy" },
  { value: "debt", title: "Долг без процентов", text: "Возвращаете занятую сумму: вернули часть, долг уменьшился.", icon: "coin" },
  { value: "loan", title: "Кредит с процентами", text: "Платите раз в месяц. Мы покажем, сколько уходит банку, а сколько на долг.", icon: "trend" },
];

const STEP_TITLES = ["Кто видит цель", "Что за цель", "Параметры"];

/** Название книги для выбора: «Только я» или «Вся семья «Дом»». */
function sharedTitle(ledger: Ledger): string {
  return `Вся семья «${ledger.household_name}»`;
}

/**
 * Мастер создания финансовой цели из трёх шагов:
 *   1) кто видит цель: только вы (личная книга) или вся семья (семейная книга);
 *   2) механика: накопление, долг без процентов или кредит с процентами;
 *   3) параметры: название, суммы, для кредита ещё ставка и день платежа.
 * ledgers — книги пользователя (из них берутся личная и семейные); onCreated — после успешного создания;
 * onCancel — закрыть мастер. Пример: личная копилка «Отпуск» на 200 000 ₽ при 15 000 ₽ уже отложенных.
 */
export default function GoalWizard({
  ledgers,
  onCreated,
  onCancel,
}: {
  ledgers: Ledger[];
  onCreated: () => void;
  onCancel: () => void;
}) {
  const personal = ledgers.find((ledger) => ledger.kind === "personal") ?? null;
  const households = ledgers.filter((ledger) => ledger.kind === "household");

  const [step, setStep] = useState(0);
  // Выбранная книга: id личной или одной из семейных
  const [ledgerId, setLedgerId] = useState<number | null>(personal?.id ?? households[0]?.id ?? null);
  const [kind, setKind] = useState<FinanceGoalKind | null>(null);

  const [name, setName] = useState("");
  const [target, setTarget] = useState("");
  const [start, setStart] = useState("");
  const [rate, setRate] = useState("");
  const [day, setDay] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const ledger = ledgers.find((item) => item.id === ledgerId) ?? null;
  const shared = ledger?.kind === "household";

  // Подписи полей зависят от механики
  const targetLabel =
    kind === "savings" ? "Сколько нужно накопить" : kind === "debt" ? "Сумма долга" : "Остаток основного долга";
  const startLabel = kind === "savings" ? "Уже накоплено" : "Уже выплачено";

  /** Создаёт цель: POST /finance/ledgers/{id}/goals. */
  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!ledger || !kind) return;

    const targetValue = Number(target.replace(",", "."));
    if (!Number.isFinite(targetValue) || targetValue <= 0) {
      setError("Укажите сумму больше нуля.");
      return;
    }
    const startValue = start === "" ? 0 : Number(start.replace(",", "."));
    if (kind !== "loan" && (!Number.isFinite(startValue) || startValue < 0 || startValue > targetValue)) {
      setError(`«${startLabel}» не может быть больше всей суммы.`);
      return;
    }

    setError(null);
    setSaving(true);
    try {
      await createFinanceGoal(ledger.id, {
        kind,
        name: name.trim(),
        target_amount: targetValue,
        ...(kind !== "loan" ? { start_amount: startValue } : {}),
        ...(kind === "loan" ? { interest_rate: Number(rate.replace(",", ".")), payment_day: Number(day) } : {}),
      });
      onCreated();
    } catch (err) {
      setError(getErrorText(err));
      setSaving(false);
    }
  }

  return (
    <Card
      title="Новая цель"
      action={
        <Button size="sm" variant="ghost" onClick={onCancel}>
          Отмена
        </Button>
      }
    >
      {/* Это настоящая последовательность, поэтому шаги пронумерованы */}
      <div className="mb-6">
        <div className="flex gap-1.5" aria-hidden="true">
          {STEP_TITLES.map((title, index) => (
            <span key={title} className={`h-1 flex-1 rounded-full ${index <= step ? "bg-brand-600" : "bg-slate-200"}`} />
          ))}
        </div>
        <p className="mt-2 text-sm text-slate-500">
          Шаг {step + 1} из {STEP_TITLES.length}. <span className="font-medium text-slate-800">{STEP_TITLES[step]}</span>
        </p>
      </div>

      {step === 0 && (
        <div className="space-y-3">
          <ChoiceCard
            icon="user"
            title="Личная цель"
            text="Видите только вы. Подходит для своих накоплений и долгов."
            selected={ledger?.kind === "personal"}
            disabled={!personal}
            onSelect={() => personal && setLedgerId(personal.id)}
          />
          {households.length > 0 ? (
            households.map((household) => (
              <ChoiceCard
                key={household.id}
                icon="users"
                title="Общая цель"
                text={`${sharedTitle(household)} видит цель и вносит свои взносы. Мы покажем, кто сколько добавил.`}
                selected={ledgerId === household.id}
                onSelect={() => setLedgerId(household.id)}
              />
            ))
          ) : (
            <Notice>
              Общие цели ведутся в семейных финансах. Создайте семью на странице{" "}
              <Link href="/family" className="font-medium underline underline-offset-2">
                «Семья»
              </Link>
              , затем включите финансы семьи во вкладке «Настройки».
            </Notice>
          )}
          {!personal && households.length > 0 && (
            <p className="text-sm text-slate-500">Личные финансы не включены: включить их можно во вкладке «Настройки».</p>
          )}
          <div className="pt-2">
            <Button onClick={() => setStep(1)} disabled={!ledger}>
              Дальше
            </Button>
          </div>
        </div>
      )}

      {step === 1 && (
        <div className="space-y-3">
          {KINDS.map((item) => (
            <ChoiceCard
              key={item.value}
              icon={item.icon}
              title={item.title}
              text={item.text}
              selected={kind === item.value}
              onSelect={() => setKind(item.value)}
            />
          ))}
          <div className="flex gap-2 pt-2">
            <Button variant="secondary" onClick={() => setStep(0)}>
              Назад
            </Button>
            <Button onClick={() => setStep(2)} disabled={!kind}>
              Дальше
            </Button>
          </div>
        </div>
      )}

      {step === 2 && kind && ledger && (
        <form onSubmit={handleSubmit} className="space-y-4">
          <TextField
            label="Название"
            value={name}
            onChange={setName}
            required
            maxLength={100}
            placeholder={kind === "savings" ? "Отпуск" : kind === "debt" ? "Долг брату" : "Ипотека"}
          />
          <div className="grid gap-4 sm:grid-cols-2">
            <TextField
              label={targetLabel}
              type="number"
              inputMode="decimal"
              min={0.01}
              step="0.01"
              value={target}
              onChange={setTarget}
              required
              hint={
                kind === "loan"
                  ? "Сколько осталось вернуть банку без процентов. Платежи считаются от этой суммы."
                  : `В валюте книги: ${ledger.currency}.`
              }
            />
            {kind !== "loan" ? (
              <TextField
                label={`${startLabel} (необязательно)`}
                type="number"
                inputMode="decimal"
                min={0}
                step="0.01"
                value={start}
                onChange={setStart}
              />
            ) : (
              <>
                <TextField
                  label="Ставка, % годовых"
                  type="number"
                  inputMode="decimal"
                  min={0}
                  max={1000}
                  step="0.001"
                  value={rate}
                  onChange={setRate}
                  required
                />
                <TextField
                  label="День ежемесячного платежа"
                  type="number"
                  inputMode="numeric"
                  min={1}
                  max={31}
                  value={day}
                  onChange={setDay}
                  required
                  hint="Если в месяце нет такого дня, платёж приходится на последний день."
                />
              </>
            )}
          </div>

          <p className="flex items-center gap-2 text-sm text-slate-500">
            <Icon name={shared ? "users" : "user"} size={16} />
            {shared ? `Цель увидит вся семья «${ledger.household_name}»` : "Цель видите только вы"}
          </p>

          {error && <ErrorBanner message={error} />}

          <div className="flex gap-2">
            <Button variant="secondary" onClick={() => setStep(1)}>
              Назад
            </Button>
            <Button type="submit" loading={saving}>
              Создать цель
            </Button>
          </div>
        </form>
      )}
    </Card>
  );
}

/** Крупный вариант выбора: значок, заголовок и пояснение. Выбранный подсвечен рамкой. */
function ChoiceCard({
  icon,
  title,
  text,
  selected,
  disabled,
  onSelect,
}: {
  icon: IconName;
  title: string;
  text: string;
  selected: boolean;
  disabled?: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      disabled={disabled}
      aria-pressed={selected}
      className={`flex w-full items-start gap-4 rounded-2xl border p-4 text-left transition disabled:cursor-not-allowed disabled:opacity-50 ${
        selected ? "border-brand-600 bg-brand-50 ring-2 ring-brand-600/20" : "border-slate-200 bg-white hover:border-slate-300"
      }`}
    >
      <span
        className={`flex size-10 shrink-0 items-center justify-center rounded-xl ${
          selected ? "bg-brand-700 text-white" : "bg-slate-100 text-slate-600"
        }`}
      >
        <Icon name={icon} size={22} />
      </span>
      <span className="min-w-0">
        <span className="block font-medium text-slate-900">{title}</span>
        <span className="mt-0.5 block text-sm text-slate-500">{text}</span>
      </span>
    </button>
  );
}
