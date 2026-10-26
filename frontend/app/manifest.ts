import type { MetadataRoute } from "next";

/** Манифест PWA: Next.js отдаёт его как /manifest.webmanifest и сам подключает к страницам. */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Balance — питание и тренировки",
    short_name: "Balance",
    description: "Планирование питания и тренировок",
    start_url: "/",
    // standalone: открывается как отдельное приложение, без панели браузера
    display: "standalone",
    background_color: "#f5f6f8",
    theme_color: "#047857",
    lang: "ru",
    icons: [
      { src: "/pwa-icon?size=192", sizes: "192x192", type: "image/png" },
      { src: "/pwa-icon?size=512", sizes: "512x512", type: "image/png" },
    ],
  };
}