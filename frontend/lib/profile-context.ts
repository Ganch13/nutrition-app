import { createContext, useContext } from "react";
import type { UserProfile } from "./types";

type ProfileContextValue = {
  // Профиль текущего пользователя, например { id: 1, name: "Имя", timezone: "UTC", ... }
  profile: UserProfile;
  // Перезагружает профиль после его изменения
  refreshProfile: () => void;
};

/** Общий контейнер профиля: его заполняет AppShell, читают все страницы. */
export const ProfileContext = createContext<ProfileContextValue | null>(null);

/** Возвращает профиль и функцию его обновления. Работает только внутри AppShell. */
export function useProfile(): ProfileContextValue {
  const value = useContext(ProfileContext);

  if (value === null) {
    throw new Error("useProfile нужно вызывать внутри AppShell");
  }

  return value;
}