"use client";

import { useCallback, useMemo, useState } from "react";
import { Icon } from "@/components/icons";
import PeriodNav from "@/components/PeriodNav";
import EventDrawer, { type DrawerState } from "@/components/schedule/EventDrawer";
import { itemKey, segmentsByDay } from "@/components/schedule/layout";
import { WeekGrid, WeekStrip } from "@/components/schedule/WeekView";
import { Button, ErrorBanner, Loading, PageHeader } from "@/components/ui";
import { getScheduleWeek } from "@/lib/endpoints";
import { formatDayShort, mondayOf, shiftDate, todayInZone } from "@/lib/format";
import { useProfile } from "@/lib/profile-context";
import type { ScheduleItem } from "@/lib/types";
import { useAsyncData } from "@/lib/use-async-data";

/**
 * Страница «Расписание»: неделя в виде календаря, как в календаре iPhone.
 * На компьютере — семь колонок с понедельника по воскресенье, вся неделя на одном экране без прокрутки.
 * На телефоне — полоса с днями сверху и события выбранного дня под ней (решение пробное).
 * Формы при входе нет: нажатие на день открывает панель сбоку с подставленной датой (время вводится вручную),
 * нажатие на событие — его изменение или удаление. Кнопка «+» — запасной способ добавить событие.
 */
export default function SchedulePage() {
  const { profile } = useProfile();
  const userId = profile.id;
  const zone = profile.timezone;
  const today = todayInZone(zone);

  // Понедельник показываемой недели, например "2026-10-26"
  const [weekStart, setWeekStart] = useState(() => mondayOf(today));
  // День, выбранный в полосе на телефоне; по умолчанию сегодня, если он на этой неделе
  const [selectedDay, setSelectedDay] = useState(today);
  const [drawer, setDrawer] = useState<DrawerState | null>(null);

  const load = useCallback(() => getScheduleWeek(userId, weekStart), [userId, weekStart]);
  const { data: week, loading, error, reload } = useAsyncData(load);

  const days = useMemo(() => Array.from({ length: 7 }, (_, index) => shiftDate(weekStart, index)), [weekStart]);
  const segments = useMemo(() => (week ? segmentsByDay(week.items, days, zone) : null), [week, days, zone]);

  // Элементы, у которых есть пересечения: подсвечиваются красной рамкой
  const conflictKeys = useMemo(() => {
    const keys = new Set<string>();
    for (const conflict of week?.conflicts ?? []) {
      keys.add(itemKey(conflict.first.kind, conflict.first.id));
      keys.add(itemKey(conflict.second.kind, conflict.second.id));
    }
    return keys;
  }, [week]);

  // Выбранный день всегда внутри показываемой недели
  const stripDay = days.includes(selectedDay) ? selectedDay : days[0];

  /** Переходит на неделю со смещением в днях и выбирает в ней тот же день недели. */
  function moveWeek(offset: number) {
    setWeekStart(shiftDate(weekStart, offset));
    setSelectedDay(shiftDate(stripDay, offset));
  }

  /** После сохранения: показываем неделю, где оказалось событие, и обновляем её. */
  const handleSaved = useCallback(
    (date: string) => {
      setDrawer(null);
      setSelectedDay(date);
      const target = mondayOf(date);
      if (target === weekStart) reload();
      else setWeekStart(target);
    },
    [weekStart, reload],
  );
  const closeDrawer = useCallback(() => setDrawer(null), []);

  const openCreate = (day: string) => setDrawer({ mode: "create", date: day });
  const openItem = (item: ScheduleItem) => setDrawer({ mode: "edit", item });
  const drawerDay = drawer?.mode === "create" ? drawer.date : null;

  return (
    <>
      <PageHeader
        title="Расписание"
        subtitle="Нажмите на день, чтобы добавить событие, или на событие, чтобы его изменить"
        action={
          <div className="flex flex-wrap items-center gap-2">
            <PeriodNav
              title={`${formatDayShort(weekStart)} – ${formatDayShort(shiftDate(weekStart, 6))}`}
              prevLabel="Предыдущая неделя"
              nextLabel="Следующая неделя"
              todayLabel="Эта неделя"
              onPrev={() => moveWeek(-7)}
              onNext={() => moveWeek(7)}
              onToday={() => {
                setWeekStart(mondayOf(today));
                setSelectedDay(today);
              }}
              todayDisabled={weekStart === mondayOf(today)}
            />
            <Button className="hidden md:inline-flex" onClick={() => openCreate(stripDay)}>
              <Icon name="plus" size={18} />
              Добавить
            </Button>
          </div>
        }
      />

      {error && <ErrorBanner message={error} onRetry={reload} />}
      {week && week.conflicts.length > 0 && (
        <div className="mb-4 rounded-xl bg-amber-50 px-4 py-3 text-sm text-amber-800">
          На этой неделе есть пересечения по времени: {week.conflicts.length}. Они обведены красным. Измените время или
          отметьте у блока «Внутри этого блока могут быть другие события».
        </div>
      )}

      <div className="lg:flex lg:items-start lg:gap-4">
        <div className="min-w-0 flex-1">
          {loading && segments === null && <Loading />}
          {segments && (
            <>
              <div className="hidden md:block">
                <WeekGrid
                  days={days}
                  today={today}
                  segments={segments}
                  selected={drawerDay}
                  conflictKeys={conflictKeys}
                  onDayClick={openCreate}
                  onItemClick={openItem}
                />
              </div>
              <div className="md:hidden">
                <WeekStrip
                  days={days}
                  today={today}
                  selected={stripDay}
                  segments={segments}
                  conflictKeys={conflictKeys}
                  onSelect={setSelectedDay}
                  onItemClick={openItem}
                />
              </div>
            </>
          )}
        </div>

        {drawer && <EventDrawer state={drawer} userId={userId} zone={zone} onSaved={handleSaved} onClose={closeDrawer} />}
      </div>

      {/* «+» на телефоне: добавить событие в выбранный день. Над нижней панелью навигации */}
      {!drawer && (
        <button
          type="button"
          onClick={() => openCreate(stripDay)}
          aria-label={`Добавить событие: ${formatDayShort(stripDay)}`}
          className="fixed right-4 z-30 flex size-14 items-center justify-center rounded-full bg-brand-700 text-white shadow-lg active:bg-brand-800 md:hidden"
          style={{ bottom: "calc(4.75rem + env(safe-area-inset-bottom))" }}
        >
          <Icon name="plus" size={26} strokeWidth={2.5} />
        </button>
      )}
    </>
  );
}
