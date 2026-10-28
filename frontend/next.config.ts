import type { NextConfig } from "next";

const isDev = process.env.NODE_ENV === "development";

// Адрес backend из .env.local / сборки: "http://localhost:8000" (разработка, локальный Docker)
// или "/api" (публичный сервер: сайт и API на одном домене).
const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "";
const apiOrigin = apiUrl.startsWith("http") ? new URL(apiUrl).origin : null;

// Политика содержимого (CSP) говорит браузеру, откуда странице можно загружать скрипты, картинки и
// куда отправлять запросы. Если злоумышленнику удастся внедрить в страницу чужой код, браузер не даст
// ему отправить данные на чужой сервер.
// 'unsafe-inline' для скриптов и стилей нужен, потому что Next.js вставляет в страницу свои небольшие
// встроенные скрипты; строгий вариант с nonce требует полностью динамической отрисовки всех страниц.
// Остальные правила остаются строгими.
const contentSecurityPolicy = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline'${isDev ? " 'unsafe-eval'" : ""}`,
  "style-src 'self' 'unsafe-inline'",
  // blob: — предпросмотр и показ фото прогресса, загруженных запросом с токеном
  "img-src 'self' blob: data:",
  "font-src 'self' data:",
  // Запросы к API: свой домен и, если backend на другом адресе, он; в разработке ещё веб-сокет горячей перезагрузки
  `connect-src 'self'${apiOrigin ? ` ${apiOrigin}` : ""}${isDev ? " ws: wss:" : ""}`,
  "manifest-src 'self'",
  "worker-src 'self'",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
  // Автоматически переводить http-ссылки на https. Только на публичном сервере: на localhost по http это сломало бы страницы
  ...(!isDev && (apiOrigin === null || apiOrigin.startsWith("https://")) ? ["upgrade-insecure-requests"] : []),
].join("; ");

const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  // Приложению не нужны камера, микрофон и геолокация (фото выбираются через обычное окно выбора файла)
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
  // В разработке CSP не отправляем: она мешает инструментам отладки
  ...(isDev ? [] : [{ key: "Content-Security-Policy", value: contentSecurityPolicy }]),
];

const nextConfig: NextConfig = {
  /* config options here */
  experimental: {
    agentFeedback: true,
  },
  cacheComponents: true,
  partialPrefetching: true,
  // Не сообщать в заголовке X-Powered-By, на чём работает сайт
  poweredByHeader: false,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  async headers() {
    return [
      { source: "/:path*", headers: securityHeaders },
      {
        // Шрифты не меняются: браузер может хранить их год и не спрашивать сервер
        source: "/fonts/:path*",
        headers: [{ key: "Cache-Control", value: "public, max-age=31536000, immutable" }],
      },
      {
        // Значки и заставки меняются редко: сутки в кэше, потом проверка
        source: "/:folder(icons|splash|brand)/:path*",
        headers: [{ key: "Cache-Control", value: "public, max-age=86400" }],
      },
      {
        // Файл service worker не должен кэшироваться браузером, иначе обновления приложения будут доходить с задержкой
        source: "/sw.js",
        headers: [
          { key: "Content-Type", value: "application/javascript; charset=utf-8" },
          { key: "Cache-Control", value: "no-cache, no-store, must-revalidate" },
        ],
      },
    ];
  },
};

export default nextConfig;
