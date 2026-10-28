"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { logout } from "@/lib/api";
import { BRAND } from "@/lib/brand";
import { getProfile } from "@/lib/endpoints";
import { ProfileContext } from "@/lib/profile-context";
import { useAsyncData } from "@/lib/use-async-data";
import { BrandMark, Wordmark } from "./BrandMark";
import IncomePromptDialog from "./finance/IncomePromptDialog";
import { Icon, type IconName } from "./icons";
import SplashScreen from "./SplashScreen";
import { Button, ErrorBanner, Notice } from "./ui";

type NavItem = {
  href: string;
  label: string;
  // Подпись в узкой нижней панели телефона, если полное название не помещается
  shortLabel?: string;
  icon: IconName;
  // true — пункт стоит в нижней панели телефона; остальные открываются кнопкой «Ещё»
  primary?: boolean;
};

// Меню сгруппировано по смыслу: так проще найти нужный раздел, чем в плоском списке из четырнадцати пунктов.
// На компьютере группы видны в боковом меню, на телефоне в панели «Ещё».
const NAV_GROUPS: { title: string; items: NavItem[] }[] = [
  {
    title: "Сегодня",
    items: [
      { href: "/", label: "Главная", icon: "home", primary: true },
      { href: "/schedule", label: "Расписание", icon: "calendar", primary: true },
    ],
  },
  {
    title: "Еда",
    items: [
      { href: "/meal-plan", label: "Меню на неделю", shortLabel: "Меню", icon: "menu", primary: true },
      { href: "/nutrition", label: "Питание", icon: "bowl", primary: true },
      { href: "/shopping", label: "Закупки и готовка", icon: "cart" },
      { href: "/family-menu", label: "Семейное меню", icon: "users" },
      { href: "/recipes", label: "Рецепты", icon: "book" },
      { href: "/foods", label: "Продукты", icon: "leaf" },
    ],
  },
  {
    title: "Тело",
    items: [
      { href: "/training", label: "Тренировки", icon: "dumbbell", primary: true },
      { href: "/norms", label: "Нормы и цели", icon: "target" },
      { href: "/progress", label: "Прогресс", icon: "trend" },
    ],
  },
  {
    title: "Дом",
    items: [
      { href: "/finance", label: "Финансы", icon: "wallet" },
      { href: "/family", label: "Семья", icon: "heart" },
    ],
  },
];

const ALL_ITEMS = NAV_GROUPS.flatMap((group) => group.items);
const PRIMARY_ITEMS = ALL_ITEMS.filter((item) => item.primary);
const MORE_GROUPS = NAV_GROUPS.map((group) => ({
  title: group.title,
  items: group.items.filter((item) => !item.primary),
})).filter((group) => group.items.length > 0);

/** Пункт активен, если адрес страницы совпадает с ним: "/nutrition" для "/nutrition". */
function isActive(pathname: string, href: string): boolean {
  // "/family" не должен считаться открытым на странице "/family-menu", поэтому сравниваем целыми сегментами
  return href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);
}

/**
 * Рама для всех страниц после входа.
 * Загружает профиль (GET /users/me), показывает меню и передаёт профиль страницам
 * через контекст. Без токена запрос профиля вернёт 401, и apiRequest отправит
 * пользователя на /login. Пока профиль грузится, показывается заставка с названием приложения.
 */
