"use client";

import { useCallback, useState } from "react";
import { Badge, Button, Card, ErrorBanner, Loading, Notice, TextField } from "@/components/ui";
import { absoluteApiUrl, getErrorText } from "@/lib/api";
import { createAccessKey, getAccessKeys, QUICK_CATEGORIES_PATH, QUICK_EXPENSE_PATH, revokeAccessKey } from "@/lib/endpoints";
import { formatDateTime } from "@/lib/format";
import type { CreatedAccessKey } from "@/lib/types";
import { useAsyncData } from "@/lib/use-async-data";

/**
 * Полный адрес эндпоинта по адресу сайта. На сервере (нет window) — просто путь.
 * Пример на https://lad.example.ru: "https://lad.example.ru/api/quick/expense".
 */
function endpointUrl(path: string): string {
  return typeof window === "undefined" ? path : absoluteApiUrl(path);
}

/** Строка с адресом и кнопкой «Копировать». Пример: label="Расход", value="https://.../api/quick/expense". */
function CopyLine({ label, value }: { label: string; value: string }) {
  const [copied, setCopied] = useState(false);

  /** Копирует value в буфер обмена; «Скопировано» видно 2 секунды. */
  async function copy() {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      // Буфер недоступен (старый браузер, нет разрешения): текст можно выделить и скопировать вручную
      setCopied(false);
    }
  }

  return (
    <div>
      <p className="text-xs text-slate-500">{label}</p>
      <div className="mt-1 flex items-center gap-2">
        <code className="min-w-0 flex-1 select-all break-all rounded-lg bg-slate-100 px-3 py-2 font-mono text-xs text-slate-800">
          {value}
        </code>
        <Button size="sm" variant="secondary" onClick={() => void copy()}>
          {copied ? "Скопировано" : "Копировать"}
        </Button>
      </div>
    </div>
  );
}

/**
 * «Профиль и настройки» → «Быстрое добавление с iPhone»: личные ключи для быстрой команды.
 *
 * Путь данных: «Создать ключ» → POST /access-keys {"name": "iPhone"} → ответ с полем key ("lad_Xk3f9Q...")
 * → ключ показывается здесь ОДИН раз с кнопкой «Копировать» → человек вставляет его в быструю команду.
 * Дальше iPhone сам отправляет POST /api/quick/expense с заголовком Authorization: Bearer lad_...
 * Список ключей (GET /access-keys) показывает только начало ключа, даты и статус; «Отозвать» — DELETE /access-keys/{id}.
 * Подробная инструкция для «Быстрых команд» — docs/QUICK_ADD_IPHONE.md.
 */
