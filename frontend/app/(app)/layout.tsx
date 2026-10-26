import type { ReactNode } from "react";
import AppShell from "@/components/AppShell";

/** Общая рама для всех страниц внутри группы (app): меню и профиль. */
export default function AppLayout({ children }: { children: ReactNode }) {
  return <AppShell>{children}</AppShell>;
}