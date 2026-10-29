"use client";

import { useEffect, useRef, useState } from "react";
import { Button, ErrorBanner, TextField } from "@/components/ui";
import { getErrorText } from "@/lib/api";
import { confirmOccurrence, getIncomePrompts, skipOccurrence } from "@/lib/endpoints";
import { formatMoney, formatWeekdayDayMonth, todayInZone } from "@/lib/format";
import type { IncomePrompt } from "@/lib/types";
import { useAsyncData } from "@/lib/use-async-data";

// Где в браузере хранится «не спрашивать до…»: { "1:3:2026-10-25": 1761598800000 }.
// Это удобство одного устройства: ответы «да» и «пропустить» сохраняются на сервере для всех
const SNOOZE_KEY = "lad-income-prompt-snooze";

// «Напомнить позже» откладывает вопрос на три часа
const LATER_MS = 3 * 60 * 60 * 1000;

// Как часто перепроверять ожидаемые поступления, пока приложение открыто
const RECHECK_MS = 30 * 60 * 1000;

/**
 * Событие окна: финансы изменились (поступление подтверждено, баланс исправлен, добавлена операция).
 * Главная и разделы могут обновиться.
 */
export const FINANCE_CHANGED_EVENT = "lad:finance-changed";

/** Сообщает всем блокам на странице, что деньги изменились (они перезагрузят свои цифры). */
export function notifyFinanceChanged(): void {
  window.dispatchEvent(new Event(FINANCE_CHANGED_EVENT));
}

/**
 * Перезагружает блок, когда в другом месте изменились деньги (FINANCE_CHANGED_EVENT).
 * Пример: useFinanceChanged(reload) в «Финансы → Обзор» — после «Изменить баланс» цифры периода обновятся сами.
 */
export function useFinanceChanged(reload: () => void): void {
  useEffect(() => {
    window.addEventListener(FINANCE_CHANGED_EVENT, reload);
    return () => window.removeEventListener(FINANCE_CHANGED_EVENT, reload);
  }, [reload]);
}

/** Ключ поступления: книга, правило и плановая дата. */
function promptKey(item: IncomePrompt): string {
  return `${item.ledger_id}:${item.rule_id}:${item.due_on}`;
}

/** Читает отложенные вопросы; просроченные отметки выбрасывает. Хранилище может быть недоступно. */
function readSnoozed(): Record<string, number> {
  try {
    const parsed = JSON.parse(window.localStorage.getItem(SNOOZE_KEY) ?? "{}") as Record<string, number>;
    const now = Date.now();
    return Object.fromEntries(Object.entries(parsed).filter(([, until]) => typeof until === "number" && until > now));
  } catch {
    return {};
  }
}

/** Откладывает вопрос о поступлении до момента until (миллисекунды). */
function snooze(item: IncomePrompt, until: number) {
  try {
    window.localStorage.setItem(SNOOZE_KEY, JSON.stringify({ ...readSnoozed(), [promptKey(item)]: until }));
  } catch {
    // Без хранилища вопрос просто вернётся при следующей проверке
  }
}

/** Начало завтрашнего дня по часам устройства, в миллисекундах. */
function tomorrowStart(): number {
  const date = new Date();
  date.setHours(24, 0, 0, 0);
  return date.getTime();
}

/** Чья книга: «Личные» или «Семья: Дом». */
function ledgerLabel(item: IncomePrompt): string {
  return item.ledger_kind === "personal" ? "Личные" : `Семья: ${item.household_name ?? ""}`;
}

/**
 * Всплывающее окно «Поступил ли платёж?». Доход не начисляется сам: за два дня до плановой даты и до двух дней
 * после неё приложение спрашивает, пришли ли деньги. Окно показывается поверх любой страницы.
 *
 * Ответы:
 *   * «Да» — можно поправить фактическую дату и сумму; создаётся операция дохода;
 *   * «Нет» — деньги ещё не пришли: спросим завтра (пока не закончится окно в два дня после даты);
 *   * «Пропустить» — этой выплаты не будет: она больше не ожидается и не попадает в бюджет;
 *   * «Напомнить позже» — спросим через три часа.
 * zone — часовой пояс профиля для «сегодня».
 */
export default function IncomePromptDialog({ zone }: { zone: string }) {
  const { data, reload } = useAsyncData(getIncomePrompts);
  // Ответы, уже отправленные на сервер, пока список не перезагрузился
  const [answered, setAnswered] = useState<string[]>([]);
  // Меняется при «Нет» и «Напомнить позже», чтобы перечитать отложенные вопросы
  const [, setSnoozeVersion] = useState(0);

  // Перепроверяем раз в полчаса, при возвращении на вкладку и после изменений в финансах
  useEffect(() => {
    const timer = window.setInterval(reload, RECHECK_MS);
    const onVisible = () => {
      if (document.visibilityState === "visible") reload();
    };
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener(FINANCE_CHANGED_EVENT, reload);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener(FINANCE_CHANGED_EVENT, reload);
    };
  }, [reload]);

  if (data === null || data.length === 0) return null;
  const snoozed = readSnoozed();
  const waiting = data.filter((item) => !(promptKey(item) in snoozed) && !answered.includes(promptKey(item)));
  if (waiting.length === 0) return null;
  const current = waiting[0];

  return (
    <PromptCard
      key={promptKey(current)}
      item={current}
      left={waiting.length - 1}
      today={todayInZone(zone)}
      onPostpone={(until) => {
        snooze(current, until);
        setSnoozeVersion((version) => version + 1);
      }}
      onAnswered={() => {
        setAnswered((list) => [...list, promptKey(current)]);
        window.dispatchEvent(new Event(FINANCE_CHANGED_EVENT));
      }}
    />
  );
}

