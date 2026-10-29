"use client";

import { useEffect, useId, useRef, useState } from "react";
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from "react";
import { Icon } from "./icons";

// Общие «кирпичики» интерфейса: карточка, поля, кнопки, сообщения. Страницы собираются из них,
// поэтому поменяв вид кнопки здесь, вы меняете её во всём приложении.

/** Цвет значка-метки. */
export type Tone = "slate" | "green" | "amber" | "red";

/** Белая карточка с необязательными заголовком и блоком действий справа. */
export function Card({
  title,
  description,
  action,
  children,
}: {
  title?: string;
  // Пояснение под заголовком: что здесь можно сделать
  description?: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5 sm:p-6">
      {(title || action) && (
        <div className={`flex flex-wrap items-center justify-between gap-3 ${description ? "mb-1" : "mb-4"}`}>
          {title && <h2 className="text-lg font-semibold text-slate-900">{title}</h2>}
          {action}
        </div>
      )}
      {description && <p className="mb-4 text-sm text-slate-500">{description}</p>}
      {children}
    </section>
  );
}

/** Заголовок страницы с подзаголовком и необязательной кнопкой справа. */
export function PageHeader({
  title,
  subtitle,
  action,
}: {
  title: string;
  subtitle?: string;
  action?: ReactNode;
}) {
  return (
    <header className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div className="min-w-0">
        <h1 className="text-[1.75rem] font-semibold leading-tight text-slate-900 sm:text-3xl">{title}</h1>
        {subtitle && <p className="mt-1.5 max-w-prose text-sm text-slate-500">{subtitle}</p>}
      </div>
      {action}
    </header>
  );
}

/** Красное сообщение об ошибке с необязательной кнопкой повтора. */
export function ErrorBanner({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div
      role="alert"
      className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-red-100 bg-red-50 px-4 py-3 text-sm text-red-700"
    >
      <span className="flex items-start gap-2.5">
        <Icon name="alert" size={18} className="mt-0.5 shrink-0" />
        <span>{message}</span>
      </span>
      {onRetry && (
        <button type="button" onClick={onRetry} className="font-medium underline underline-offset-2">
          Повторить
        </button>
      )}
    </div>
  );
}

/** Зелёное сообщение об успехе. */
export function SuccessNotice({ message }: { message: string }) {
  return (
    <div
      role="status"
      className="flex items-start gap-2.5 rounded-xl border border-good-100 bg-good-50 px-4 py-3 text-sm text-good-700"
    >
      <Icon name="check" size={18} className="mt-0.5 shrink-0" />
      <span>{message}</span>
    </div>
  );
}

/**
 * Нейтральная или предупреждающая подсказка. tone="warning" — жёлтая, "info" — спокойная синяя.
 * onClose — показать справа крестик «Закрыть» (что делать после закрытия, решает вызывающий код).
 */
export function Notice({
  tone = "info",
  title,
  children,
  onClose,
}: {
  tone?: "info" | "warning";
  title?: string;
  children: ReactNode;
  onClose?: () => void;
}) {
  const style =
    tone === "warning"
      ? "border-amber-200 bg-amber-50 text-amber-800"
      : "border-brand-100 bg-brand-50 text-brand-900";
  return (
    <div className={`flex items-start gap-2.5 rounded-xl border px-4 py-3 text-sm ${style}`}>
      <Icon name={tone === "warning" ? "alert" : "info"} size={18} className="mt-0.5 shrink-0" />
      <div className="min-w-0 flex-1">
        {title && <p className="font-semibold">{title}</p>}
        <div className={title ? "mt-0.5" : ""}>{children}</div>
      </div>
      {onClose && (
        <button
          type="button"
          onClick={onClose}
          aria-label="Закрыть"
          title="Закрыть"
          className="-my-1.5 -mr-2 inline-flex size-8 shrink-0 items-center justify-center rounded-lg opacity-70 transition hover:bg-black/5 hover:opacity-100"
        >
          <Icon name="x" size={16} />
        </button>
      )}
    </div>
  );
}

/** Крутящийся индикатор. Размер задаётся в пикселях. */
export function Spinner({ size = 16 }: { size?: number }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="none"
      aria-hidden="true"
      className="animate-spin"
    >
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeOpacity="0.25" strokeWidth="3" />
      <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}

/** Индикатор «Загрузка...». */
export function Loading({ text = "Загрузка..." }: { text?: string }) {
  return (
    <p role="status" className="flex items-center gap-2 text-sm text-slate-500">
      <Spinner />
      {text}
    </p>
  );
}

