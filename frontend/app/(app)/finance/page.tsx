"use client";

import { useCallback, useState } from "react";
import Link from "next/link";
import { Button, Card, ErrorBanner, Loading, PageHeader, SelectField, TextField } from "@/components/ui";
import { getErrorText } from "@/lib/api";
import {
  createFinanceCategory,
  createFinanceTransaction,
  createLedger,
  deleteFinanceCategory,
  deleteFinanceTransaction,
  getFinanceCategories,
  getFinanceSummary,
  getFinanceTransactions,
  getHouseholds,
  getLedgers,
  setFinanceBudget,
} from "@/lib/endpoints";
import {
  CURRENCY_OPTIONS,
  FINANCE_KIND_LABELS,
  formatMoney,
  formatMonthLabel,
  formatShortDate,
  optionalText,
  shiftMonth,
  todayInZone,
  toOptions,
} from "@/lib/format";
import { useProfile } from "@/lib/profile-context";
import type { FinanceCategory, FinanceKind, Ledger, LedgerKind } from "@/lib/types";
import { useAsyncData } from "@/lib/use-async-data";

/** Название книги для вкладки: "Личные" или "Семья: Дом". */
function ledgerTitle(ledger: Ledger): string {
  return ledger.kind === "personal" ? "Личные" : `Семья: ${ledger.household_name}`;
}

/** Страница «Финансы»: выбор книги (личные или семья) и работа с ней. */
export default function FinancePage() {
  // Книги пользователя и его домохозяйства (чтобы предложить создать недостающие)
  const loadLedgers = useCallback(async () => {
    const [ledgers, households] = await Promise.all([getLedgers(), getHouseholds()]);
    return { ledgers, households };
  }, []);
  const { data, loading, error, reload } = useAsyncData(loadLedgers);
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const ledgers = data?.ledgers ?? [];
  // Показываем выбранную книгу, а если выбора ещё не было, первую (личную)
  const current = ledgers.find((ledger) => ledger.id === selectedId) ?? ledgers[0] ?? null;
  const hasPersonal = ledgers.some((ledger) => ledger.kind === "personal");
  // Семейную книгу создают владелец или администратор домохозяйства, у которого её ещё нет
  const creatableHouseholds = (data?.households ?? []).filter(
    (household) =>
      (household.role === "owner" || household.role === "admin") &&
      !ledgers.some((ledger) => ledger.household_id === household.id),
  );

  return (
    <>
      <PageHeader title="Финансы" subtitle="Личные и семейные деньги" />

      {error && <ErrorBanner message={error} onRetry={reload} />}
      {loading && data === null && <Loading />}

      {data && (
        <div className="space-y-6">
          <div className="flex flex-wrap gap-2">
            {ledgers.map((ledger) => (
              <Button
                key={ledger.id}
                variant={current?.id === ledger.id ? "primary" : "secondary"}
                onClick={() => setSelectedId(ledger.id)}
              >
                {ledgerTitle(ledger)}
              </Button>
            ))}
          </div>
          {data.households.length === 0 && (
          <Card title="Семейные финансы">
              <p className="text-sm text-slate-600">
                Чтобы вести общие деньги, нужно домохозяйство. Создайте его или присоединитесь по коду на
                странице{" "}
                 <Link href="/family" className="font-medium text-emerald-700 underline">
                  «Семья»
                </Link>
                .
              </p>
            </Card>
          )}
          {data.households.length > 0 &&
            creatableHouseholds.length === 0 &&
            !ledgers.some((ledger) => ledger.kind === "household") && (
              <p className="text-sm text-slate-500">
                Семейную книгу ещё не создали. Это делает владелец или администратор домохозяйства.
              </p>
            )}

          {!hasPersonal && (
            <CreateLedgerCard
              title="Включить личные финансы"
              kind="personal"
              householdId={null}
              onCreated={reload}
            />
          )}
          {creatableHouseholds.map((household) => (
            <CreateLedgerCard
              key={household.id}
              title={`Включить финансы семьи «${household.name}»`}
              kind="household"
              householdId={household.id}
              onCreated={reload}
            />
          ))}

          {current && <LedgerView key={current.id} ledger={current} />}
        </div>
      )}
    </>
  );
}

