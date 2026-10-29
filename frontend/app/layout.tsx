import type { Metadata, Viewport } from "next";
import "./globals.css";
import ServiceWorkerRegister from "@/components/ServiceWorkerRegister";
import { BRAND } from "@/lib/brand";
import { IPHONE_SPLASH } from "@/lib/splash";

// Здесь задаётся то, что видно «снаружи» страницы: название во вкладке браузера (title),
// подпись под значком на экране iPhone (appleWebApp.title) и заставка при запуске (startupImage).
// Само название берётся из lib/brand.ts.
export const metadata: Metadata = {
  title: BRAND.title,
  description: BRAND.description,
  applicationName: BRAND.name,
  // Для запуска с главного экрана iPhone как отдельного приложения
  appleWebApp: {
    capable: true,
    title: BRAND.name,
    statusBarStyle: "default",
    // Картинки на время запуска: без них iPhone показывает пустой чёрный или белый экран
    startupImage: IPHONE_SPLASH,
  },
  // Не превращать числа в тексте в ссылки «позвонить»
  formatDetection: { telephone: false },
};

// Цвет строки состояния и поведение экрана на телефоне.
// colorScheme: "light" — приложение всегда светлое, поэтому тёмная тема телефона не делает фон чёрным.
export const viewport: Viewport = {
  themeColor: BRAND.themeColor,
  colorScheme: "light",
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    // Фон записан прямо в HTML (style), а не только в CSS: пока файл стилей грузится по медленной сети,
    // экран уже светлый фирменный, а не белый или чёрный
    <html lang="ru" className="h-full antialiased" style={{ backgroundColor: BRAND.themeColor }}>
      <body className="min-h-full" style={{ backgroundColor: BRAND.themeColor }}>
        {children}
        <ServiceWorkerRegister />
      </body>
    </html>
  );
}
