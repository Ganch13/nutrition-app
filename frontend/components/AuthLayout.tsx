import type { ReactNode } from "react";
import { BRAND } from "@/lib/brand";
import { BrandMark, Wordmark } from "./BrandMark";
import { Icon, type IconName } from "./icons";

// Что получает человек: три короткие строки на левой панели экрана входа (только на компьютере)
const PERKS: { icon: IconName; text: string }[] = [
  { icon: "menu", text: "Меню на неделю с учётом тренировок и расписания" },
  { icon: "wallet", text: "Бюджет по зарплатным периодам, а не по календарному месяцу" },
  { icon: "heart", text: "Семья в одном месте: общие закупки, цели и деньги" },
];

/**
 * Общая рама для страниц входа и регистрации.
 * На телефоне: значок и название над формой. На компьютере: слева индиго-панель с названием,
 * справа форма. title — заголовок формы, subtitle — пояснение под ним.
 */
export default function AuthLayout({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
}) {
  return (
    <div className="grid min-h-dvh lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
      <aside className="relative hidden flex-col justify-between overflow-hidden bg-brand-900 p-12 text-white lg:flex">
        <div className="flex items-center gap-4">
          <BrandMark size={56} />
          <Wordmark height={36} />
        </div>

        <div>
          <p className="max-w-sm font-display text-3xl font-semibold leading-snug">{BRAND.tagline}</p>
          <ul className="mt-8 space-y-4">
            {PERKS.map((perk) => (
              <li key={perk.text} className="flex items-start gap-3 text-brand-100">
                <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg bg-white/10">
                  <Icon name={perk.icon} size={18} />
                </span>
                <span className="max-w-xs text-sm leading-relaxed">{perk.text}</span>
              </li>
            ))}
          </ul>
        </div>

        {/* Шафрановая точка из значка: «вы здесь». Единственное яркое пятно на панели */}
        <span className="absolute -right-6 top-1/3 size-14 rounded-full bg-saffron" aria-hidden="true" />
        <span aria-hidden="true" />
      </aside>

      <main className="flex items-center justify-center px-5 py-10 sm:px-8">
        <div className="w-full max-w-md">
          <div className="mb-8 flex items-center gap-3 lg:hidden">
            <BrandMark size={44} />
            <div className="text-slate-900">
              <Wordmark height={26} />
            </div>
          </div>
          <h1 className="text-[1.75rem] font-semibold leading-tight text-slate-900 sm:text-3xl">{title}</h1>
          {subtitle && <p className="mt-2 text-sm text-slate-500">{subtitle}</p>}
          <div className="mt-7">{children}</div>
        </div>
      </main>
    </div>
  );
}