/** Пустое состояние: что здесь будет и что сделать, чтобы оно появилось. */
export function EmptyState({
  title,
  children,
  action,
}: {
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="rounded-xl border border-dashed border-slate-300 px-5 py-7 text-center">
      <p className="font-medium text-slate-800">{title}</p>
      {children && <div className="mx-auto mt-1 max-w-sm text-sm text-slate-500">{children}</div>}
      {action && <div className="mt-4 flex justify-center">{action}</div>}
    </div>
  );
}

const BADGE_TONES: Record<Tone, string> = {
  slate: "bg-slate-100 text-slate-600",
  green: "bg-good-50 text-good-700",
  amber: "bg-amber-50 text-amber-800",
  red: "bg-red-50 text-red-700",
};

/** Маленькая цветная метка, например статус. */
export function Badge({ children, tone = "slate" }: { children: ReactNode; tone?: Tone }) {
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${BADGE_TONES[tone]}`}>
      {children}
    </span>
  );
}

// Поля ввода: 16 px на телефоне (iPhone иначе приближает страницу при касании поля), 14 px на компьютере
const FIELD_CLASS =
  "w-full rounded-xl border border-field bg-white px-3.5 py-2.5 text-base text-slate-900 outline-none transition " +
  "placeholder:text-slate-400 focus:border-brand-600 focus:ring-4 focus:ring-brand-100 " +
  "disabled:bg-slate-50 disabled:text-slate-500 sm:text-sm";

const FIELD_ERROR_CLASS = "border-red-500 focus:border-red-600 focus:ring-red-100";

type TextFieldProps = Omit<InputHTMLAttributes<HTMLInputElement>, "onChange" | "value"> & {
  label: string;
  value: string;
  // Получает новый текст поля, а не событие: onChange={setName}
  onChange: (value: string) => void;
  hint?: string;
  // Сообщение об ошибке под полем: красное, поле подсвечивается
  error?: string;
};

/** Подпись, поле и пояснения под ним. Общая часть TextField и PasswordField. */
function FieldShell({
  label,
  hint,
  error,
  htmlFor,
  describedBy,
  children,
}: {
  label: string;
  hint?: string;
  error?: string;
  htmlFor: string;
  describedBy: string;
  children: ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={htmlFor} className="block text-sm font-medium text-slate-700">
        {label}
      </label>
      {children}
      {error ? (
        <p id={describedBy} role="alert" className="text-xs font-medium text-red-600">
          {error}
        </p>
      ) : (
        hint && (
          <p id={describedBy} className="text-xs text-slate-500">
            {hint}
          </p>
        )
      )}
    </div>
  );
}

/** Поле ввода с подписью. Подходит для текста, чисел, дат и времени (параметр type). */
export function TextField({ label, onChange, hint, error, id, className, ...inputProps }: TextFieldProps) {
  const generatedId = useId();
  const inputId = id ?? generatedId;
  const noteId = `${inputId}-note`;
  return (
    <FieldShell label={label} hint={hint} error={error} htmlFor={inputId} describedBy={noteId}>
      <input
        {...inputProps}
        id={inputId}
        onChange={(event) => onChange(event.target.value)}
        aria-invalid={error ? true : undefined}
        aria-describedby={error || hint ? noteId : undefined}
        className={`${FIELD_CLASS} ${error ? FIELD_ERROR_CLASS : ""} ${className ?? ""}`}
      />
    </FieldShell>
  );
}

/**
 * Поле пароля с «глазом» справа: нажатие показывает введённый пароль, повторное нажатие скрывает.
 * Принимает те же параметры, что TextField (кроме type). Пример:
 *   <PasswordField label="Пароль" value={password} onChange={setPassword} autoComplete="current-password" />
 */
export function PasswordField({ label, onChange, hint, error, id, className, ...inputProps }: Omit<TextFieldProps, "type">) {
  const generatedId = useId();
  const inputId = id ?? generatedId;
  const noteId = `${inputId}-note`;
  // Виден ли сейчас пароль. Состояние у каждого поля своё
  const [visible, setVisible] = useState(false);

  return (
    <FieldShell label={label} hint={hint} error={error} htmlFor={inputId} describedBy={noteId}>
      <div className="relative">
        <input
          {...inputProps}
          id={inputId}
          type={visible ? "text" : "password"}
          onChange={(event) => onChange(event.target.value)}
          aria-invalid={error ? true : undefined}
          aria-describedby={error || hint ? noteId : undefined}
          // Пароль не должен автоисправляться и подчёркиваться, пока виден
          autoCapitalize="none"
          autoCorrect="off"
          spellCheck={false}
          className={`${FIELD_CLASS} pr-12 ${error ? FIELD_ERROR_CLASS : ""} ${className ?? ""}`}
        />
        <button
          type="button"
          onClick={() => setVisible((current) => !current)}
          aria-label={visible ? "Скрыть пароль" : "Показать пароль"}
          aria-pressed={visible}
          title={visible ? "Скрыть пароль" : "Показать пароль"}
          className="absolute inset-y-0 right-0 flex w-12 items-center justify-center rounded-r-xl text-slate-500 transition hover:text-slate-900"
        >
          <Icon name={visible ? "eye-off" : "eye"} size={20} />
        </button>
      </div>
    </FieldShell>
  );
}

/** Выпадающий список с подписью. options — пары [значение, подпись]. */
export function SelectField({
  label,
  value,
  onChange,
  options,
  hint,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: [string, string][];
  hint?: string;
}) {
  const id = useId();
  return (
    <FieldShell label={label} hint={hint} htmlFor={id} describedBy={`${id}-note`}>
      <div className="relative">
        <select
          id={id}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          aria-describedby={hint ? `${id}-note` : undefined}
          className={`${FIELD_CLASS} appearance-none pr-10`}
        >
          {options.map(([optionValue, optionLabel]) => (
            <option key={optionValue} value={optionValue}>
              {optionLabel}
            </option>
          ))}
        </select>
        <Icon
          name="chevron-down"
          size={18}
          className="pointer-events-none absolute right-3.5 top-1/2 -translate-y-1/2 text-slate-500"
        />
      </div>
    </FieldShell>
  );
}

/**
 * Переключатель из нескольких вариантов в одну строку (вкладки, «доход / расход»).
 * options — пары [значение, подпись]. Пример: <Segmented value={kind} onChange={setKind} options={[["income","Доход"],["expense","Расход"]]} />
 */
export function Segmented({
  value,
  onChange,
  options,
  label,
}: {
  value: string;
  onChange: (value: string) => void;
  options: [string, string][];
  // Название группы для экранных дикторов
  label: string;
}) {
  // При смене выбора прокручиваем группу так, чтобы выбранный вариант был виден (на узком экране группа листается вбок)
  const groupRef = useRef<HTMLDivElement>(null);
  const mounted = useRef(false);
  useEffect(() => {
    if (!mounted.current) {
      mounted.current = true;
      return;
    }
    groupRef.current?.querySelector('[aria-checked="true"]')?.scrollIntoView({ inline: "nearest", block: "nearest" });
  }, [value]);

  return (
    <div
      ref={groupRef}
      role="radiogroup"
      aria-label={label}
      className="inline-flex max-w-full overflow-x-auto rounded-xl bg-slate-100 p-1"
    >
      {options.map(([optionValue, optionLabel]) => {
        const active = optionValue === value;
        return (
          <button
            key={optionValue}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => onChange(optionValue)}
            className={`min-h-9 shrink-0 whitespace-nowrap rounded-lg px-3.5 text-sm font-medium transition ${
              active ? "bg-white text-slate-900 shadow-sm" : "text-slate-600 hover:text-slate-900"
            }`}
          >
            {optionLabel}
          </button>
        );
      })}
    </div>
  );
}

/**
 * Полоса прогресса. value — доля от 0 до 1. segments — несколько долей разных цветов подряд
 * (например, вклад каждого участника в общую цель); тогда value не нужен.
 */
export function ProgressBar({
  value,
  segments,
  tone = "brand",
  label,
}: {
  value?: number;
  segments?: { share: number; className: string }[];
  tone?: "brand" | "good" | "amber" | "red";
  label: string;
}) {
  const fill = { brand: "bg-brand-600", good: "bg-good-500", amber: "bg-amber-500", red: "bg-red-500" }[tone];
  const total = segments ? segments.reduce((sum, item) => sum + item.share, 0) : (value ?? 0);
  const percent = Math.round(Math.min(1, Math.max(0, total)) * 100);

  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={percent}
      className="flex h-2.5 overflow-hidden rounded-full bg-slate-100"
    >
      {segments ? (
        segments.map((item, index) => (
          <div
            key={index}
            className={`h-full ${item.className}`}
            style={{ width: `${Math.min(100, Math.max(0, item.share * 100))}%` }}
          />
        ))
      ) : (
        <div className={`h-full rounded-full ${fill}`} style={{ width: `${percent}%` }} />
      )}
    </div>
  );
}

const BUTTON_VARIANTS = {
  primary: "bg-brand-700 text-white hover:bg-brand-800 active:bg-brand-900",
  secondary: "border border-slate-300 bg-white text-slate-700 hover:bg-slate-50 active:bg-slate-100",
  // Мягкая кнопка без рамки: второстепенные действия внутри карточек
  ghost: "text-brand-700 hover:bg-brand-50 active:bg-brand-100",
  danger: "border border-red-200 bg-white text-red-600 hover:bg-red-50 active:bg-red-100",
  // Подтверждение необратимого действия: сплошная красная
  "danger-solid": "bg-red-600 text-white hover:bg-red-700 active:bg-red-700",
};

const BUTTON_SIZES = {
  md: "min-h-11 px-4 text-sm sm:min-h-10",
  sm: "min-h-9 px-3 text-sm",
};

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: keyof typeof BUTTON_VARIANTS;
  size?: keyof typeof BUTTON_SIZES;
  // true блокирует кнопку на время запроса и показывает индикатор
  loading?: boolean;
};

/** Кнопка. По умолчанию type="button"; для отправки формы передайте type="submit". */
export function Button({
  variant = "primary",
  size = "md",
  loading = false,
  disabled,
  type = "button",
  className,
  children,
  ...rest
}: ButtonProps) {
  return (
    <button
      {...rest}
      type={type}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={`inline-flex items-center justify-center gap-2 rounded-xl font-medium transition disabled:cursor-not-allowed disabled:opacity-60 ${BUTTON_SIZES[size]} ${BUTTON_VARIANTS[variant]} ${className ?? ""}`}
    >
      {loading && <Spinner size={14} />}
      {children}
    </button>
  );
}

/** Кнопка-значок без текста (например, «закрыть» или «удалить» в строке списка). label обязателен: это подпись для экранных дикторов. */
export function IconButton({
  icon,
  label,
  tone = "neutral",
  ...rest
}: Omit<ButtonHTMLAttributes<HTMLButtonElement>, "children"> & {
  icon: Parameters<typeof Icon>[0]["name"];
  label: string;
  tone?: "neutral" | "danger";
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      {...rest}
      className={`inline-flex size-10 items-center justify-center rounded-xl transition disabled:opacity-60 ${
        tone === "danger"
          ? "text-slate-500 hover:bg-red-50 hover:text-red-600"
          : "text-slate-500 hover:bg-slate-100 hover:text-slate-900"
      }`}
    >
      <Icon name={icon} size={18} />
    </button>
  );
}

/**
 * Всплывающее окно поверх страницы: на телефоне выезжает снизу, на компьютере стоит по центру.
 * Закрывается кнопкой в самом окне, клавишей Escape и нажатием на затемнённый фон; фокус сразу переходит в окно.
 * Пример: <Dialog title="Личные" heading="Новая операция" onClose={close}>форма</Dialog>.
 * title — мелкая подпись сверху (чья книга), heading — крупный заголовок (по нему окно называют экранные дикторы).
 * onClose лучше передавать через useCallback: иначе обработчик Escape переподключается на каждой отрисовке.
 */
export function Dialog({
  title,
  heading,
  onClose,
  children,
}: {
  title?: string;
  heading: string;
  onClose: () => void;
  children: ReactNode;
}) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const headingId = useId();

  // Фокус в окно и закрытие по Escape
  useEffect(() => {
    dialogRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-brand-950/40 sm:items-center sm:p-6" onClick={onClose}>
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={headingId}
        tabIndex={-1}
        onClick={(event) => event.stopPropagation()}
        className="max-h-[90dvh] w-full max-w-md overflow-y-auto rounded-t-3xl bg-white p-5 shadow-xl outline-none sm:rounded-3xl sm:p-6"
        style={{ paddingBottom: "max(1.25rem, env(safe-area-inset-bottom))" }}
      >
        {title && <p className="text-xs font-medium text-slate-500">{title}</p>}
        <h2 id={headingId} className="mt-1 font-display text-2xl font-semibold text-slate-900">
          {heading}
        </h2>
        {children}
      </div>
    </div>
  );
}
