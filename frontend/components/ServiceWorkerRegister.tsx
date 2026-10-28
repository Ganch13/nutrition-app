"use client";

import { useEffect } from "react";

/**
 * Подключает service worker (public/sw.js), который показывает страницу «Нет соединения» без интернета.
 * Работает только в боевой сборке: при разработке он мешал бы горячей перезагрузке страниц.
 * Ничего не отображает.
 */
export default function ServiceWorkerRegister() {
  useEffect(() => {
    if (process.env.NODE_ENV !== "production" || !("serviceWorker" in navigator)) return;

    // updateViaCache: "none" — файл sw.js всегда проверяется на сервере, поэтому обновления доходят сразу
    navigator.serviceWorker
      .register("/sw.js", { scope: "/", updateViaCache: "none" })
      .catch(() => {
        // Приложение работает и без service worker, ошибку регистрации показывать пользователю незачем
      });
  }, []);

  return null;
}
