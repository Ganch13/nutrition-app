"use client";

import { useEffect, useState } from "react";
import { BRAND } from "@/lib/brand";
import { BrandMark, Wordmark } from "./BrandMark";
import { Button } from "./ui";

/**
 * Экран загрузки на всю площадь: значок, название и короткая подпись о том, что происходит.
 * Показывается, пока приложение получает ваш профиль после запуска. Выглядит так же, как заставка iPhone
 * (public/splash), поэтому переход от запуска к приложению незаметен.
 * Если загрузка идёт дольше 8 секунд, появляется подсказка и кнопка «Повторить»: человек не остаётся
 * перед вечным вращением, а понимает, что дело в связи, и может попробовать снова.
 * onRetry — что делать по кнопке (обычно перезапросить данные).
 */
export default function SplashScreen({ onRetry }: { onRetry?: () => void }) {
  const [slow, setSlow] = useState(false);

  useEffect(() => {
    const timer = window.setTimeout(() => setSlow(true), 8000);
    return () => window.clearTimeout(timer);
  }, []);

  return (
    <div className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-[#f4f5fb] px-8 text-center">
      <div className="lad-rise flex flex-col items-center">
        <BrandMark size={104} pulse />
        <div className="mt-6 text-slate-900">
          <Wordmark height={40} />
        </div>
        <p className="mt-2 text-sm text-slate-500">{BRAND.tagline}</p>
      </div>

      <div className="mt-10 flex w-40 flex-col items-center gap-3" role="status" aria-live="polite">
        <div className="relative h-1 w-full overflow-hidden rounded-full bg-slate-200">
          <div className="lad-track absolute inset-y-0 left-0 w-2/5 rounded-full bg-saffron" />
        </div>
        <p className="text-xs text-slate-500">{slow ? "Связь медленная" : "Загружаем ваши данные"}</p>
      </div>

      {slow && (
        <div className="lad-rise mt-4 max-w-xs space-y-3">
          <p className="text-sm text-slate-600">
            Приложение всё ещё ждёт ответа сервера. Проверьте интернет: если связь есть, подождите ещё немного или
            повторите.
          </p>
          {onRetry && (
            <Button variant="secondary" onClick={onRetry}>
              Повторить
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