export default function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { data: profile, error, reload } = useAsyncData(getProfile);
  // Открыта ли панель «Ещё» в нижнем меню телефона
  const [moreOpen, setMoreOpen] = useState(false);

  // Escape закрывает панель «Ещё»
  useEffect(() => {
    if (!moreOpen) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMoreOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [moreOpen]);

  // Пока профиля нет: заставка или ошибка (с кнопкой повтора)
  if (profile === null) {
    if (!error) return <SplashScreen onRetry={reload} />;
    return (
      <div className="flex min-h-dvh flex-col items-center justify-center gap-5 px-6 text-center">
        <BrandMark size={72} />
        <div className="w-full max-w-sm space-y-3">
          <ErrorBanner message={error} onRetry={reload} />
          <Button variant="ghost" onClick={logout}>
            Выйти из аккаунта
          </Button>
        </div>
      </div>
    );
  }

  // Часовой пояс устройства, например "Europe/Berlin"
  const deviceZone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  const zoneMismatch = profile.timezone !== deviceZone;
  const initial = profile.name.trim().charAt(0).toUpperCase() || "?";

  return (
    <ProfileContext.Provider value={{ profile, refreshProfile: reload }}>
      <div className="min-h-dvh">
        {/* Боковое меню: только на экранах от md. Тёмный индиго отделяет навигацию от содержимого */}
        <aside className="fixed inset-y-0 left-0 z-20 hidden w-64 flex-col bg-brand-950 md:flex">
          <Link href="/" className="flex items-center gap-3 px-6 pb-4 pt-7 text-white">
            <BrandMark size={40} />
            <div className="min-w-0">
              <Wordmark height={26} />
              <p className="mt-1 truncate text-xs text-brand-300">{BRAND.tagline}</p>
            </div>
          </Link>

          <nav aria-label="Разделы" className="flex-1 overflow-y-auto px-3 pb-4">
            {NAV_GROUPS.map((group) => (
              <div key={group.title}>
                <p className="px-3 pb-1 pt-5 text-xs font-medium text-brand-300">{group.title}</p>
                <ul className="space-y-0.5">
                  {group.items.map((item) => {
                    const active = isActive(pathname, item.href);
                    return (
                      <li key={item.href}>
                        <Link
                          href={item.href}
                          aria-current={active ? "page" : undefined}
                          className={`flex items-center gap-3 rounded-xl px-3 py-2 text-sm font-medium transition ${
                            active
                              ? "bg-white/12 text-white"
                              : "text-brand-200 hover:bg-white/8 hover:text-white"
                          }`}
                        >
                          <Icon name={item.icon} size={20} />
                          {item.label}
                          {active && <span className="ml-auto size-1.5 rounded-full bg-saffron" aria-hidden="true" />}
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))}
          </nav>

          <div className="border-t border-white/10 p-3">
            <Link
              href="/profile"
              aria-current={isActive(pathname, "/profile") ? "page" : undefined}
              className={`flex items-center gap-3 rounded-xl px-3 py-2 text-sm transition ${
                isActive(pathname, "/profile") ? "bg-white/12 text-white" : "text-brand-100 hover:bg-white/8"
              }`}
            >
              <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-brand-700 text-sm font-semibold text-white">
                {initial}
              </span>
              <span className="min-w-0">
                <span className="block truncate font-medium">{profile.name}</span>
                <span className="block text-xs text-brand-300">Профиль и настройки</span>
              </span>
            </Link>
            <button
              type="button"
              onClick={logout}
              className="mt-1 flex w-full items-center gap-3 rounded-xl px-3 py-2 text-sm text-brand-200 transition hover:bg-white/8 hover:text-white"
            >
              <Icon name="logout" size={20} />
              Выйти
            </button>
          </div>
        </aside>

        <div className="md:pl-64">
          <main className="mx-auto w-full max-w-6xl px-4 pb-28 pt-5 sm:px-6 md:px-10 md:pb-12 md:pt-9">
            {zoneMismatch && (
              <div className="mb-6">
                <Notice tone="warning">
                  Часовой пояс профиля ({profile.timezone}) отличается от часового пояса устройства ({deviceZone}).
                  Итоги питания считаются по поясу профиля.{" "}
                  <Link href="/profile" className="font-medium underline underline-offset-2">
                    Изменить в профиле
                  </Link>
                </Notice>
              </div>
            )}
            {children}
          </main>
        </div>

        {/* «Поступил ли платёж?»: появляется поверх любой страницы за два дня до ожидаемого дохода и до двух дней после */}
        <IncomePromptDialog zone={profile.timezone} />

        {/* Панель «Ещё»: остальные разделы, профиль и выход (только на телефоне) */}
        {moreOpen && (
          <>
            <button
              type="button"
              aria-label="Закрыть меню"
              onClick={() => setMoreOpen(false)}
              className="fixed inset-0 z-20 bg-brand-950/40 md:hidden"
            />
            <div
              role="dialog"
              aria-label="Все разделы"
              className="fixed inset-x-0 bottom-[calc(3.75rem+env(safe-area-inset-bottom))] z-30 max-h-[75dvh] overflow-y-auto rounded-t-3xl border-t border-slate-200 bg-white p-5 shadow-[0_-12px_32px_-12px_rgba(24,29,77,0.25)] md:hidden"
            >
              {MORE_GROUPS.map((group) => (
                <div key={group.title} className="mb-4">
                  <p className="mb-2 text-xs font-medium text-slate-500">{group.title}</p>
                  <div className="grid grid-cols-3 gap-2">
                    {group.items.map((item) => (
                      <Link
                        key={item.href}
                        href={item.href}
                        onClick={() => setMoreOpen(false)}
                        aria-current={isActive(pathname, item.href) ? "page" : undefined}
                        className={`flex flex-col items-center gap-1.5 rounded-2xl px-2 py-3 text-center text-xs font-medium ${
                          isActive(pathname, item.href)
                            ? "bg-brand-50 text-brand-700"
                            : "bg-slate-50 text-slate-700 active:bg-slate-100"
                        }`}
                      >
                        <Icon name={item.icon} size={22} />
                        {item.label}
                      </Link>
                    ))}
                  </div>
                </div>
              ))}
              <div className="flex items-center justify-between gap-3 border-t border-slate-100 pt-4">
                <Link
                  href="/profile"
                  onClick={() => setMoreOpen(false)}
                  className="flex min-w-0 items-center gap-3 text-sm font-medium text-slate-800"
                >
                  <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-brand-700 font-semibold text-white">
                    {initial}
                  </span>
                  <span className="min-w-0">
                    <span className="block truncate">{profile.name}</span>
                    <span className="block text-xs font-normal text-slate-500">Профиль и настройки</span>
                  </span>
                </Link>
                <Button variant="secondary" onClick={logout}>
                  Выйти
                </Button>
              </div>
            </div>
          </>
        )}

        {/* Нижняя панель: только на телефоне; отступ учитывает «домашнюю» полосу iPhone */}
        <nav
          aria-label="Основные разделы"
          className="fixed inset-x-0 bottom-0 z-30 flex border-t border-slate-200 bg-white/95 backdrop-blur md:hidden"
          style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
        >
          {PRIMARY_ITEMS.map((item) => {
            const active = isActive(pathname, item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setMoreOpen(false)}
                aria-current={active ? "page" : undefined}
                className={`relative flex min-h-15 min-w-0 flex-1 flex-col items-center justify-center gap-1 text-[11px] font-medium ${
                  active ? "text-brand-700" : "text-slate-500"
                }`}
              >
                {active && <span className="absolute top-1.5 size-1 rounded-full bg-saffron" aria-hidden="true" />}
                <Icon name={item.icon} size={22} />
                {item.shortLabel ?? item.label}
              </Link>
            );
          })}
          <button
            type="button"
            onClick={() => setMoreOpen(!moreOpen)}
            aria-expanded={moreOpen}
            className={`relative flex min-h-15 min-w-0 flex-1 flex-col items-center justify-center gap-1 text-[11px] font-medium ${
              moreOpen ||
              isActive(pathname, "/profile") ||
              MORE_GROUPS.some((group) => group.items.some((item) => isActive(pathname, item.href)))
                ? "text-brand-700"
                : "text-slate-500"
            }`}
          >
            <Icon name="more" size={22} strokeWidth={2.5} />
            Ещё
          </button>
        </nav>
      </div>
    </ProfileContext.Provider>
  );
}
