"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, useSyncExternalStore } from "react";
import AuthLayout from "@/components/AuthLayout";
import { Button, ErrorBanner, PasswordField, SuccessNotice, TextField } from "@/components/ui";
import { getErrorText, storeAccessToken } from "@/lib/api";
import { loginUser } from "@/lib/endpoints";

// Сообщение для страницы входа, оставленное другой страницей (например, «Аккаунт удалён»)
const NOTICE_KEY = "lad_notice";

/** Читает сообщение из sessionStorage. Вне браузера и при запрете хранилища возвращает null. */
function readNotice(): string | null {
  try {
    return sessionStorage.getItem(NOTICE_KEY);
  } catch {
    return null;
  }
}

// Сообщение не меняется само, поэтому подписка не нужна
const subscribeNever = () => () => {};

/** Страница входа: email и пароль (пароль можно показать «глазом» справа). */
export default function LoginPage() {
  const router = useRouter();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  // На сервере сообщения нет (null), в браузере оно читается после загрузки страницы
  const notice = useSyncExternalStore(subscribeNever, readNotice, () => null);

  /** Вход: POST /auth/login → сохранить токен → открыть главную. */
  async function handleLogin(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setLoading(true);

    try {
      const data = await loginUser(email.trim(), password);
      storeAccessToken(data.access_token);
      try {
        sessionStorage.removeItem(NOTICE_KEY);
      } catch {
        // Не страшно: сообщение просто покажется ещё раз
      }
      router.push("/");
    } catch (err) {
      setError(getErrorText(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthLayout title="Вход" subtitle="Войдите, чтобы увидеть свой день, меню и бюджет.">
      <form onSubmit={handleLogin} className="space-y-5">
        {notice && <SuccessNotice message={notice} />}

        <TextField
          label="Email"
          type="email"
          autoComplete="email"
          inputMode="email"
          autoCapitalize="none"
          required
          value={email}
          onChange={setEmail}
          placeholder="name@example.com"
        />
        <PasswordField
          label="Пароль"
          autoComplete="current-password"
          required
          value={password}
          onChange={setPassword}
          placeholder="Введите пароль"
        />

        {error && <ErrorBanner message={error} />}

        <Button type="submit" loading={loading} className="w-full">
          {loading ? "Входим..." : "Войти"}
        </Button>

        <p className="text-center text-sm text-slate-500">
          Нет аккаунта?{" "}
          <Link href="/register" className="font-medium text-brand-700 underline underline-offset-2">
            Создать аккаунт
          </Link>
        </p>
      </form>
    </AuthLayout>
  );
}
