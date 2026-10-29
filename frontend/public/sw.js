// Service worker приложения «Лад» (PWA).
//
// Что он делает:
//   * когда нет интернета, сервер выключен или молчит дольше NAVIGATION_TIMEOUT_MS, при открытии страницы
//     показывает понятную страницу /offline.html из кэша вместо пустого экрана или ошибки браузера.
//     Сама страница выбирает текст: «Нет подключения к интернету» (у устройства нет сети) или
//     «Сервер недоступен, попробуйте позже» (сеть есть, а сервер не отвечает), и даёт кнопку «Повторить»;
//   * запоминает неизменяемые файлы сайта (/_next/static/...), поэтому приложение открывается быстрее.
//
// Чего он НЕ делает намеренно: не кэширует ответы API и страницы, не хранит никаких личных данных.
// Данные всегда берутся с сервера, поэтому после выхода из аккаунта на устройстве ничего не остаётся.

const VERSION = "v5";
// Два отдельных кэша: страница «нет соединения» не должна вытесняться файлами сайта при очистке
const OFFLINE_CACHE = `lad-offline-${VERSION}`;
const STATIC_CACHE = `lad-static-${VERSION}`;
const OFFLINE_URL = "/offline.html";
// Сколько файлов держать в кэше; при переполнении удаляются самые старые (после обновлений сайта файлы меняются)
const MAX_STATIC_ENTRIES = 150;
// Сколько ждать сервер при открытии страницы. Дольше — показываем «Сервер недоступен» вместо вечной загрузки
const NAVIGATION_TIMEOUT_MS = 20_000;
// Ответы прокси (Caddy), когда сам сервер приложения выключен или не отвечает
const SERVER_DOWN_STATUSES = [502, 503, 504];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(OFFLINE_CACHE)
      // Страница ошибки самодостаточна: стили, значок и скрипт записаны прямо в ней
      .then((cache) => cache.add(OFFLINE_URL))
      // Новая версия начинает работать сразу, не дожидаясь закрытия всех вкладок
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      // Удаляем кэши прежних версий, в том числе старые «balance-...» от времён, когда приложение называлось Balance
      const names = await caches.keys();
      await Promise.all(
        names
          .filter(
            (name) =>
              (name.startsWith("lad-") || name.startsWith("balance-")) && name !== STATIC_CACHE && name !== OFFLINE_CACHE,
          )
          .map((name) => caches.delete(name)),
      );
      await self.clients.claim();
    })(),
  );
});

async function trim(cache) {
  const keys = await cache.keys();
  for (const key of keys.slice(0, Math.max(0, keys.length - MAX_STATIC_ENTRIES))) {
    await cache.delete(key);
  }
}

/**
 * Открытие страницы. Пример: сервер ответил за 2 с → его страница; сервер выключен (сеть есть, но соединение
 * не устанавливается), прокси ответил 502 или прошло 20 с без ответа → /offline.html из кэша.
 * Обычные ответы сервера (в том числе 404) показываются как есть.
 */
async function navigate(request) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), NAVIGATION_TIMEOUT_MS);
  try {
    const response = await fetch(request, { signal: controller.signal });
    if (!SERVER_DOWN_STATUSES.includes(response.status)) return response;
  } catch {
    // Нет сети, сервер не принимает соединения или истёк тайм-аут
  } finally {
    clearTimeout(timer);
  }
  return (await caches.match(OFFLINE_URL)) ?? Response.error();
}

self.addEventListener("fetch", (event) => {
  const request = event.request;

  // Изменяющие запросы (вход, сохранение данных) и всё, что идёт с токеном, service worker не трогает
  if (request.method !== "GET" || request.headers.has("authorization")) return;

  const url = new URL(request.url);

  // Чужие адреса (в том числе backend на другом порту) и API на этом же домене — напрямую в сеть
  if (url.origin !== self.location.origin || url.pathname.startsWith("/api/")) return;

  // Открытие страницы: всегда с сервера; если сервер недоступен — страница ошибки из кэша
  if (request.mode === "navigate") {
    event.respondWith(navigate(request));
    return;
  }

  // Файлы сайта с хешем в имени никогда не меняются: можно отдавать из кэша
  if (url.pathname.startsWith("/_next/static/")) {
    event.respondWith(
      caches.open(STATIC_CACHE).then(async (cache) => {
        const cached = await cache.match(request);
        if (cached) return cached;
        const response = await fetch(request);
        if (response.ok) {
          cache.put(request, response.clone()).then(() => trim(cache));
        }
        return response;
      }),
    );
  }
});
