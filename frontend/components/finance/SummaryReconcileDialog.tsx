"use client";

import { useEffect, useRef } from "react";
import { Button, ErrorBanner } from "@/components/ui";
import { formatMoney, formatWeekdayDayMonth } from "@/lib/format";
import type { ExpenseSummaryCheck } from "@/lib/types";
import { formatPeriod } from "./shared";

// Сколько найденных расходов перечислять в окне; остальные — «и ещё N»
const SHOWN_MATCHES = 8;

/**
 * Окно сверки сводки: «За этот период уже записано 4 450 ₽, сводка на 9 200 ₽. Это дополнение или повтор?»
 * Приложение само ничего не складывает и не удаляет — решает человек:
 *   * «Добавить как дополнение» → onAdd (ничего не удаляется);
 *   * «Это повтор, заменить»   → onReplace (удаляются ровно показанные здесь расходы);
 *   * «Отмена»                  → onCancel (ничего не сохраняется).
 * check — ответ сверки сервера; busy — идёт сохранение; error — текст ошибки сохранения.
 */
export default function SummaryReconcileDialog({
  check,
  currency,
  busy,
  error,
  onAdd,
  onReplace,
  onCancel,
}: {
  check: ExpenseSummaryCheck;
  currency: string;
  busy: boolean;
  error: string | null;
  onAdd: () => void;
  onReplace: () => void;
  onCancel: () => void;
}) {
  const money = (value: string | number) => formatMoney(value, currency);
  const dialogRef = useRef<HTMLDivElement>(null);

  // Фокус в окно и закрытие по Escape (= «Отмена»)
  useEffect(() => {
    dialogRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onCancel();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onCancel]);

  const hidden = check.matches.length - SHOWN_MATCHES;

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-brand-950/40 sm:items-center sm:p-6">
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="summary-reconcile-title"
        tabIndex={-1}
        className="max-h-[90dvh] w-full max-w-md overflow-y-auto rounded-t-3xl bg-white p-5 shadow-xl outline-none sm:rounded-3xl sm:p-6"
        style={{ paddingBottom: "max(1.25rem, env(safe-area-inset-bottom))" }}
      >
        <p className="text-xs font-medium text-slate-500">Сводка за {formatPeriod(check.period_start, check.period_end)}</p>
        <h2 id="summary-reconcile-title" className="mt-1 font-display text-2xl font-semibold text-slate-900">
          Это дополнение или повтор?
        </h2>
        <p className="mt-2 text-sm text-slate-700">
          За этот период уже записано{" "}
          <span className="num font-semibold text-slate-900">{money(check.existing_total)}</span> ({check.existing_count} шт.),
          сводка на <span className="num font-semibold text-slate-900">{money(check.summary_total)}</span>.
        </p>

        <ul className="mt-4 divide-y divide-slate-100 rounded-2xl bg-slate-50 px-4">
          {check.matches.slice(0, SHOWN_MATCHES).map((match) => (
            <li key={match.transaction_id} className="flex items-center justify-between gap-3 py-2 text-sm">
              <div className="min-w-0">
                <p className="truncate font-medium text-slate-900">{match.category_name}</p>
                <p className="truncate text-xs text-slate-500">
                  {formatWeekdayDayMonth(match.occurred_on)}
                  {match.summary_id !== null ? " · прежняя сводка" : ""}
                  {match.description ? ` · ${match.description}` : ""}
                </p>
              </div>
              <p className="num shrink-0 font-semibold text-slate-900">{money(match.amount)}</p>
            </li>
          ))}
          {hidden > 0 && <li className="py-2 text-xs text-slate-500">и ещё {hidden}</li>}
        </ul>

        {error && (
          <div className="mt-4">
            <ErrorBanner message={error} />
          </div>
        )}

        <div className="mt-5 grid gap-3">
          <Button onClick={onAdd} loading={busy}>
            Добавить как дополнение
          </Button>
          <Button variant="danger" onClick={onReplace} disabled={busy}>
            Это повтор, заменить
          </Button>
          <Button variant="ghost" onClick={onCancel} disabled={busy}>
            Отмена
          </Button>
        </div>
        <p className="mt-4 text-xs text-slate-500">
          «Дополнение» — сводка добавится, записанное останется. «Повтор» — показанные выше расходы удалятся, вместо них
          будет сводка. «Отмена» — ничего не сохраняется.
        </p>
      </div>
    </div>
  );
}
