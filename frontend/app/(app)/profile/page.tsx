"use client";

import { useMemo, useState } from "react";
import DeleteAccountCard from "@/components/DeleteAccountCard";
import {
  Button,
  Card,
  ErrorBanner,
  PageHeader,
  PasswordField,
  SelectField,
  SuccessNotice,
  TextField,
} from "@/components/ui";
import { getErrorText, logout } from "@/lib/api";
import { changePassword, updateProfile } from "@/lib/endpoints";
import { optionalText, SEX_OPTIONS } from "@/lib/format";
import { useProfile } from "@/lib/profile-context";
import type { Sex } from "@/lib/types";

/** Профиль и настройки: редактирование данных и часового пояса, выход из аккаунта. */
export default function ProfilePage() {
  const { profile, refreshProfile } = useProfile();

  // Начальные значения полей берём из текущего профиля; null превращаем в ""
  const [name, setName] = useState(profile.name);
  const [birthDate, setBirthDate] = useState(profile.birth_date ?? "");
  const [sex, setSex] = useState(profile.sex ?? "");
  const [height, setHeight] = useState(String(profile.height_cm));
  const [occupation, setOccupation] = useState(profile.occupation ?? "");
  const [timeZone, setTimeZone] = useState(profile.timezone);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Форма смены пароля
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [repeatPassword, setRepeatPassword] = useState("");
  const [passwordSaving, setPasswordSaving] = useState(false);
  const [passwordChanged, setPasswordChanged] = useState(false);
  const [passwordError, setPasswordError] = useState<string | null>(null);

  // Список часовых поясов; "UTC" и текущий пояс профиля добавляем явно,
  // потому что браузер может не включить их в свой список
  const zoneOptions = useMemo(() => {
    const zones = new Set<string>(["UTC", profile.timezone, ...Intl.supportedValuesOf("timeZone")]);
    return Array.from(zones).map((zone): [string, string] => [zone, zone]);
  }, [profile.timezone]);

  /** Сохраняет профиль (PATCH /users/{id}) и обновляет данные во всём приложении. */
  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSaved(false);
    setSaving(true);

    try {
      await updateProfile(profile.id, {
        name: name.trim(),
        birth_date: birthDate === "" ? null : birthDate,
        sex: sex === "" ? null : (sex as Sex),
        height_cm: Number(height),
        occupation: optionalText(occupation),
        timezone: timeZone,
      });
      refreshProfile();
      setSaved(true);
    } catch (err) {
      setError(getErrorText(err));
    } finally {
      setSaving(false);
    }
  }

  /**
   * Смена пароля (POST /auth/change-password). Проверяем то же, что backend: новый пароль не короче 12 символов.
   * После успеха на других устройствах нужно войти заново, а здесь сессия продолжается.
   */
  async function handlePasswordSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPasswordError(null);
    setPasswordChanged(false);

    if (newPassword.length < 12) {
      setPasswordError("Новый пароль должен содержать не менее 12 символов.");
      return;
    }
    if (newPassword !== repeatPassword) {
      setPasswordError("Новые пароли не совпадают.");
      return;
    }

    setPasswordSaving(true);
    try {
      await changePassword(currentPassword, newPassword);
      setCurrentPassword("");
      setNewPassword("");
      setRepeatPassword("");
      setPasswordChanged(true);
    } catch (err) {
      setPasswordError(getErrorText(err));
    } finally {
      setPasswordSaving(false);
    }
  }

  return (
    <>
      <PageHeader title="Профиль" subtitle="Личные данные и настройки" />

      <div className="max-w-2xl space-y-6">
        <Card title="Личные данные">
          <form onSubmit={handleSubmit} className="space-y-4">
            <TextField label="Имя" value={name} onChange={setName} required maxLength={100} />
            <div className="grid gap-4 sm:grid-cols-2">
              <TextField label="Дата рождения" type="date" value={birthDate} onChange={setBirthDate} />
              <SelectField label="Пол" value={sex} onChange={setSex} options={SEX_OPTIONS} />
              <TextField
                label="Рост, см"
                type="number"
                min={50}
                max={300}
                value={height}
                onChange={setHeight}
                required
              />
              <TextField label="Род занятий" value={occupation} onChange={setOccupation} maxLength={100} />
            </div>

            <SelectField label="Часовой пояс" value={timeZone} onChange={setTimeZone} options={zoneOptions} />
            <div>
              <Button
                size="sm"
                variant="ghost"
                className="-ml-3"
                onClick={() => setTimeZone(Intl.DateTimeFormat().resolvedOptions().timeZone)}
              >
                Использовать часовой пояс устройства
              </Button>
            </div>

            {error && <ErrorBanner message={error} />}
            {saved && <SuccessNotice message="Профиль сохранён." />}

            <Button type="submit" loading={saving}>
              Сохранить
            </Button>
          </form>
        </Card>

        <Card title="Смена пароля">
          <form onSubmit={handlePasswordSubmit} className="space-y-4">
            <PasswordField
              label="Текущий пароль"
              autoComplete="current-password"
              value={currentPassword}
              onChange={setCurrentPassword}
              required
              maxLength={128}
            />
            <PasswordField
              label="Новый пароль"
              autoComplete="new-password"
              value={newPassword}
              onChange={setNewPassword}
              required
              minLength={12}
              maxLength={128}
              hint="Не короче 12 символов. Лучше длинная фраза, которую вы нигде больше не используете."
            />
            <PasswordField
              label="Новый пароль ещё раз"
              autoComplete="new-password"
              value={repeatPassword}
              onChange={setRepeatPassword}
              required
              maxLength={128}
              error={repeatPassword !== "" && repeatPassword !== newPassword ? "Пароли не совпадают" : undefined}
            />

            {passwordError && <ErrorBanner message={passwordError} />}
            {passwordChanged && (
              <SuccessNotice message="Пароль изменён. На остальных устройствах нужно войти заново." />
            )}

            <Button type="submit" loading={passwordSaving}>
              Изменить пароль
            </Button>
          </form>
        </Card>

        <Card title="Приложение на телефоне">
          <div className="space-y-3 text-sm text-slate-600">
            <p>
              <span className="font-medium text-slate-800">iPhone (Safari):</span> нажмите «Поделиться» (квадрат со
              стрелкой) → «На экран «Домой»» → «Добавить». Открывайте именно в Safari: из других браузеров этот пункт
              недоступен.
            </p>
            <p>
              <span className="font-medium text-slate-800">Android (Chrome):</span> меню ⋮ → «Установить приложение»
              (или «Добавить на главный экран»).
            </p>
            <p className="text-xs text-slate-500">
              После установки приложение открывается без адресной строки. Войти нужно один раз: сессия сохраняется на
              30 дней.
            </p>
          </div>
        </Card>

        <Card title="Аккаунт">
          <Button variant="secondary" onClick={logout}>
            Выйти из аккаунта
          </Button>
        </Card>

        <DeleteAccountCard />
      </div>
    </>
  );
}