"use client";

import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from "react";

/** Цвет значка-метки. */
export type Tone = "slate" | "green" | "amber" | "red";

/** Белая карточка с необязательными заголовком и блоком действий справа. */
export function Card({
  title,
  action,
  children,
}: {
  title?: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5 sm:p-6">
      {(title || action) && (
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          {title && <h2 className="text-lg font-bold">{title}</h2>}
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

/** Заголовок страницы с подзаголовком. */
export function PageHeader({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <header className="mb-6">
      <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">{title}</h1>
      {subtitle && <p className="mt-1 text-sm text-slate-500">{subtitle}</p>}
    </header>
  );
}

/** Красное сообщение об ошибке с необязательной кнопкой повтора. */
export function ErrorBanner({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div
      role="alert"
      className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700"
    >
      <span>{message}</span>
      {onRetry && (
        <button type="button" onClick={onRetry} className="font-medium underline">
          Повторить
        </button>
      )}
    </div>
  );
}

/** Зелёное сообщение об успехе. */
export function SuccessNotice({ message }: { message: string }) {
  return (
    <div role="status" className="rounded-xl bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
      {message}
    </div>
  );
}

/** Текст «Загрузка...». */
export function Loading({ text = "Загрузка..." }: { text?: string }) {
  return <p className="text-sm text-slate-500">{text}</p>;
}

const BADGE_TONES: Record<Tone, string> = {
  slate: "bg-slate-100 text-slate-600",
  green: "bg-emerald-50 text-emerald-700",
  amber: "bg-amber-50 text-amber-700",
  red: "bg-red-50 text-red-700",
};

/** Маленькая цветная метка, например статус. */
export function Badge({ children, tone = "slate" }: { children: ReactNode; tone?: Tone }) {
  return (
    <span className={`inline-flex rounded-full px-3 py-1 text-xs font-medium ${BADGE_TONES[tone]}`}>
      {children}
    </span>
  );
}

const FIELD_CLASS =
  "w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none focus:border-emerald-600";

type TextFieldProps = Omit<InputHTMLAttributes<HTMLInputElement>, "onChange" | "value"> & {
  label: string;
  value: string;
  // Получает новый текст поля, а не событие: onChange={setName}
  onChange: (value: string) => void;
  hint?: string;
};

/** Поле ввода с подписью. Подходит для текста, чисел, дат и времени (параметр type). */
export function TextField({ label, onChange, hint, ...inputProps }: TextFieldProps) {
  return (
    <label className="block space-y-1.5">
      <span className="text-sm font-medium text-slate-700">{label}</span>
      <input {...inputProps} onChange={(event) => onChange(event.target.value)} className={FIELD_CLASS} />
      {hint && <span className="block text-xs text-slate-500">{hint}</span>}
    </label>
  );
}

/** Выпадающий список с подписью. options — пары [значение, подпись]. */
export function SelectField({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: [string, string][];
}) {
  return (
    <label className="block space-y-1.5">
      <span className="text-sm font-medium text-slate-700">{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value)} className={FIELD_CLASS}>
        {options.map(([optionValue, optionLabel]) => (
          <option key={optionValue} value={optionValue}>
            {optionLabel}
          </option>
        ))}
      </select>
    </label>
  );
}

const BUTTON_VARIANTS = {
  primary: "bg-emerald-700 text-white hover:bg-emerald-800",
  secondary: "border border-slate-200 bg-white text-slate-700 hover:bg-slate-50",
  danger: "border border-red-200 bg-white text-red-600 hover:bg-red-50",
};

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: keyof typeof BUTTON_VARIANTS;
  // true блокирует кнопку на время запроса
  loading?: boolean;
};

/** Кнопка. По умолчанию type="button"; для отправки формы передайте type="submit". */
export function Button({
  variant = "primary",
  loading = false,
  disabled,
  type = "button",
  children,
  ...rest
}: ButtonProps) {
  return (
    <button
      {...rest}
      type={type}
      disabled={disabled || loading}
      className={`rounded-xl px-4 py-2 text-sm font-medium transition disabled:opacity-60 ${BUTTON_VARIANTS[variant]}`}
    >
      {children}
    </button>
  );
}