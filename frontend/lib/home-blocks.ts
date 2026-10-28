import { useState } from "react";
import { getErrorText } from "./api";
import { patchProfile } from "./endpoints";
import { useProfile } from "./profile-context";
import type { HomeBlock } from "./types";

/** Названия блоков главной для подписей «Блок «Деньги» скрыт». */
export const HOME_BLOCK_LABELS: Record<HomeBlock, string> = {
  money: "Деньги",
  finance_goal: "Финансовая цель",
  nutrition: "Питание сегодня",
  training: "Ближайшая тренировка",
  weight: "Вес и цель по весу",
};

/**
 * Скрытые блоки главной страницы и функции, которые их меняют.
 * Список хранится в профиле на сервере, поэтому блок, скрытый на телефоне, скрыт и на компьютере.
 * Пока запрос идёт, интерфейс уже показывает новое состояние; при ошибке оно откатывается.
 * Пример: const { isHidden, setHidden } = useHomeBlocks(); setHidden("weight", true).
 */
export function useHomeBlocks() {
  const { profile, refreshProfile } = useProfile();
  // Список, отправленный на сервер, и профиль, от которого он посчитан. Как только профиль
  // перезагрузится (придёт новый массив), берётся уже сохранённый на сервере список
  const [pending, setPending] = useState<{ base: HomeBlock[]; value: HomeBlock[] } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const hidden =
    pending !== null && pending.base === profile.home_hidden_blocks ? pending.value : profile.home_hidden_blocks;

  async function setHidden(block: HomeBlock, value: boolean) {
    const next = value ? [...new Set([...hidden, block])] : hidden.filter((item) => item !== block);
    setPending({ base: profile.home_hidden_blocks, value: next });
    setError(null);
    try {
      await patchProfile(profile.id, { home_hidden_blocks: next });
      refreshProfile();
    } catch (err) {
      setPending(null);
      setError(getErrorText(err));
    }
  }

  return {
    hidden,
    isHidden: (block: HomeBlock) => hidden.includes(block),
    setHidden,
    error,
  };
}