/** Карточка создания книги: выбор валюты и кнопка. */
function CreateLedgerCard({
  title,
  kind,
  householdId,
  onCreated,
}: {
  title: string;
  kind: LedgerKind;
  householdId: number | null;
  onCreated: () => void;
}) {
  const [currency, setCurrency] = useState("RUB");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /** Создаёт книгу и просит страницу обновить список книг. */
  async function handleCreate() {
    setError(null);
    setSaving(true);
    try {
      await createLedger({ kind, household_id: householdId, currency });
      onCreated();
    } catch (err) {
      setError(getErrorText(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card title={title}>
      <p className="mb-4 text-sm text-slate-500">
        {kind === "household"
          ? "Данные будут видны всем участникам домохозяйства."
          : "Данные видны только вам."}{" "}
        Валюту потом изменить нельзя.
      </p>
      <div className="flex flex-wrap items-end gap-3">
        <div className="w-64">
          <SelectField label="Валюта" value={currency} onChange={setCurrency} options={CURRENCY_OPTIONS} />
        </div>
        <Button onClick={handleCreate} loading={saving}>
          Создать
        </Button>
      </div>
      {error && (
        <div className="mt-4">
          <ErrorBanner message={error} />
        </div>
      )}
    </Card>
  );
}

/** Одна книга: итоги месяца, лимиты, добавление операций, список и категории. */
function LedgerView({ ledger }: { ledger: Ledger }) {
  const { profile } = useProfile();
  const today = todayInZone(profile.timezone);
  // Месяц в формате "2026-10"
  const [month, setMonth] = useState(today.slice(0, 7));

  // Итоги, операции и категории месяца загружаются вместе
  const load = useCallback(async () => {
    const [summary, transactions, categories] = await Promise.all([
      getFinanceSummary(ledger.id, month),
      getFinanceTransactions(ledger.id, month),
      getFinanceCategories(ledger.id),
    ]);
    return { summary, transactions, categories };
  }, [ledger.id, month]);
  const view = useAsyncData(load);
  const data = view.data;

  const [actionError, setActionError] = useState<string | null>(null);

  /** Выполняет действие (удаление, лимит), обновляет данные и показывает ошибку при сбое. */
  async function run(action: () => Promise<unknown>) {
    setActionError(null);
    try {
      await action();
      view.reload();
    } catch (err) {
      setActionError(getErrorText(err));
    }
  }

  const money = (value: string | number) => formatMoney(value, ledger.currency);

  /** Запрашивает у пользователя месячный лимит категории; пустой ответ убирает лимит. */
  function handleBudget(category: { category_id: number; name: string; budget_limit: string | null }) {
    const answer = window.prompt(
      `Месячный лимит для «${category.name}» в ${ledger.currency} (пусто — убрать лимит)`,
      category.budget_limit === null ? "" : String(Number(category.budget_limit)),
    );
    if (answer === null) return; // нажали «Отмена»

    const limit = answer.trim() === "" ? null : Number(answer.replace(",", "."));
    if (limit !== null && (!Number.isFinite(limit) || limit <= 0)) {
      setActionError("Лимит должен быть положительным числом.");
      return;
    }
    void run(() => setFinanceBudget(ledger.id, category.category_id, limit));
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="secondary" onClick={() => setMonth(shiftMonth(month, -1))}>
          ←
        </Button>
        <p className="min-w-40 text-center font-semibold capitalize">{formatMonthLabel(month)}</p>
        <Button variant="secondary" onClick={() => setMonth(shiftMonth(month, 1))}>
          →
        </Button>
        <Button variant="secondary" onClick={() => setMonth(today.slice(0, 7))} disabled={month === today.slice(0, 7)}>
          Текущий месяц
        </Button>
      </div>

      {view.error && <ErrorBanner message={view.error} onRetry={view.reload} />}
      {actionError && <ErrorBanner message={actionError} />}
      {data === null && view.loading && <Loading />}

      {data && (
        <>
          <Card title="Итоги месяца">
            <div className="grid gap-3 sm:grid-cols-3">
              <div className="rounded-xl bg-emerald-50 p-4">
                <p className="text-sm text-slate-500">Доходы</p>
                <p className="mt-1 text-xl font-bold text-emerald-700">{money(data.summary.income)}</p>
              </div>
              <div className="rounded-xl bg-slate-50 p-4">
                <p className="text-sm text-slate-500">Расходы</p>
                <p className="mt-1 text-xl font-bold">{money(data.summary.expense)}</p>
              </div>
              <div className="rounded-xl bg-slate-50 p-4">
                <p className="text-sm text-slate-500">Баланс</p>
                <p className={`mt-1 text-xl font-bold ${Number(data.summary.balance) < 0 ? "text-red-600" : ""}`}>
                  {money(data.summary.balance)}
                </p>
              </div>
            </div>
          </Card>

          <Card title="Расходы по категориям и лимиты">
            <ul className="space-y-4">
              {data.summary.categories
                .filter((row) => row.kind === "expense" && (Number(row.total) > 0 || row.budget_limit !== null))
                .map((row) => {
                  const spent = Number(row.total);
                  const limit = row.budget_limit === null ? null : Number(row.budget_limit);
                  const percent = limit === null ? 0 : Math.min(100, Math.round((spent / limit) * 100));

                  return (
                    <li key={row.category_id}>
                      <div className="flex items-center justify-between gap-3 text-sm">
                        <span className="font-medium">{row.name}</span>
                        <span className={limit !== null && spent > limit ? "text-red-600" : "text-slate-600"}>
                          {money(spent)}
                          {limit !== null && ` из ${money(limit)}`}
                        </span>
                      </div>
                      {limit !== null && (
                        <div className="mt-2 h-2 overflow-hidden rounded-full bg-slate-100">
                          <div
                            className={`h-full rounded-full ${spent > limit ? "bg-red-500" : "bg-emerald-500"}`}
                            style={{ width: `${percent}%` }}
                          />
                        </div>
                      )}
                      {ledger.can_manage && (
                        <button
                          type="button"
                          onClick={() => handleBudget(row)}
                          className="mt-1 text-xs text-emerald-700 underline"
                        >
                          {limit === null ? "Задать лимит" : "Изменить лимит"}
                        </button>
                      )}
                    </li>
                  );
                })}
            </ul>
            {data.summary.categories.every((row) => row.kind !== "expense" || (Number(row.total) === 0 && row.budget_limit === null)) && (
              <p className="text-sm text-slate-500">В этом месяце расходов и лимитов пока нет.</p>
            )}
            {ledger.can_manage && (
              <div className="mt-4 border-t border-slate-100 pt-4">
                <p className="mb-2 text-sm text-slate-500">Лимит для категории без расходов:</p>
                <div className="flex flex-wrap gap-2">
                  {data.summary.categories
                    .filter((row) => row.kind === "expense" && Number(row.total) === 0 && row.budget_limit === null)
                    .map((row) => (
                      <Button key={row.category_id} variant="secondary" onClick={() => handleBudget(row)}>
                        {row.name}
                      </Button>
                    ))}
                </div>
              </div>
            )}
          </Card>

          <TransactionForm
            ledgerId={ledger.id}
            categories={data.categories}
            today={today}
            onAdded={view.reload}
          />

          <Card title="Операции">
            {data.transactions.length === 0 && <p className="text-sm text-slate-500">В этом месяце операций нет.</p>}
            <ul className="divide-y divide-slate-100">
              {data.transactions.map((transaction) => {
                // Удалять можно свои операции; управляющий может удалять любые
                const canDelete = ledger.can_manage || transaction.created_by_user_id === profile.id;
                return (
                  <li key={transaction.id} className="flex items-center justify-between gap-3 py-3">
                    <div className="min-w-0">
                      <p className="font-medium">
                        {transaction.category_name}
                        {transaction.description && (
                          <span className="font-normal text-slate-500"> · {transaction.description}</span>
                        )}
                      </p>
                      <p className="text-xs text-slate-400">
                        {formatShortDate(transaction.occurred_on)}
                        {ledger.kind === "household" && ` · ${transaction.created_by_name}`}
                      </p>
                    </div>
                    <div className="flex shrink-0 items-center gap-3">
                      <p className={`font-semibold ${transaction.kind === "income" ? "text-emerald-700" : ""}`}>
                        {transaction.kind === "income" ? "+" : "−"}
                        {money(transaction.amount)}
                      </p>
                      {canDelete && (
                        <Button
                          variant="danger"
                          onClick={() => {
                            if (window.confirm("Удалить операцию?")) {
                              void run(() => deleteFinanceTransaction(ledger.id, transaction.id));
                            }
                          }}
                        >
                          Удалить
                        </Button>
                      )}
                    </div>
                  </li>
                );
              })}
            </ul>
          </Card>

          <CategoriesCard
            ledgerId={ledger.id}
            categories={data.categories}
            canManage={ledger.can_manage}
            onChanged={view.reload}
          />
        </>
      )}
    </div>
  );
}

/** Форма добавления операции: тип, категория, сумма, дата и описание. */
function TransactionForm({
  ledgerId,
  categories,
  today,
  onAdded,
}: {
  ledgerId: number;
  categories: FinanceCategory[];
  today: string;
  onAdded: () => void;
}) {
  const [kind, setKind] = useState<FinanceKind>("expense");
  const [categoryId, setCategoryId] = useState("");
  const [amount, setAmount] = useState("");
  const [date, setDate] = useState(today);
  const [description, setDescription] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Категории выбранного типа в виде пар [id, название]
  const options = categories
    .filter((category) => category.kind === kind)
    .map((category): [string, string] => [String(category.id), category.name]);
  // Если выбранная категория не подходит к типу, используем первую из списка
  const selected = options.some(([value]) => value === categoryId) ? categoryId : (options[0]?.[0] ?? "");

  /** Добавляет операцию и обновляет данные страницы. */
  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    if (selected === "") {
      setError("Выберите категорию.");
      return;
    }

    setSaving(true);
    try {
      await createFinanceTransaction(ledgerId, {
        category_id: Number(selected),
        amount: Number(amount.replace(",", ".")),
        occurred_on: date,
        description: optionalText(description),
      });
      setAmount("");
      setDescription("");
      onAdded();
    } catch (err) {
      setError(getErrorText(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card title="Новая операция">
      <form onSubmit={handleSubmit} className="grid gap-3 sm:grid-cols-2">
        <SelectField
          label="Тип"
          value={kind}
          onChange={(value) => setKind(value as FinanceKind)}
          options={toOptions(FINANCE_KIND_LABELS)}
        />
        <SelectField label="Категория" value={selected} onChange={setCategoryId} options={options} />
        <TextField label="Сумма" type="number" min={0.01} step="0.01" value={amount} onChange={setAmount} required />
        <TextField label="Дата" type="date" value={date} onChange={setDate} required />
        <div className="sm:col-span-2">
          <TextField label="Описание (необязательно)" value={description} onChange={setDescription} maxLength={250} />
        </div>
        <div className="sm:col-span-2">
          <Button type="submit" loading={saving}>
            Добавить
          </Button>
        </div>
      </form>
      {error && (
        <div className="mt-4">
          <ErrorBanner message={error} />
        </div>
      )}
    </Card>
  );
}

/** Категории книги: список и (для управляющих) добавление и удаление. */
function CategoriesCard({
  ledgerId,
  categories,
  canManage,
  onChanged,
}: {
  ledgerId: number;
  categories: FinanceCategory[];
  canManage: boolean;
  onChanged: () => void;
}) {
  const [name, setName] = useState("");
  const [kind, setKind] = useState<FinanceKind>("expense");
  const [error, setError] = useState<string | null>(null);

  /** Добавляет категорию. */
  async function handleAdd(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    try {
      await createFinanceCategory(ledgerId, { name: name.trim(), kind });
      setName("");
      onChanged();
    } catch (err) {
      setError(getErrorText(err));
    }
  }

  /** Удаляет категорию без операций после подтверждения. */
  async function handleDelete(category: FinanceCategory) {
    if (!window.confirm(`Удалить категорию «${category.name}»?`)) return;
    setError(null);
    try {
      await deleteFinanceCategory(ledgerId, category.id);
      onChanged();
    } catch (err) {
      setError(getErrorText(err));
    }
  }

  return (
    <Card title="Категории">
      {(["expense", "income"] as FinanceKind[]).map((groupKind) => (
        <div key={groupKind} className="mb-4">
          <p className="mb-2 text-sm font-medium text-slate-500">{FINANCE_KIND_LABELS[groupKind]}ы</p>
          <div className="flex flex-wrap gap-2">
            {categories
              .filter((category) => category.kind === groupKind)
              .map((category) => (
                <span
                  key={category.id}
                  className="inline-flex items-center gap-2 rounded-full bg-slate-100 px-3 py-1 text-sm"
                >
                  {category.name}
                  {canManage && (
                    <button
                      type="button"
                      onClick={() => handleDelete(category)}
                      className="text-slate-400 hover:text-red-600"
                      aria-label={`Удалить категорию ${category.name}`}
                    >
                      ✕
                    </button>
                  )}
                </span>
              ))}
          </div>
        </div>
      ))}

      {canManage ? (
        <form onSubmit={handleAdd} className="grid gap-3 sm:grid-cols-3">
          <TextField label="Новая категория" value={name} onChange={setName} required maxLength={80} />
          <SelectField
            label="Тип"
            value={kind}
            onChange={(value) => setKind(value as FinanceKind)}
            options={toOptions(FINANCE_KIND_LABELS)}
          />
          <div className="flex items-end">
            <Button type="submit">Добавить категорию</Button>
          </div>
        </form>
      ) : (
        <p className="text-sm text-slate-500">Категориями управляют владелец и администратор домохозяйства.</p>
      )}
      {error && (
        <div className="mt-4">
          <ErrorBanner message={error} />
        </div>
      )}
    </Card>
  );
}