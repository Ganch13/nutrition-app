import type { MetadataRoute } from "next";
import { BRAND } from "@/lib/brand";

/** Манифест PWA: Next.js отдаёт его как /manifest.webmanifest и сам подключает к страницам. */
export default function manifest(): MetadataRoute.Manifest {
  return {
    // id не зависит от start_url и от названия: при переименовании браузер не сочтёт это новым приложением
    id: "/",
    // name — полное название (экран установки, заставка Android), short_name — подпись под значком
    name: BRAND.name,
    short_name: BRAND.name,
    description: BRAND.description,
    start_url: "/",
    scope: "/",
    // standalone: открывается как отдельное приложение, без панели браузера
    display: "standalone",
    orientation: "portrait",
    // Цвет заставки Android и строки состояния: совпадает с фоном приложения
    background_color: BRAND.themeColor,
    theme_color: BRAND.themeColor,
    lang: "ru",
    categories: ["health", "fitness", "lifestyle", "finance"],
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      // maskable: Android обрезает значок по форме своей темы; буква занимает центр, поэтому не обрезается
      { src: "/icons/icon-maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
    // Быстрые действия по долгому нажатию на значок (Android)
    shortcuts: [
      { name: "Питание сегодня", url: "/nutrition" },
      { name: "Меню на неделю", url: "/meal-plan" },
      { name: "Финансы", url: "/finance" },
      { name: "Закупки и готовка", url: "/shopping" },
    ],
  };
}
