import { Loading } from "@/components/ui";

/**
 * Что видно, пока открывается раздел приложения (соглашение Next.js loading.js: обёртка Suspense вокруг страницы).
 * Меню (AppShell из layout.tsx) остаётся на месте, а вместо содержимого — индикатор, а не пустое место.
 * Особенно заметно при медленной сети или VPN, когда код раздела ещё не догрузился.
 */
export default function AppLoading() {
  return (
    <div className="flex min-h-[40vh] items-center justify-center">
      <Loading text="Открываем раздел..." />
    </div>
  );
}
