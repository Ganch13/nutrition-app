"use client";

import { useEffect, useState } from "react";
import { NO_INTERNET_TEXT, SERVER_DOWN_TEXT } from "@/lib/api";
import { BRAND } from "@/lib/brand";
import { BrandMark, Wordmark } from "./BrandMark";
import { Button } from "./ui";

/**
 * Экран загрузки на всю площадь: значок, название и короткая подпись о том, что происходит.
 * Показывается, пока приложение получает ваш профиль после запуска. Выглядит так же, как заставка iPhone
 * (public/splash), поэтому переход от запуска к приложению незаметен.
 * Этапы:
 *   * до 8 секунд — индикатор и «Загружаем ваши данные»;
 *   * после 8 секунд — «Связь медленная», подсказка и кнопка «Повторить»;
 *   * после 30 секунд — индикатор пропадает, вместо него ошибка: «Нет подключения к интернету», если у устройства
 *     нет сети, иначе «Сервер недоступен, попробуйте позже», и кнопка «Повторить». Бесконечной загрузки не бывает.
 * Когда сеть возвращается (событие online), повтор запускается сам.
 * onRetry — что делать по кнопке (обычно перезапросить данные).
 */
// Через сколько миллисекунд сказать «Связь медленная» и когда перестать ждать
const SLOW_MS = 8_000;
const GIVE_UP_MS = 30_000;

export default function SplashScreen({ onRetry }: { onRetry?: () => void }) {
  // "loading" → "slow" → "failed"; attempt увеличивается при «Повторить» и перезапускает таймеры
  const [phase, setPhase] = useState<"loading" | "slow" | "failed">("loading");
  const [attempt, setAttempt] = useState(0);
  // Текст ошибки на этапе failed: зависит от того, есть ли сеть у устройства в этот момент
  const [failure, setFailure] = useState(SERVER_DOWN_TEXT);

  useEffect(() => {
    const slowTimer = window.setTimeout(() => setPhase("slow"), SLOW_MS);
    const failTimer = window.setTimeout(() => {
      setFailure(navigator.onLine === false ? NO_INTERNET_TEXT : SERVER_DOWN_TEXT);
      setPhase("failed");
    }, GIVE_UP_MS);
    return () => {
      window.clearTimeout(slowTimer);
      window.clearTimeout(failTimer);
    };
  }, [attempt]);

  /** «Повторить»: снова ждём с начала и просим страницу перезапросить данные. */
  function retry() {
    setPhase("loading");
    setAttempt((value) => value + 1);
    onRetry?.();
  }

  // Сеть вернулась — повторяем сами
  useEffect(() => {
    if (!onRetry) return;
    const onOnline = () => {
      setPhase("loading");
      setAttempt((value) => value + 1);
      onRetry();
    };
    window.addEventListener("online", onOnline);
    return () => window.removeEventListener("online", onOnline);
  }, [onRetry]);

  const slow = phase === "slow";

  return (
    <div className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-[#f4f5fb] px-8 text-center">
      <div className="lad-rise flex flex-col items-center">
        <BrandMark size={104} pulse />
        <div className="mt-6 text-slate-900">
          <Wordmark height={40} />
        </div>
        <p className="mt-2 text-sm text-slate-500">{BRAND.tagline}</p>
      </div>

      {phase === "failed" ? (
        <div className="lad-rise mt-10 max-w-xs space-y-3" role="alert">
          <p className="text-base font-semibold text-slate-900">{failure}</p>
          <p className="text-sm text-slate-600">Ваши данные в сохранности. Попробуйте ещё раз чуть позже.</p>
          <Button onClick={retry}>Повторить</Button>
        </div>
      ) : (
        <div className="mt-10 flex w-40 flex-col items-center gap-3" role="status" aria-live="polite">
          <div className="relative h-1 w-full overflow-hidden rounded-full bg-slate-200">
            <div className="lad-track absolute inset-y-0 left-0 w-2/5 rounded-full bg-saffron" />
          </div>
          <p className="text-xs text-slate-500">{slow ? "Связь медленная" : "Загружаем ваши данные"}</p>
        </div>
      )}

      {slow && (
        <div className="lad-rise mt-4 max-w-xs space-y-3">
          <p className="text-sm text-slate-600">
            Приложение всё ещё ждёт ответа сервера. Проверьте интернет: если связь есть, подождите ещё немного или
            повторите.
          </p>
          {onRetry && (
            <Button variant="secondary" onClick={retry}>
              Повторить
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
