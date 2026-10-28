"use client";

import { useState } from "react";
import { getErrorText } from "@/lib/api";
import { deleteAccount, getDeletionPreview } from "@/lib/endpoints";
import { plural } from "@/lib/format";
import { useAsyncData } from "@/lib/use-async-data";
import { Button, Card, ErrorBanner, Loading, Notice, PasswordField } from "./ui";

// Подписи для счётчиков из ответа сервера: [один, два, пять] — склонение для чисел
const COUNT_LABELS: Record<string, [string, string, string]> = {
  weight_records: ["запись веса", "записи веса", "записей веса"],
  meal_entries: ["запись о питании", "записи о питании", "записей о питании"],
  training_sessions: ["тренировка", "тренировки", "тренировок"],
  progress_photos: ["фото прогресса", "фото прогресса", "фото прогресса"],
  finance_transactions: ["финансовая операция", "финансовые операции", "финансовых операций"],
};

/**
 * Карточка «Удаление аккаунта» на странице профиля.
 * Сначала короткое предупреждение и кнопка. По кнопке запрашивается, что именно будет стёрто
 * (GET /auth/delete-account/preview), и показывается форма подтверждения: пароль и галочка.
 * Удаление (POST /auth/delete-account) необратимо: после него открывается страница входа.
 */
export default function DeleteAccountCard() {
  const [open, setOpen] = useState(false);

  return (
    <Card title="Удаление аккаунта">
      {!open ? (
        <div className="space-y-4">
          <p className="text-sm text-slate-600">
            Аккаунт и все ваши данные будут стёрты без возможности восстановления: питание, тренировки, вес, фото и
            личные финансы.
          </p>
          <Button variant="danger" onClick={() => setOpen(true)}>
            Удалить аккаунт
          </Button>
        </div>
      ) : (
        <DeletePanel onCancel={() => setOpen(false)} />
      )}
    </Card>
  );
}

/** Подтверждение удаления: что будет стёрто, пароль, галочка и кнопки. */
function DeletePanel({ onCancel }: { onCancel: () => void }) {
  // «Что будет стёрто»: запрос выполняется один раз при показе панели
  const { data: preview, error: previewError, reload } = useAsyncData(getDeletionPreview);

  const [password, setPassword] = useState("");
  const [understood, setUnderstood] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /** Удаляет аккаунт. При успехе deleteAccount сам закрывает сессию и открывает страницу входа. */
  async function handleDelete(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setDeleting(true);
    try {
      await deleteAccount(password);
    } catch (err) {
      setError(getErrorText(err));
      setDeleting(false);
    }
  }

  if (previewError) return <ErrorBanner message={previewError} onRetry={reload} />;
  if (preview === null) return <Loading text="Проверяем, что будет удалено..." />;

  // Счётчики, по которым что-то есть: [подпись, число]
  const counted = Object.entries(preview.counts)
    .filter(([key, value]) => value > 0 && COUNT_LABELS[key])
    .map(([key, value]) => `${value} ${plural(value, COUNT_LABELS[key])}`);

  return (
    <form onSubmit={handleDelete} className="space-y-5">
      <div className="space-y-2 text-sm text-slate-700">
        <p className="font-medium text-slate-900">Будет стёрто:</p>
        <ul className="list-disc space-y-1 pl-5">
          <li>профиль, цели, расписание, нормы питания, личные продукты и рецепты;</li>
          {counted.length > 0 && <li>{counted.join(", ")};</li>}
          <li>вы выйдете со всех устройств.</li>
        </ul>
      </div>

      {(preview.households_to_delete.length > 0 || preview.households_to_leave.length > 0) && (
        <div className="space-y-2">
          {preview.households_to_delete.map((household) => (
            <Notice key={household.id} tone="warning" title={`Семья «${household.name}» будет удалена`}>
              Вы в ней единственный участник, поэтому вместе с семьёй исчезнут её общие продукты, рецепты и финансы.
            </Notice>
          ))}
          {preview.households_to_leave.map((household) => (
            <Notice key={household.id} title={`Семья «${household.name}» останется`}>
              Вы выйдете из неё
              {household.new_owner_name
                ? `, а владельцем станет ${household.new_owner_name}`
                : ""}
              . Общие операции останутся в семейной книге с подписью «Удалённый пользователь».
            </Notice>
          ))}
        </div>
      )}

      <p className="text-sm text-slate-500">
        Тот же email можно будет зарегистрировать снова, но это будет новый аккаунт без прежних данных.
      </p>

      <PasswordField
        label="Пароль для подтверждения"
        autoComplete="current-password"
        value={password}
        onChange={setPassword}
        required
        maxLength={128}
      />

      <label className="flex items-start gap-3 text-sm text-slate-700">
        <input
          type="checkbox"
          checked={understood}
          onChange={(event) => setUnderstood(event.target.checked)}
          className="mt-0.5 size-5 shrink-0 accent-brand-700"
        />
        Я понимаю, что данные нельзя будет восстановить
      </label>

      {error && <ErrorBanner message={error} />}

      <div className="flex flex-wrap gap-3">
        <Button type="submit" variant="danger-solid" loading={deleting} disabled={!understood || password === ""}>
          Удалить аккаунт навсегда
        </Button>
        <Button variant="secondary" onClick={onCancel} disabled={deleting}>
          Отмена
        </Button>
      </div>
    </form>
  );
}
