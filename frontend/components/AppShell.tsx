"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { logout } from "@/lib/api";
import { getProfile } from "@/lib/endpoints";
import { ProfileContext } from "@/lib/profile-context";
import { useAsyncData } from "@/lib/use-async-data";
import { Button, ErrorBanner } from "./ui";

// Пункты меню: адрес, подпись и значок
const NAV_ITEMS = [
  { href: "/", label: "Главная", icon: "⌂" },
  { href: "/nutrition", label: "Питание", icon: "◷" },
  { href: "/training", label: "Тренировки", icon: "↗" },
  { href: "/finance", label: "Финансы", icon: "¤" },
  { href: "/family", label: "Семья", icon: "♥" },
  { href: "/progress", label: "Прогресс", icon: "◎" },
  { href: "/profile", label: "Профиль", icon: "☺" },
];

/** Пункт активен, если адрес страницы совпадает с ним: "/nutrition" для "/nutrition". */
function isActive(pathname: string, href: string): boolean {
  return href === "/" ? pathname === "/" : pathname.startsWith(href);
}

/**
 * Рама для всех страниц после входа.
 * Загружает профиль (GET /users/me), показывает меню и передаёт профиль страницам
 * через контекст. Без токена запрос профиля вернёт 401, и apiRequest отправит
 * пользователя на /login.
 */
export default function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { data: profile, error, reload } = useAsyncData(getProfile);

  // Пока профиля нет: показываем загрузку или ошибку (с кнопкой повтора)
  if (profile === null) {
    return error ? (
      <div className="p-6">
        <ErrorBanner message={error} onRetry={reload} />
      </div>
    ) : (
      <div className="flex min-h-screen items-center justify-center text-slate-500">
        Загрузка...
      </div>
    );
  }

  // Часовой пояс устройства, например "Europe/Berlin"
  const deviceZone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  const zoneMismatch = profile.timezone !== deviceZone;

  return (
    <ProfileContext.Provider value={{ profile, refreshProfile: reload }}>
      <div className="min-h-screen bg-[#f5f6f8] text-slate-900">
        <div className="mx-auto flex min-h-screen max-w-[1440px]">
          {/* Боковое меню: только на экранах от md */}
          <aside className="hidden w-64 shrink-0 flex-col border-r border-slate-200 bg-white p-6 md:flex">
            <div className="mb-10 flex items-center gap-3">
              <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-emerald-600 text-xl font-bold text-white">
                B
              </div>
              <div>
                <p className="font-bold tracking-tight">Balance</p>
                <p className="text-xs text-slate-500">Nutrition & Training</p>
              </div>
            </div>

            <nav className="space-y-2">
              {NAV_ITEMS.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`flex items-center gap-3 rounded-xl px-4 py-3 text-sm font-medium transition ${
                    isActive(pathname, item.href)
                      ? "bg-emerald-50 text-emerald-700"
                      : "text-slate-600 hover:bg-slate-50"
                  }`}
                >
                  <span className="text-lg">{item.icon}</span>
                  {item.label}
                </Link>
              ))}
            </nav>

            <div className="mt-auto space-y-3">
              <p className="truncate text-sm text-slate-500">{profile.name}</p>
              <Button variant="secondary" onClick={logout}>
                Выйти
              </Button>
            </div>
          </aside>

          <main className="min-w-0 flex-1 p-4 pb-24 sm:p-6 md:pb-10 lg:p-10">
            {zoneMismatch && (
              <div className="mb-6 rounded-xl bg-amber-50 px-4 py-3 text-sm text-amber-800">
                Часовой пояс профиля ({profile.timezone}) отличается от часового пояса
                устройства ({deviceZone}). Итоги питания считаются по поясу профиля.{" "}
                <Link href="/profile" className="font-medium underline">
                  Изменить в профиле
                </Link>
              </div>
            )}
            {children}
          </main>
        </div>

        {/* Нижняя панель: только на телефоне; отступ учитывает «домашнюю» полосу iPhone */}
        <nav
          className="fixed inset-x-0 bottom-0 z-10 flex border-t border-slate-200 bg-white md:hidden"
          style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
        >
          {NAV_ITEMS.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={`flex min-w-0 flex-1 flex-col items-center gap-0.5 py-2 text-[10px] ${
                isActive(pathname, item.href) ? "text-emerald-700" : "text-slate-500"
              }`}
            >
              <span className="text-lg">{item.icon}</span>
              {item.label}
            </Link>
          ))}
        </nav>
      </div>
    </ProfileContext.Provider>
  );
}