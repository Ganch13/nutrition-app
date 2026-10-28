"use client";

import { HOME_BLOCK_LABELS, useHomeBlocks } from "@/lib/home-blocks";
import type { HomeBlock } from "@/lib/types";
import { Button, ErrorBanner } from "./ui";

/**
 * Плашка «Блок скрыт на главной» с кнопкой «Вернуть на главную». Ставится в раздел, к которому относится
 * блок: деньги — в «Финансы», финансовая цель — во вкладку «Цели», питание — в «Питание»,
 * тренировка — в «Тренировки», вес — в «Прогресс». Пока блок не скрыт, ничего не показывает.
 */
export default function HomeBlockReturn({ block }: { block: HomeBlock }) {
  const { isHidden, setHidden, error } = useHomeBlocks();
  if (!isHidden(block) && !error) return null;

  return (
    <div className="mb-6 space-y-3">
      {isHidden(block) && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-slate-100 px-4 py-3 text-sm text-slate-700">
          <span>Блок «{HOME_BLOCK_LABELS[block]}» скрыт на главной странице.</span>
          <Button size="sm" variant="secondary" onClick={() => void setHidden(block, false)}>
            Вернуть на главную
          </Button>
        </div>
      )}
      {error && <ErrorBanner message={error} />}
    </div>
  );
}
