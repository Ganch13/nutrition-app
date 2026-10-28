"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import AuthLayout from "@/components/AuthLayout";
import { Button, ErrorBanner, PasswordField, SelectField, TextField } from "@/components/ui";
import { getErrorText, storeAccessToken } from "@/lib/api";
import { loginUser, registerUser } from "@/lib/endpoints";
import { SEX_OPTIONS } from "@/lib/format";
import type { Sex } from "@/lib/types";

/**
 * Страница регистрации: создаёт аккаунт, сразу выполняет вход и открывает главную.
 * Пароль вводится дважды: так опечатка не превратится в пароль, который человек не знает.
 * Часовой пояс берётся с устройства автоматически; потом его можно изменить в профиле.
 */
export default function RegisterPage() {
  const router = useRouter();

  // Значения полей формы; числа и даты хранятся как строки, как их отдаёт поле ввода
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [repeat, setRepeat] = useState("");
  const [height, setHeight] = useState("");
  const [birthDate, setBirthDate] = useState("");
  const [sex, setSex] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  // Подсказка о несовпадении появляется, как только второе поле начали заполнять
  const mismatch = repeat !== "" && repeat !== password;

  /** Отправка формы: проверки → регистрация → вход → переход на главную. */
  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    // Те же правила, что на backend: пароль не короче 12 символов
    if (password.length < 12) {
      setError("Пароль должен содержать не менее 12 символов.");
      return;
    }
    if (password !== repeat) {
      setError("Пароли не совпадают. Введите один и тот же пароль в оба поля.");
      return;
    }

    setSaving(true);
    try {
      await registerUser({
        name: name.trim(),
        email: email.trim(),
        password,
        height_cm: Number(height),
        birth_date: birthDate === "" ? null : birthDate,
        sex: sex === "" ? null : (sex as Sex),
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
      });

      const token = await loginUser(email.trim(), password);
      storeAccessToken(token.access_token);
      router.push("/");
    } catch (err) {
      setError(getErrorText(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <AuthLayout title="Создать аккаунт" subtitle="Пара минут, и можно планировать неделю.">
      <form onSubmit={handleSubmit} className="space-y-5">
        <TextField label="Имя" value={name} onChange={setName} required maxLength={100} autoComplete="name" />
        <TextField
          label="Email"
          type="email"
          autoComplete="email"
          inputMode="email"
          autoCapitalize="none"
          value={email}
          onChange={setEmail}
          required
        />
        <PasswordField
          label="Пароль"
          autoComplete="new-password"
          value={password}
          onChange={setPassword}
          required
          maxLength={128}
          hint="Не короче 12 символов. Лучше длинная фраза, которую вы нигде не используете."
        />
        <PasswordField
          label="Повторите пароль"
          autoComplete="new-password"
          value={repeat}
          onChange={setRepeat}
          required
          maxLength={128}
          error={mismatch ? "Пароли не совпадают" : undefined}
          hint={repeat !== "" && !mismatch ? "Пароли совпадают" : "Введите тот же пароль ещё раз"}
        />

        <div className="grid gap-5 sm:grid-cols-2">
          <TextField
            label="Рост, см"
            type="number"
            inputMode="numeric"
            min={50}
            max={300}
            value={height}
            onChange={setHeight}
            required
          />
          <SelectField label="Пол" value={sex} onChange={setSex} options={SEX_OPTIONS} />
        </div>
        <TextField label="Дата рождения (необязательно)" type="date" value={birthDate} onChange={setBirthDate} />

        {error && <ErrorBanner message={error} />}

        <Button type="submit" loading={saving} className="w-full">
          {saving ? "Создаём аккаунт..." : "Создать аккаунт"}
        </Button>

        <p className="text-center text-sm text-slate-500">
          Уже есть аккаунт?{" "}
          <Link href="/login" className="font-medium text-brand-700 underline underline-offset-2">
            Войти
          </Link>
        </p>
      </form>
    </AuthLayout>
  );
}
