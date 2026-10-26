import { useCallback, useEffect, useState } from "react";
import { getErrorText } from "./api";

/** Итог одного запроса вместе с тем, для каких параметров он получен. */
type Settled<T> = {
  loader: () => Promise<T>;
  reloadCount: number;
  data: T | null;
  error: string | null;
};

/**
 * Загружает данные при показе страницы и по команде reload().
 *
 * Аргумент loader — функция запроса. Её нужно оборачивать в useCallback,
 * чтобы запрос повторялся только при смене зависимостей (например, userId или date).
 *
 * Результат, например: { data: [...], loading: false, error: null, reload }
 *  - data    — последние полученные данные (null, пока их не было);
 *  - loading — true, пока идёт запрос для текущих параметров;
 *  - error   — текст ошибки или null;
 *  - reload  — запускает запрос заново (после добавления или удаления записи).
 */
export function useAsyncData<T>(loader: () => Promise<T>) {
  const [reloadCount, setReloadCount] = useState(0);
  const [settled, setSettled] = useState<Settled<T> | null>(null);

  useEffect(() => {
    // cancelled не даёт записать устаревший результат, если параметры
    // сменились или страница закрыта до ответа сервера
    let cancelled = false;

    loader().then(
      (data) => {
        if (!cancelled) setSettled({ loader, reloadCount, data, error: null });
      },
      (error: unknown) => {
        if (!cancelled) {
          setSettled({ loader, reloadCount, data: null, error: getErrorText(error) });
        }
      },
    );

    return () => {
      cancelled = true;
    };
  }, [loader, reloadCount]);

  const reload = useCallback(() => setReloadCount((count) => count + 1), []);

  // Результат актуален, если получен для текущих loader и reloadCount
  const current =
    settled !== null && settled.loader === loader && settled.reloadCount === reloadCount
      ? settled
      : null;

  return {
    data: settled?.data ?? null,
    loading: current === null,
    error: current?.error ?? null,
    reload,
  };
}