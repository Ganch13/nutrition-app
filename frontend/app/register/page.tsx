"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button, ErrorBanner, SelectField, TextField } from "@/components/ui";
import { getErrorText } from "@/lib/api";
import { loginUser, registerUser } from "@/lib/endpoints";
import { SEX_OPTIONS } from "@/lib/format";
import type { Sex } from "@/lib/types";

/**
 * Страница регистрации: создаёт аккаунт, сразу выполняет вход и открывает главную.
 * Часовой пояс берётся с устройства автоматически; потом его можно изменить в профиле.
 */
export default function RegisterPage() {
  const router = useRouter();

  // Значения полей формы; числа и даты хранятся как строки, как их отдаёт поле ввода
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [height, setHeight] = useState("");
  const [birthDate, setBirthDate] = useState("");
  const [sex, setSex] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  /** Отправка формы: регистрация → вход → переход на главную. */
  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    // Те же правила, что на backend: пароль не короче 12 символов
    if (password.length < 12) {
      setError("Пароль должен содержать не менее 12 символов.");
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
      sessionStorage.setItem("access_token", token.access_token);
      router.push("/");
    } catch (err) {
      setError(getErrorText(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-zinc-100 px-4 py-8">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-md space-y-4 rounded-2xl bg-white p-8 shadow-sm"
      >
        <div>
          <h1 className="text-2xl font-bold text-zinc-900">Регистрация</h1>
          <p className="mt-2 text-sm text-zinc-500">Nutrition & Training Planner</p>
        </div>

        <TextField label="Имя" value={name} onChange={setName} required maxLength={100} />
        <TextField
          label="Email"
          type="email"
          autoComplete="email"
          value={email}
          onChange={setEmail}
          required
        />
        <TextField
          label="Пароль"
          type="password"
          autoComplete="new-password"
          value={password}
          onChange={setPassword}
          required
          hint="Не менее 12 символов"
        />
        <TextField
          label="Рост, см"
          type="number"
          min={50}
          max={300}
          value={height}
          onChange={setHeight}
          required
        />
        <TextField label="Дата рождения (необязательно)" type="date" value={birthDate} onChange={setBirthDate} />
        <SelectField label="Пол" value={sex} onChange={setSex} options={SEX_OPTIONS} />

        {error && <ErrorBanner message={error} />}

        <Button type="submit" loading={saving}>
          {saving ? "Создаём аккаунт..." : "Зарегистрироваться"}
        </Button>

        <p className="text-sm text-zinc-500">
          Уже есть аккаунт?{" "}
          <Link href="/login" className="font-medium text-green-700 hover:underline">
            Войти
          </Link>
        </p>
      </form>
    </main>
  );
}