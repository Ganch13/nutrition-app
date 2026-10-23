
const meals = [
  { time: "08:00", name: "Завтрак", description: "Овсянка, яйца, фрукты", kcal: 620, done: true },
  { time: "13:00", name: "Обед", description: "Рис, курица, овощи", kcal: 750, done: false },
  { time: "17:30", name: "Перекус", description: "Йогурт и банан", kcal: 280, done: false },
  { time: "20:30", name: "Ужин", description: "Рыба и картофель", kcal: 650, done: false },
];

const navigation = [
  { icon: "⌂", label: "Главная", active: true },
  { icon: "◷", label: "Питание", active: false },
  { icon: "↗", label: "Тренировки", active: false },
  { icon: "◎", label: "Мой прогресс", active: false },
  { icon: "▦", label: "Расписание", active: false },
];

export default function Home() {
  const caloriesEaten = meals
    .filter((meal) => meal.done)
    .reduce((sum, meal) => sum + meal.kcal, 0);

  const calorieGoal = 2300;
  const caloriePercent = Math.min(
    Math.round((caloriesEaten / calorieGoal) * 100),
    100
  );

  return (
    <main className="min-h-screen bg-[#f5f6f8] text-slate-900">
      <div className="mx-auto flex min-h-screen max-w-[1440px]">
        <aside className="hidden w-64 shrink-0 flex-col border-r border-slate-200 bg-white p-6 md:flex">
          <div className="mb-10 flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-emerald-600 text-xl text-white">
              ✳
            </div>
            <div>
              <p className="font-bold tracking-tight">Balance</p>
              <p className="text-xs text-slate-500">Nutrition & Training</p>
            </div>
          </div>

          <p className="mb-3 text-xs font-semibold uppercase tracking-widest text-slate-400">
            Меню
          </p>

          <nav className="space-y-2">
            {navigation.map((item) => (
              <a
                key={item.label}
                href="#"
                className={`flex items-center gap-3 rounded-xl px-4 py-3 text-sm font-medium transition ${
                  item.active
                    ? "bg-emerald-50 text-emerald-700"
                    : "text-slate-600 hover:bg-slate-50"
                }`}
              >
                <span className="text-lg">{item.icon}</span>
                {item.label}
              </a>
            ))}
          </nav>

          <div className="mt-auto rounded-2xl bg-slate-50 p-4">
            <p className="text-sm font-semibold">Маленькие шаги</p>
            <p className="mt-2 text-xs leading-5 text-slate-500">
              Регулярность важнее идеального дня. Продолжай двигаться к своей цели.
            </p>
          </div>
        </aside>

        <section className="min-w-0 flex-1 p-4 sm:p-6 lg:p-10">
          <header className="mb-8 flex items-center justify-between gap-4">
            <div>
              <p className="text-sm text-slate-500">Четверг · Твой план на день</p>
              <h1 className="mt-1 text-2xl font-bold tracking-tight sm:text-3xl">
                Привет! 👋
              </h1>
              <p className="mt-2 text-sm text-slate-500">
                Двигайся к своим целям шаг за шагом.
              </p>
            </div>

            <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-emerald-100 font-bold text-emerald-800">
              Д
            </div>
          </header>

          <div className="mb-6 rounded-3xl bg-emerald-700 p-6 text-white sm:p-8">
            <p className="text-sm text-emerald-100">Твоя главная цель</p>
            <h2 className="mt-2 text-2xl font-bold sm:text-3xl">
              Сильнее каждый день
            </h2>
            <p className="mt-3 max-w-xl text-sm leading-6 text-emerald-100">
              Сбалансируй питание, восстановление и нагрузку. План должен
              помогать тебе в жизни, а не усложнять её.
            </p>

            <div className="mt-6 grid grid-cols-2 gap-3 sm:max-w-lg">
              <div className="rounded-2xl bg-white/10 p-4">
                <p className="text-xs text-emerald-100">Текущий вес</p>
                <p className="mt-1 text-2xl font-bold">100 кг</p>
              </div>
              <div className="rounded-2xl bg-white/10 p-4">
                <p className="text-xs text-emerald-100">Целевой вес</p>
                <p className="mt-1 text-2xl font-bold">96 кг</p>
              </div>
            </div>
          </div>

          <div className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            <article className="rounded-2xl border border-slate-200 bg-white p-5">
              <div className="flex items-center justify-between">
                <p className="text-sm text-slate-500">Калории сегодня</p>
                <span className="text-xl">◉</span>
              </div>
              <p className="mt-4 text-3xl font-bold">
                {caloriesEaten.toLocaleString("ru-RU")}
                <span className="ml-2 text-sm font-normal text-slate-400">
                  / {calorieGoal.toLocaleString("ru-RU")} ккал
                </span>
              </p>
              <div className="mt-4 h-2 overflow-hidden rounded-full bg-slate-100">
                <div
                  className="h-full rounded-full bg-emerald-500 transition-all"
                  style={{ width: `${caloriePercent}%` }}
                />
              </div>
              <p className="mt-2 text-xs text-slate-500">
                {caloriePercent}% от условной дневной цели
              </p>
            </article>

            <article className="rounded-2xl border border-slate-200 bg-white p-5">
              <div className="flex items-center justify-between">
                <p className="text-sm text-slate-500">Тренировка</p>
                <span className="text-xl">↗</span>
              </div>
              <p className="mt-4 text-xl font-bold">Баскетбол</p>
              <p className="mt-2 text-sm text-slate-500">
                Сегодня · 20:00–22:00
              </p>
              <div className="mt-4 inline-flex rounded-full bg-amber-50 px-3 py-1 text-xs font-medium text-amber-700">
                Запланирована
              </div>
            </article>

            <article className="rounded-2xl border border-slate-200 bg-white p-5 sm:col-span-2 xl:col-span-1">
              <div className="flex items-center justify-between">
                <p className="text-sm text-slate-500">Восстановление</p>
                <span className="text-xl">☾</span>
              </div>
              <p className="mt-4 text-xl font-bold">Сон и отдых</p>
              <p className="mt-2 text-sm leading-6 text-slate-500">
                Следи за сном и самочувствием, чтобы лучше переносить нагрузку.
              </p>
            </article>
          </div>

          <section className="rounded-2xl border border-slate-200 bg-white p-5 sm:p-6">
            <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-lg font-bold">Питание на сегодня</h2>
                <p className="mt-1 text-sm text-slate-500">
                  Пример дневного плана
                </p>
              </div>
              <span className="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-600">
                {meals.filter((meal) => meal.done).length} из {meals.length} отмечено
              </span>
            </div>

            <div className="divide-y divide-slate-100">
              {meals.map((meal) => (
                <div
                  key={meal.name}
                  className="flex items-center gap-3 py-4 first:pt-0 last:pb-0"
                >
                  <div
                    className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${
                      meal.done
                        ? "bg-emerald-50 text-emerald-700"
                        : "bg-slate-100 text-slate-500"
                    }`}
                  >
                    {meal.done ? "✓" : "○"}
                  </div>

                  <div className="min-w-0 flex-1">
                    <p className="font-medium">{meal.name}</p>
                    <p className="mt-1 truncate text-sm text-slate-500">
                      {meal.time} · {meal.description}
                    </p>
                  </div>

                  <p className="shrink-0 text-sm font-semibold">
                    {meal.kcal} <span className="font-normal text-slate-400">ккал</span>
                  </p>
                </div>
              ))}
            </div>
          </section>

          <p className="mt-6 text-center text-xs leading-5 text-slate-400">
            Демонстрационный экран. Вес, калории и расписание пока не загружаются
            из базы данных.
          </p>
        </section>
      </div>
    </main>
  );
}
