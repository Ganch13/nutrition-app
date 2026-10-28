"use client";

import { Button, IconButton } from "@/components/ui";

/**
 * Переключатель периода: стрелки назад и вперёд вокруг названия периода и кнопка «вернуться к текущему».
 * Заменяет кнопки вида «← Неделя» и «Неделя →» на всех страницах.
 * Пример для недели: title="26 окт. – 1 нояб.", prevLabel="Предыдущая неделя", nextLabel="Следующая неделя",
 * todayLabel="Эта неделя".
 *   title — название периода (необязательно);
 *   onToday — вернуться к текущему периоду; todayDisabled — мы уже на нём.
 */
export default function PeriodNav({
  title,
  prevLabel,
  nextLabel,
  todayLabel,
  onPrev,
  onNext,
  onToday,
  todayDisabled,
}: {
  title?: string;
  prevLabel: string;
  nextLabel: string;
  todayLabel: string;
  onPrev: () => void;
  onNext: () => void;
  onToday: () => void;
  todayDisabled?: boolean;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <div className="inline-flex items-center rounded-xl border border-slate-300 bg-white">
        <IconButton icon="chevron-left" label={prevLabel} onClick={onPrev} />
        {title && <span className="num min-w-32 px-1 text-center text-sm font-medium text-slate-800">{title}</span>}
        <IconButton icon="chevron-right" label={nextLabel} onClick={onNext} />
      </div>
      <Button variant="secondary" onClick={onToday} disabled={todayDisabled}>
        {todayLabel}
      </Button>
    </div>
  );
}
