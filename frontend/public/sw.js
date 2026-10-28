// Service worker приложения «Лад» (PWA).
//
// Что он делает:
//   * когда нет интернета и пользователь открывает страницу, показывает понятную страницу /offline.html
//     вместо ошибки браузера;
//   * запоминает неизменяемые файлы сайта (/_next/static/...), поэтому приложение открывается быстрее.
//
// Чего он НЕ делает намеренно: не кэширует ответы API и страницы, не хранит никаких личных данных.
// Данные всегда берутся с сервера, поэтому после выхода из аккаунта на устройстве ничего не остаётся.

const VERSION = "v2";
// Два отдельных кэша: страница «нет соединения» не должна вытесняться файлами сайта при очистке
const OFFLINE_CACHE = `lad-offline-${VERSION}`;
const STATIC_CACHE = `lad-static-${VERSION}`;
const OFFLINE_URL = "/offline.html";
// Сколько файлов держать в кэше; при переполнении удаляются самые старые (после обновлений сайта файлы меняются)
const MAX_STATIC_ENTRIES = 150;

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(OFFLINE_CACHE)
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

self.addEventListener("fetch", (event) => {
  const request = event.request;

  // Изменяющие запросы (вход, сохранение данных) и всё, что идёт с токеном, service worker не трогает
  if (request.method !== "GET" || request.headers.has("authorization")) return;

  const url = new URL(request.url);

  // Чужие адреса (в том числе backend на другом порту) и API на этом же домене — напрямую в сеть
  if (url.origin !== self.location.origin || url.pathname.startsWith("/api/")) return;

  // Открытие страницы: всегда с сервера; если сети нет — страница «нет соединения»
  if (request.mode === "navigate") {
    event.respondWith(fetch(request).catch(async () => (await caches.match(OFFLINE_URL)) ?? Response.error()));
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
