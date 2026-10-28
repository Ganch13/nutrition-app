"use client";

import { useState } from "react";
import { Badge, Button, Card, ErrorBanner, ProgressBar, TextField, type Tone } from "@/components/ui";
import { getErrorText } from "@/lib/api";
import { simulateLoad } from "@/lib/endpoints";
import { formatMoney } from "@/lib/format";
import type { Ledger, LoadReport, LoadSimulation } from "@/lib/types";
import { AdviceList, Stat } from "./shared";

const STATUS: Record<LoadReport["status"], { label: string; tone: Tone }> = {
  no_income: { label: "Нет данных о доходе", tone: "slate" },
  comfortable: { label: "Нагрузка комфортная", tone: "green" },
  moderate: { label: "Нагрузка умеренная", tone: "green" },
  high: { label: "Нагрузка высокая", tone: "amber" },
  critical: { label: "Нагрузка критическая", tone: "red" },
};

const VERDICT_STYLE = {
  ok: "border-good-100 bg-good-50 text-good-800",
  risky: "border-amber-200 bg-amber-50 text-amber-800",
  not_recommended: "border-red-100 bg-red-50 text-red-700",
};

/**
 * «Финансовая нагрузка»: какую часть среднего месячного дохода съедают обязательные платежи,
 * сколько остаётся и можно ли взять ещё один платёж (кредит, рассрочку). Ниже калькулятор:
 * вводите сумму платежа и сразу видите, что станет с нагрузкой. Ничего не записывается, это только расчёт.
 * onAddRules — перейти на вкладку, где добавляются доходы и платежи.
 */
export default function LoadCard({
  ledger,
  load,
  onAddRules,
}: {
  ledger: Ledger;
  load: LoadReport;
  onAddRules: () => void;
}) {
  const money = (value: string | number) => formatMoney(value, ledger.currency);
  const status = STATUS[load.status];

  const [payment, setPayment] = useState("");
  const [result, setResult] = useState<LoadSimulation | null>(null);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /** Считает, что будет с нагрузкой, если взять ещё один ежемесячный платёж. */
  async function handleSimulate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = Number(payment.replace(",", "."));
    if (!Number.isFinite(value) || value <= 0) {
      setError("Введите сумму платежа больше нуля.");
      return;
    }
    setError(null);
    setChecking(true);
    try {
      setResult(await simulateLoad(ledger.id, value));
    } catch (err) {
      setError(getErrorText(err));
    } finally {
      setChecking(false);
    }
  }

  const share = load.mandatory_share;

  return (
    <Card
      title="Финансовая нагрузка"
      description="Сколько дохода уходит на обязательные платежи и можно ли брать ещё."
      action={<Badge tone={status.tone}>{status.label}</Badge>}
    >
      {load.status === "no_income" ? (
        <div className="space-y-3 text-sm text-slate-600">
          <p>Чтобы оценить нагрузку, добавьте повторяющийся доход (например, зарплату) и обязательные платежи.</p>
          <Button variant="secondary" onClick={onAddRules}>
            Добавить доход и платежи
          </Button>
        </div>
      ) : (
        <div className="space-y-6">
          <div>
            <div className="mb-2 flex items-baseline justify-between gap-3">
              <p className="text-sm text-slate-600">Обязательные платежи от дохода</p>
              <p className="figure num text-2xl text-slate-900">{share === null ? "—" : `${Math.round(share)} %`}</p>
            </div>
            <ProgressBar
              label="Доля обязательных платежей в доходе"
              value={share === null ? 0 : share / 100}
              tone={load.status === "critical" ? "red" : load.status === "high" ? "amber" : "brand"}
            />
          </div>

          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Stat label="Доход в месяц" value={money(load.income_monthly)} />
            <Stat label="Обязательные в месяц" value={money(load.mandatory_monthly)} />
            <Stat label="Свободно в месяц" value={money(load.free_monthly)} tone={Number(load.free_monthly) < 0 ? "bad" : "default"} />
            <Stat label="Можно добавить платёж" value={money(load.safe_extra_payment)} note="и остаться в пределах 50 % дохода" />
          </div>

          {load.left_after_expenses !== null && load.avg_other_expense_monthly !== null && (
            <p className="text-sm text-slate-600">
              Обычные траты в среднем {money(load.avg_other_expense_monthly)} в месяц, после них остаётся{" "}
              <span className={`num font-medium ${Number(load.left_after_expenses) < 0 ? "text-red-600" : "text-slate-900"}`}>
                {money(load.left_after_expenses)}
              </span>
              .
            </p>
          )}

          <p className="text-sm text-slate-600">
            Подушка безопасности: {money(load.emergency_fund_target)} (три месяца обязательных платежей).
          </p>

          <AdviceList items={load.advice} />

          {load.mandatory_items.length > 0 && (
            <details className="group rounded-xl border border-slate-200 px-4 py-3 text-sm">
              <summary className="cursor-pointer font-medium text-slate-700">Из чего состоят обязательные платежи</summary>
              <ul className="mt-3 divide-y divide-slate-100">
                {load.mandatory_items.map((item) => (
                  <li key={item.name} className="flex justify-between gap-3 py-2">
                    <span>{item.name}</span>
                    <span className="num text-slate-600">{money(item.monthly_amount)} в месяц</span>
                  </li>
                ))}
              </ul>
            </details>
          )}

          <form onSubmit={handleSimulate} className="space-y-3 rounded-xl bg-slate-50 p-4">
            <p className="font-medium text-slate-900">Можно ли взять ещё один платёж?</p>
            <div className="grid gap-3 sm:grid-cols-[1fr_auto] sm:items-end">
              <TextField
                label="Платёж в месяц"
                type="number"
                inputMode="decimal"
                min={0.01}
                step="0.01"
                value={payment}
                onChange={setPayment}
                placeholder="Например, 15000"
                required
                hint="Кредит, рассрочка, подписка. Расчёт ничего не записывает."
              />
              <Button type="submit" loading={checking}>
                Проверить
              </Button>
            </div>
            {error && <ErrorBanner message={error} />}
            {result && (
              <div className="space-y-3">
                <div className={`rounded-xl border px-4 py-3 text-sm ${VERDICT_STYLE[result.verdict]}`}>
                  <p className="font-semibold">{result.text}</p>
                  <p className="num mt-1">
                    Доля обязательных платежей станет{" "}
                    {result.new_mandatory_share === null ? "—" : `${Math.round(result.new_mandatory_share)} %`}, свободно в
                    месяц {money(result.new_free_monthly)}.
                  </p>
                </div>
                <AdviceList items={result.advice} />
              </div>
            )}
          </form>
        </div>
      )}
    </Card>
  );
}