/**
 * Окно с одним вопросом. Своё состояние (форма «Да», ошибка) у каждого вопроса: при переходе
 * к следующему поступлению окно создаётся заново. left — сколько вопросов ещё ждут после этого.
 */
function PromptCard({
  item,
  left,
  today,
  onPostpone,
  onAnswered,
}: {
  item: IncomePrompt;
  left: number;
  today: string;
  onPostpone: (until: number) => void;
  onAnswered: () => void;
}) {
  const [answeringYes, setAnsweringYes] = useState(false);
  const [amount, setAmount] = useState(String(Number(item.planned_amount)));
  // Деньги не могут прийти в будущем: если плановая дата ещё впереди, предлагаем сегодня
  const [date, setDate] = useState(item.due_on <= today ? item.due_on : today);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const dialogRef = useRef<HTMLDivElement>(null);

  // Фокус в окно: клавиатура и экранные дикторы сразу попадают к вопросу
  useEffect(() => {
    dialogRef.current?.focus();
  }, []);

  /** Отправляет ответ на сервер и закрывает вопрос. */
  async function send(action: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await action();
      onAnswered();
    } catch (err) {
      setError(getErrorText(err));
      setBusy(false);
    }
  }

  function handleConfirm(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = Number(amount.replace(",", "."));
    if (!Number.isFinite(value) || value <= 0) {
      setError("Сумма должна быть больше нуля.");
      return;
    }
    if (date === "") {
      setError("Укажите дату поступления.");
      return;
    }
    void send(() => confirmOccurrence(item.ledger_id, item.rule_id, item.due_on, { amount: value, occurred_on: date }));
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-brand-950/40 sm:items-center sm:p-6">
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="income-prompt-title"
        tabIndex={-1}
        className="max-h-[90dvh] w-full max-w-md overflow-y-auto rounded-t-3xl bg-white p-5 shadow-xl outline-none sm:rounded-3xl sm:p-6"
        style={{ paddingBottom: "max(1.25rem, env(safe-area-inset-bottom))" }}
      >
        <p className="text-xs font-medium text-slate-500">
          {ledgerLabel(item)}
          {left > 0 && ` · ещё ${left}`}
        </p>
        <h2 id="income-prompt-title" className="mt-1 font-display text-2xl font-semibold text-slate-900">
          Поступил ли платёж?
        </h2>
        <div className="mt-4 rounded-2xl bg-slate-50 px-4 py-3">
          <p className="font-medium text-slate-900">
            {item.rule_name}
            {!item.is_primary && <span className="ml-2 text-xs font-normal text-slate-500">дополнительный</span>}
          </p>
          <p className="mt-0.5 text-sm text-slate-600">
            Ожидался {formatWeekdayDayMonth(item.due_on)},{" "}
            <span className="num font-semibold text-good-700">{formatMoney(item.planned_amount, item.currency)}</span>
          </p>
        </div>

        {error && (
          <div className="mt-4">
            <ErrorBanner message={error} />
          </div>
        )}

        {answeringYes ? (
          <form onSubmit={handleConfirm} className="mt-4 space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <TextField label="Когда пришли деньги" type="date" value={date} onChange={setDate} max={today} required />
              <TextField
                label="Сколько пришло"
                type="number"
                inputMode="decimal"
                min={0.01}
                step="0.01"
                value={amount}
                onChange={setAmount}
                required
              />
            </div>
            <div className="flex flex-wrap gap-3">
              <Button type="submit" loading={busy}>
                Сохранить
              </Button>
              <Button variant="secondary" onClick={() => setAnsweringYes(false)} disabled={busy}>
                Назад
              </Button>
            </div>
          </form>
        ) : (
          <>
            <div className="mt-5 grid grid-cols-2 gap-3">
              <Button onClick={() => setAnsweringYes(true)} disabled={busy}>
                Да
              </Button>
              <Button variant="secondary" onClick={() => onPostpone(tomorrowStart())} disabled={busy}>
                Нет
              </Button>
              <Button
                variant="ghost"
                loading={busy}
                onClick={() => void send(() => skipOccurrence(item.ledger_id, item.rule_id, item.due_on))}
              >
                Пропустить
              </Button>
              <Button variant="ghost" onClick={() => onPostpone(Date.now() + LATER_MS)} disabled={busy}>
                Напомнить позже
              </Button>
            </div>
            <p className="mt-4 text-xs text-slate-500">
              «Нет» — деньги ещё не пришли, спросим завтра. «Пропустить» — этой выплаты не будет, в бюджете она не
              учитывается. «Напомнить позже» — спросим через три часа.
            </p>
          </>
        )}
      </div>
    </div>
  );
}
