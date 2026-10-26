"use client";

import { useMemo, useState } from "react";
import {
  Button,
  Card,
  ErrorBanner,
  PageHeader,
  SelectField,
  SuccessNotice,
  TextField,
} from "@/components/ui";
import { getErrorText, logout } from "@/lib/api";
import { updateProfile } from "@/lib/endpoints";
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
            <Button
              variant="secondary"
              onClick={() => setTimeZone(Intl.DateTimeFormat().resolvedOptions().timeZone)}
            >
              Использовать часовой пояс устройства
            </Button>

            {error && <ErrorBanner message={error} />}
            {saved && <SuccessNotice message="Профиль сохранён." />}

            <Button type="submit" loading={saving}>
              Сохранить
            </Button>
          </form>
        </Card>

        <Card title="Аккаунт">
          <Button variant="danger" onClick={logout}>
            Выйти из аккаунта
          </Button>
        </Card>
      </div>
    </>
  );
}