export default function AccessKeysCard() {
  const load = useCallback(() => getAccessKeys(), []);
  const { data: keys, error, reload } = useAsyncData(load);

  const [name, setName] = useState("iPhone");
  const [creating, setCreating] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  // Только что созданный ключ: показывается, пока человек не нажмёт «Я сохранил ключ»
  const [created, setCreated] = useState<CreatedAccessKey | null>(null);
  // Ключ, для которого открыто подтверждение «Отозвать?»
  const [confirmId, setConfirmId] = useState<number | null>(null);
  const [revoking, setRevoking] = useState(false);

  /** Создаёт ключ и показывает его один раз. */
  async function handleCreate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setActionError(null);
    setCreating(true);
    try {
      setCreated(await createAccessKey(name.trim()));
      reload();
    } catch (err) {
      setActionError(getErrorText(err));
    } finally {
      setCreating(false);
    }
  }

  /** Отзывает ключ: быстрая команда с ним сразу перестаёт работать. */
  async function handleRevoke(keyId: number) {
    setActionError(null);
    setRevoking(true);
    try {
      await revokeAccessKey(keyId);
      setConfirmId(null);
      if (created?.id === keyId) setCreated(null);
      reload();
    } catch (err) {
      setActionError(getErrorText(err));
    } finally {
      setRevoking(false);
    }
  }

  const activeCount = keys?.filter((key) => key.active).length ?? 0;

  return (
    <Card
      title="Быстрое добавление с iPhone"
      description="Расход одной командой с экрана «Домой» или голосом через Siri, не открывая приложение."
    >
      <div className="space-y-5">
        <ol className="list-decimal space-y-1 pl-5 text-sm text-slate-600">
          <li>Создайте ключ ниже и скопируйте его — он покажется только один раз.</li>
          <li>
            В приложении «Быстрые команды» соберите команду: «Запросить ввод» (сумма) → «Выбрать из меню» (категория) →
            «Получить содержимое URL» (POST на адрес ниже, заголовок <code>Authorization: Bearer ключ</code>) →
            «Показать уведомление».
          </li>
          <li>Расход сразу появится в «Финансах», а в уведомлении будут баланс, «свободно» и «в день».</li>
        </ol>

        <div className="space-y-3">
          <CopyLine label="Адрес для расхода (POST)" value={endpointUrl(QUICK_EXPENSE_PATH)} />
          <CopyLine label="Адрес списка категорий (GET, для меню)" value={endpointUrl(QUICK_CATEGORIES_PATH)} />
          <p className="text-xs text-slate-500">
            Тело запроса: <code>{'{"amount": 350, "category": "Продукты"}'}</code>. Пошаговая инструкция — в файле
            docs/QUICK_ADD_IPHONE.md.
          </p>
        </div>

        {created && (
          <div className="space-y-3 rounded-2xl border border-amber-200 bg-amber-50 p-4">
            <p className="text-sm font-semibold text-amber-900">Ключ «{created.name}» создан</p>
            <CopyLine label="Ваш ключ" value={created.key} />
            <Notice tone="warning">
              Скопируйте ключ сейчас: повторно он не покажется. Никому его не пересылайте — с ним можно записывать расходы
              от вашего имени. Потеряли — отзовите и создайте новый.
            </Notice>
            <Button size="sm" onClick={() => setCreated(null)}>
              Я сохранил ключ
            </Button>
          </div>
        )}

        {actionError && <ErrorBanner message={actionError} />}

        <form onSubmit={handleCreate} className="flex flex-wrap items-end gap-3">
          <div className="min-w-48 flex-1">
            <TextField label="Название ключа" value={name} onChange={setName} required maxLength={50} placeholder="iPhone" />
          </div>
          <Button type="submit" loading={creating} disabled={name.trim() === "" || activeCount >= 5}>
            Создать ключ
          </Button>
        </form>
        {activeCount >= 5 && <p className="text-xs text-slate-500">Действующих ключей не больше пяти: отзовите ненужный.</p>}

        {error && <ErrorBanner message={error} onRetry={reload} />}
        {keys === null && !error && <Loading />}
        {keys && keys.length > 0 && (
          <ul className="divide-y divide-slate-100">
            {keys.map((key) => (
              <li key={key.id} className="py-3">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="min-w-0">
                    <p className="flex flex-wrap items-center gap-2 font-medium text-slate-900">
                      {key.name}
                      <span className="font-mono text-xs font-normal text-slate-500">{key.key_prefix}…</span>
                      {key.active ? <Badge tone="green">Действует</Badge> : <Badge>Отозван</Badge>}
                    </p>
                    <p className="text-xs text-slate-500">
                      Создан {formatDateTime(key.created_at)}
                      {" · "}
                      {key.last_used_at ? `последний раз ${formatDateTime(key.last_used_at)}` : "ещё не использовался"}
                      {key.revoked_at && ` · отозван ${formatDateTime(key.revoked_at)}`}
                    </p>
                  </div>
                  {key.active && confirmId !== key.id && (
                    <Button size="sm" variant="danger" onClick={() => setConfirmId(key.id)}>
                      Отозвать
                    </Button>
                  )}
                </div>
                {confirmId === key.id && (
                  <div className="mt-2 flex flex-wrap items-center gap-3 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">
                    <span>Отозвать ключ «{key.name}»? Быстрая команда с ним сразу перестанет работать.</span>
                    <Button size="sm" variant="danger-solid" loading={revoking} onClick={() => void handleRevoke(key.id)}>
                      Отозвать
                    </Button>
                    <Button size="sm" variant="secondary" onClick={() => setConfirmId(null)} disabled={revoking}>
                      Отмена
                    </Button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
        {keys && keys.length === 0 && <p className="text-sm text-slate-500">Ключей пока нет.</p>}
      </div>
    </Card>
  );
}
