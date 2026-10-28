# Лад: интерфейс (Next.js)

Сайт приложения «Лад» на Next.js 16, React 19, TypeScript и Tailwind CSS 4. Данные приходят от backend (FastAPI) через `lib/api.ts`.

## Запуск на своём компьютере

```powershell
cd frontend
npm install
npm run dev          # http://localhost:3000
```

Адрес backend берётся из `.env.local` (образец: `.env.local.example`). Проверка типов: `npx tsc --noEmit`. Сборка: `npm run build`.

## Что где лежит

| Папка или файл | Что внутри |
| --- | --- |
| `app/` | страницы (`app/(app)/…` после входа, `login`, `register`), `layout.tsx`, `manifest.ts`, `globals.css` с цветами и шрифтами |
| `components/` | общие части: `ui.tsx` (кнопки, поля, карточки), `AppShell.tsx` (меню), `icons.tsx`, `finance/` (раздел «Финансы») |
| `lib/` | `api.ts` (запросы, токены, обновление сессии), `endpoints.ts` (все вызовы API), `types.ts`, `format.ts`, `brand.ts` (название) |
| `public/` | значки, заставки, шрифты, `sw.js` (service worker), `offline.html` |
| `design/` | скрипт пересоздания значков и заставок |

Название, цвета, шрифты и правила оформления: [DESIGN.md](DESIGN.md). Развёртывание: [../deploy/README.md](../deploy/README.md), обновление работающего сервера: [../deploy/UPDATE.md](../deploy/UPDATE.md).
