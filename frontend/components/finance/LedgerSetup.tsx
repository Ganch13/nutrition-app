"use client";

import { useState } from "react";
import { Button, Card, ErrorBanner, SelectField } from "@/components/ui";
import { getErrorText } from "@/lib/api";
import { createLedger } from "@/lib/endpoints";
import { CURRENCY_OPTIONS } from "@/lib/format";
import type { LedgerKind } from "@/lib/types";

/**
 * Карточка включения финансов: личных или семейных. Человек выбирает валюту и нажимает «Включить».
 * Валюту потом не изменить, потому что суммы уже записаны в ней.
 * Пример: kind="household", householdId=3, title="Финансы семьи «Дом»".
 */
export default function CreateLedgerCard({
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

  /** Создаёт книгу: POST /finance/ledgers. После успеха страница обновляет список книг. */
  async function handleCreate() {
    setError(null);
    setSaving(true);
    try {
      await createLedger({ kind, household_id: householdId, currency });
      onCreated();
    } catch (err) {
      setError(getErrorText(err));
      setSaving(false);
    }
  }

  return (
    <Card title={title}>
      <p className="mb-4 max-w-xl text-sm text-slate-600">
        {kind === "household"
          ? "Операции, платежи и цели будут видны всем участникам семьи."
          : "Эти данные видите только вы."}{" "}
        Валюту потом изменить нельзя.
      </p>
      <div className="flex flex-wrap items-end gap-3">
        <div className="w-full sm:w-64">
          <SelectField label="Валюта" value={currency} onChange={setCurrency} options={CURRENCY_OPTIONS} />
        </div>
        <Button onClick={handleCreate} loading={saving}>
          Включить
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
