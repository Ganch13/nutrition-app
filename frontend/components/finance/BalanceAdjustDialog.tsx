"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { FINANCE_CHANGED_EVENT } from "@/components/finance/IncomePromptDialog";
import { Button, ErrorBanner, Loading, TextField } from "@/components/ui";
import { getErrorText } from "@/lib/api";
import { deleteBalanceAdjustment, getLedgerBalance, setLedgerBalance } from "@/lib/endpoints";
import { formatDayMonth, formatMoney } from "@/lib/format";
import type { LedgerBalance } from "@/lib/types";
import { useAsyncData } from "@/lib/use-async-data";

// Сколько последних корректировок показывать в окне
const SHOWN_ADJUSTMENTS = 5;

/** Сумма со знаком: "+2 300 ₽" или "−500 ₽". Пример: signedMoney("2300", "RUB") → "+2 300 ₽". */
function signedMoney(value: string | number, currency: string): string {
  const amount = Number(value);
  const text = formatMoney(Math.abs(amount), currency);
  return amount > 0 ? `+${text}` : amount < 0 ? `−${text}` : text;
}

/**
 * Окно «Изменить баланс»: человек вводит, сколько денег на самом деле, без дохода и расхода.
 * Сервер сохраняет разницу с «Балансом» как корректировку; в отчёты о тратах она не попадает.
 *
 * Пример: «Баланс» 50 000 ₽, ввели 52 300 → до сохранения видно «Корректировка: +2 300 ₽»,
 * после сохранения «Баланс» = 52 300 ₽, а главная и раздел финансов обновляются (FINANCE_CHANGED_EVENT).
 * Ниже — последние корректировки, любую можно отменить (сервер проверит права).
 *
 * ledgerId — книга, title — «Личные» или «Семья», currency — "RUB", onClose — закрыть окно.
 */
export default function BalanceAdjustDialog({
  ledgerId,
  title,
  currency,
  onClose,
}: {
  ledgerId: number;
  title: string;
  currency: string;
  onClose: () => void;
}) {
  const load = useCallback(() => getLedgerBalance(ledgerId), [ledgerId]);
  const { data: loaded, error: loadError, reload } = useAsyncData(load);
  // Ответ сервера после сохранения или отмены: свежее, чем загруженный при открытии
  const [fresh, setFresh] = useState<LedgerBalance | null>(null);
  const balance = fresh ?? loaded;

  const [actual, setActual] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const dialogRef = useRef<HTMLDivElement>(null);

  // Фокус в окно и закрытие по Escape
  useEffect(() => {
    dialogRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  // Введённая сумма числом; null — поле пустое или там не число. Пример: "52 300,5" → 52300.5
  const actualNumber = actual.trim() === "" ? null : Number(actual.replace(/\s/g, "").replace(",", "."));
  const valid = actualNumber !== null && Number.isFinite(actualNumber);
  // Разница, которая будет сохранена. Пример: 52300 − 50000 = 2300
  const delta = valid && balance ? Math.round((actualNumber - Number(balance.total)) * 100) / 100 : null;

  /** Выполняет запрос, запоминает новый баланс и сообщает остальным блокам, что деньги изменились. */
  async function run(action: () => Promise<LedgerBalance>) {
    setBusy(true);
    setError(null);
    try {
      setFresh(await action());
      window.dispatchEvent(new Event(FINANCE_CHANGED_EVENT));
      return true;
    } catch (err) {
      setError(getErrorText(err));
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!valid) {
      setError("Введите сумму числом, например 52300.");
      return;
    }
    if (delta === 0) {
      setError("Баланс уже совпадает с введённой суммой.");
      return;
    }
    const ok = await run(() => setLedgerBalance(ledgerId, { actual: actualNumber, note: note.trim() || undefined }));
    if (ok) {
      setSaved(true);
      setActual("");
      setNote("");
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-brand-950/40 sm:items-center sm:p-6" onClick={onClose}>
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="balance-adjust-title"
        tabIndex={-1}
        onClick={(event) => event.stopPropagation()}
        className="max-h-[90dvh] w-full max-w-md overflow-y-auto rounded-t-3xl bg-white p-5 shadow-xl outline-none sm:rounded-3xl sm:p-6"
        style={{ paddingBottom: "max(1.25rem, env(safe-area-inset-bottom))" }}
      >
        <p className="text-xs font-medium text-slate-500">{title}</p>
        <h2 id="balance-adjust-title" className="mt-1 font-display text-2xl font-semibold text-slate-900">
          Изменить баланс
        </h2>
        <p className="mt-1 text-sm text-slate-600">
          Укажите, сколько денег сейчас на самом деле. Разница сохранится как корректировка: доходом или расходом она не
          считается и в отчёты не попадает.
        </p>

        {loadError && (
          <div className="mt-4">
            <ErrorBanner message={loadError} onRetry={reload} />
          </div>
        )}
        {balance === null && !loadError && (
          <div className="mt-4">
            <Loading />
          </div>
        )}

        {balance && (
          <>
            <div className="mt-4 rounded-2xl bg-slate-50 px-4 py-3">
              <p className="text-xs text-slate-500">Сейчас в приложении («Баланс»)</p>
              <p className="figure num mt-0.5 text-2xl text-slate-900">{formatMoney(balance.total, currency)}</p>
            </div>

            {saved && !error && (
              <p role="status" className="mt-3 text-sm font-medium text-good-700">
                Сохранено. «Баланс» теперь {formatMoney(balance.total, currency)}.
              </p>
            )}
            {error && (
              <div className="mt-4">
                <ErrorBanner message={error} />
              </div>
            )}

            <form onSubmit={handleSubmit} className="mt-4 space-y-4">
              <TextField
                label="Сколько сейчас на самом деле"
                type="number"
                inputMode="decimal"
                step="0.01"
                value={actual}
                onChange={(value) => {
                  setActual(value);
                  setSaved(false);
                }}
                hint={
                  delta === null || delta === 0
                    ? "Можно и отрицательную сумму, если ушли в минус"
                    : `Корректировка: ${signedMoney(delta, currency)}`
                }
                required
              />
              <TextField label="Пояснение (необязательно)" value={note} onChange={setNote} maxLength={250} placeholder="Сверка с банком" />
              <div className="flex flex-wrap gap-3">
                <Button type="submit" loading={busy} disabled={!valid || delta === 0}>
                  Сохранить
                </Button>
                <Button variant="secondary" onClick={onClose} disabled={busy}>
                  Закрыть
                </Button>
              </div>
            </form>

            {balance.adjustments.length > 0 && (
              <div className="mt-6">
                <p className="text-sm font-medium text-slate-700">Последние корректировки</p>
                <ul className="mt-2 divide-y divide-slate-100">
                  {balance.adjustments.slice(0, SHOWN_ADJUSTMENTS).map((item) => (
                    <li key={item.id} className="flex items-center justify-between gap-3 py-2 text-sm">
                      <div className="min-w-0">
                        <p className="num font-medium text-slate-900">{signedMoney(item.amount, currency)}</p>
                        <p className="truncate text-xs text-slate-500">
                          {formatDayMonth(item.adjusted_on)} · {item.created_by_name}
                          {item.note && ` · ${item.note}`}
                        </p>
                      </div>
                      <Button
                        size="sm"
                        variant="ghost"
                        disabled={busy}
                        onClick={() => void run(() => deleteBalanceAdjustment(ledgerId, item.id))}
                      >
                        Отменить
                      </Button>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
