// Типы данных, которые возвращает backend.
//
// Каждый тип описывает JSON-ответ определённого эндпоинта и повторяет схему
// из backend/schemas.py. Если схема на backend изменится, нужно обновить
// и тип здесь.
//
// Важно: числа с дробной частью (вес, проценты, темп) backend отдаёт
// СТРОКАМИ, например "100.00". Поэтому они объявлены как string, а для
// вывода и вычислений их нужно преобразовывать: Number("100.00") → 100.

/** Допустимые значения пола (совпадают с проверкой на backend). */
export type Sex = "male" | "female" | "unspecified";

/** Допустимые типы целей (совпадают с ограничением таблицы goals). */
export type GoalType =
  | "fat_loss"
  | "muscle_gain"
  | "weight_maintenance"
  | "performance"
  | "general_health";

/** Допустимые статусы цели. */
export type GoalStatus = "active" | "completed" | "paused" | "cancelled";

/**
 * Профиль пользователя. Ответ GET /users/me (схема UserResponse).
 *
 * Пример данных:
 *   { id: 1, name: "Имя", age: 34, birth_date: "1992-05-17", sex: "male",
 *     height_cm: 180, occupation: null, timezone: "Europe/Berlin",
 *     created_at: "2026-10-21T14:36:36.837089Z" }
 */
export type UserProfile = {
  id: number;
  name: string;
  // Возраст считает backend по birth_date; null, если даты рождения нет
  age: number | null;
  birth_date: string | null;
  sex: Sex | null;
  height_cm: number;
  occupation: string | null;
  // Название часового пояса IANA, например "Europe/Berlin" или "UTC"
  timezone: string;
  // Блоки главной страницы, которые пользователь скрыл, например ["money", "weight"]
  home_hidden_blocks: HomeBlock[];
  created_at: string;
};

/** Блоки главной страницы: деньги, финансовая цель, питание сегодня, ближайшая тренировка, вес. */
export type HomeBlock = "money" | "finance_goal" | "nutrition" | "training" | "weight";

/**
 * Запись веса. Элемент ответа GET /users/{user_id}/weight-records
 * (схема WeightRecordResponse).
 *
 * Пример данных:
 *   { id: 3, user_id: 1, measurement_date: "2026-10-23", weight_kg: "100.00",
 *     body_fat_percent: null, notes: null,
 *     created_at: "2026-10-23T13:42:59.904498Z" }
 */
export type WeightRecord = {
  id: number;
  user_id: number;
  // Дата измерения в формате ГГГГ-ММ-ДД
  measurement_date: string;
  // Строка с двумя знаками после точки: "100.00"
  weight_kg: string;
  body_fat_percent: string | null;
  notes: string | null;
  created_at: string;
};

/**
 * Цель пользователя. Элемент ответа GET /users/{user_id}/goals
 * (схема GoalResponse).
 *
 * Пример данных:
 *   { id: 3, user_id: 1, goal_type: "fat_loss", priority: 1,
 *     target_weight_kg: "90.00", target_body_fat_percent: null,
 *     desired_rate_kg_per_week: "0.50", start_date: "2026-10-23",
 *     target_date: null, status: "active", notes: null,
 *     created_at: "2026-10-23T13:43:41.551156Z" }
 */
export type UserGoal = {
  id: number;
  user_id: number;
  goal_type: GoalType;
  // Приоритет от 1 (самый высокий) до 5
  priority: number;
  // У цели может не быть целевого веса, например у "muscle_gain"
  target_weight_kg: string | null;
  target_body_fat_percent: string | null;
  desired_rate_kg_per_week: string | null;
  start_date: string;
  target_date: string | null;
  status: GoalStatus;
  notes: string | null;
  created_at: string;
};


/** Ответ POST /auth/login. */
export type LoginResponse = {
  access_token: string;
  token_type: string;
};

export type MealType = "breakfast" | "lunch" | "dinner" | "snack" | "other";

/**
 * Приём пищи. Элемент ответа GET /users/{id}/nutrition/daily-entries.
 * Пример: { id: 1, eaten_at: "2026-10-23T10:00:00Z", meal_type: "lunch",
 *           description: "Рис и курица", calories: "650.00", protein_g: "45.00",
 *           fat_g: "12.00", carbs_g: "80.00", notes: null, ... }
 */
export type MealEntry = {
  id: number;
  user_id: number;
  eaten_at: string;
  meal_type: MealType;
  description: string;
  calories: string;
  protein_g: string;
  fat_g: string;
  carbs_g: string;
  notes: string | null;
  // Продукт справочника и масса, если запись создана из справочника
  food_id: number | null;
  amount_g: string | null;
  created_at: string;
};

/** Итоги дня. Ответ GET /users/{id}/nutrition/daily-summary. */
export type DailyNutritionSummary = {
  date: string;
  user_id: number;
  entries_count: number;
  calories: string;
  protein_g: string;
  fat_g: string;
  carbs_g: string;
};

export type TrainingSessionStatus = "planned" | "completed" | "skipped" | "cancelled";
export type LoadType = "strength" | "cardio" | "mixed" | "other";
export type Intensity = "low" | "moderate" | "high";

/** Тренировочная сессия. Элемент ответа GET /users/{id}/training-sessions. */
export type TrainingSession = {
  id: number;
  user_id: number;
  schedule_event_id: number | null;
  name: string;
  start_at: string;
  end_at: string;
  status: TrainingSessionStatus;
  notes: string | null;
  created_at: string;
};

/** Блок тренировки внутри сессии. */
export type Workout = {
  id: number;
  training_session_id: number;
  name: string;
  load_type: LoadType;
  planned_intensity: Intensity;
  actual_intensity: Intensity | null;
  start_at: string;
  end_at: string;
  notes: string | null;
  // Номер суперсета (блоки одной группы идут вперемежку) или null
  superset_group: number | null;
  // Когда нажали «Выполнил упражнение»; null — ещё не выполнено
  completed_at: string | null;
  created_at: string;
};

// ---- Расписание (шаг 64) ----

export type ScheduleEventType = "sleep" | "work" | "meal" | "workout" | "personal" | "other";

/** Событие расписания. Элемент ответа GET /users/{id}/schedule-events. */
export type ScheduleEvent = {
  id: number;
  user_id: number;
  event_type: ScheduleEventType;
  title: string;
  start_at: string;
  end_at: string;
  location: string | null;
  notes: string | null;
  // Не null у событий повторяющейся серии
  series_id: string | null;
  // Блок, внутри которого могут быть другие события («Работа» с обедом внутри)
  is_container: boolean;
  created_at: string;
};

/**
 * Элемент недельного вида: событие или тренировка.
 * Пример: { kind: "event", id: 5, title: "Работа", category: "work",
 *           start_at: "2026-10-26T06:00:00Z", end_at: "2026-10-26T15:00:00Z",
 *           location: "Офис", status: null, series_id: "3f2b...", is_container: true, parent_id: null }
 */
export type ScheduleItem = {
  kind: "event" | "training";
  id: number;
  title: string;
  category: string;
  start_at: string;
  end_at: string;
  location: string | null;
  status: string | null;
  series_id: string | null;
  // Только у событий: блок, внутри которого могут быть другие события
  is_container: boolean;
  // id события-блока, внутрь которого целиком попадает этот элемент; иначе null
  parent_id: number | null;
};

/** Пара элементов, пересекающихся по времени. */
export type ScheduleConflict = {
  first: { kind: "event" | "training"; id: number; title: string };
  second: { kind: "event" | "training"; id: number; title: string };
};

/** Ответ GET /users/{id}/schedule/week?start=2026-10-26. */
export type ScheduleWeek = {
  start: string;
  end: string;
  timezone: string;
  items: ScheduleItem[];
  conflicts: ScheduleConflict[];
};

export type ScheduleEventInput = {
  event_type: ScheduleEventType;
  title: string;
  start_at: string;
  end_at: string;
  location: string | null;
  notes: string | null;
  is_container: boolean;
};

export type ScheduleSeriesInput = {
  event_type: ScheduleEventType;
  title: string;
  // 0 — понедельник … 6 — воскресенье
  weekdays: number[];
  // "09:00"; если окончание не позже начала, событие заканчивается на следующий день
  start_time: string;
  end_time: string;
  from_date: string;
  weeks: number;
  location: string | null;
  notes: string | null;
  is_container: boolean;
};

// ---- Данные, которые интерфейс отправляет на backend ----

export type RegisterInput = {
  name: string;
  email: string;
  password: string;
  height_cm: number;
  birth_date: string | null;
  sex: Sex | null;
  timezone: string;
};

export type ProfileUpdateInput = {
  name: string;
  birth_date: string | null;
  sex: Sex | null;
  height_cm: number;
  occupation: string | null;
  timezone: string;
};

/** Частичное изменение профиля, например { home_hidden_blocks: ["weight"] }. */
export type ProfilePatch = Partial<ProfileUpdateInput> & { home_hidden_blocks?: HomeBlock[] };

export type WeightRecordInput = {
  measurement_date: string;
  weight_kg: number;
  body_fat_percent: number | null;
  notes: string | null;
};

export type GoalInput = {
  goal_type: GoalType;
  priority: number;
  target_weight_kg: number | null;
  target_body_fat_percent: number | null;
  desired_rate_kg_per_week: number | null;
  start_date: string;
  target_date: string | null;
  notes: string | null;
};

export type MealEntryInput = {
  eaten_at: string;
  meal_type: MealType;
  description: string;
  calories: number;
  protein_g: number;
  fat_g: number;
  carbs_g: number;
  notes: string | null;
};

export type TrainingSessionInput = {
  name: string;
  start_at: string;
  end_at: string;
  notes: string | null;
};

export type WorkoutInput = {
  name: string;
  load_type: LoadType;
  planned_intensity: Intensity;
  start_at: string;
  end_at: string;
  notes: string | null;
  // id блока, с которым объединить в суперсет (тогда время может совпадать)
  superset_with_workout_id?: number | null;
};


export type LedgerKind = "personal" | "household";
export type FinanceKind = "expense" | "income";

/** Книга и права пользователя. Элемент ответа GET /finance/ledgers. */
export type Ledger = {
  id: number;
  kind: LedgerKind;
  household_id: number | null;
  household_name: string | null;
  currency: string;
  can_manage: boolean;
  // Как считается бюджетный период: календарный месяц или «от дохода до дохода»
  cycle_mode: CycleMode;
};

/** Домохозяйство пользователя с его ролью. Элемент ответа GET /households. */
export type UserHousehold = {
  id: number;
  name: string;
  created_at: string;
  role: "owner" | "admin" | "member";
};
/** Роль в домохозяйстве. */
export type HouseholdRole = "owner" | "admin" | "member";

/** Участник домохозяйства. Элемент ответа GET /households/{id}/members.
 *  Пример: { household_id: 1, user_id: 2, name: "Леся", role: "member", joined_at: "2026-10-26T10:05:00Z" } */
export type HouseholdMember = {
  household_id: number;
  user_id: number;
  name: string;
  role: HouseholdRole;
  joined_at: string;
};

/** Код приглашения. Элемент ответа GET /households/{id}/invites.
 *  Пример: { id: 1, household_id: 1, code: "K7M29QXP", created_at: "...", expires_at: "..." } */
export type HouseholdInvite = {
  id: number;
  household_id: number;
  code: string;
  created_at: string;
  expires_at: string;
};

export type FinanceCategory = {
  id: number;
  ledger_id: number;
  name: string;
  kind: FinanceKind;
};

/** Операция. Суммы приходят строками, например "120.50". */
export type FinanceTransaction = {
  id: number;
  ledger_id: number;
  category_id: number;
  category_name: string;
  kind: FinanceKind;
  amount: string;
  occurred_on: string;
  description: string | null;
  // null, если автор удалил свой аккаунт (тогда created_by_name = "Удалённый пользователь")
  created_by_user_id: number | null;
  created_by_name: string;
  created_at: string;
  // Цель, к которой отнесён расход, например 3 и "Отпуск"; null — без цели
  goal_id: number | null;
  goal_name: string | null;
  // Сводка, строкой которой является операция, и её период («Сводка 19–25 окт.»); null — обычная операция
  summary_id: number | null;
  summary_start: string | null;
  summary_end: string | null;
};

/** Строка сводки: категория расходов, сумма и (необязательно) цель. Пример: { category_id: 3, amount: 8000 }. */
export type ExpenseSummaryLineInput = {
  category_id: number;
  amount: number;
  goal_id?: number | null;
};

/** Тело сверки POST /finance/ledgers/{id}/summaries/check. */
export type ExpenseSummaryCheckInput = {
  period_start: string;
  period_end: string;
  lines: ExpenseSummaryLineInput[];
};

/**
 * Тело сохранения POST /finance/ledgers/{id}/summaries. mode — ответ из окна сверки:
 * "add" — дополнение; "replace" + replace_ids — повтор, удалить показанные расходы. Без пересечений mode не нужен.
 */
export type ExpenseSummaryCreateInput = ExpenseSummaryCheckInput & {
  mode?: "add" | "replace";
  replace_ids?: number[];
  note?: string | null;
};

/** Уже записанный расход за период в категории сводки (возможный повтор). */
export type ExpenseSummaryMatch = {
  transaction_id: number;
  occurred_on: string;
  category_id: number;
  category_name: string;
  amount: string;
  description: string | null;
  summary_id: number | null;
};

/** Итог сверки: пустой matches — пересечений нет, можно сохранять. */
export type ExpenseSummaryCheck = {
  period_start: string;
  period_end: string;
  summary_total: string;
  existing_total: string;
  existing_count: number;
  matches: ExpenseSummaryMatch[];
};

/** Сохранённая сводка со строками. replaced_count — сколько расходов удалено при замене. */
export type ExpenseSummary = {
  id: number;
  ledger_id: number;
  period_start: string;
  period_end: string;
  note: string | null;
  total: string;
  created_by_user_id: number | null;
  created_by_name: string;
  created_at: string;
  lines: FinanceTransaction[];
  replaced_count: number;
};

export type CategorySummary = {
  category_id: number;
  name: string;
  kind: FinanceKind;
  total: string;
  budget_limit: string | null;
};

/** Сводка за месяц. Ответ GET /finance/ledgers/{id}/summary. */
export type FinanceSummary = {
  ledger_id: number;
  month: string;
  currency: string;
  income: string;
  expense: string;
  balance: string;
  categories: CategorySummary[];
};

export type LedgerCreateInput = {
  kind: LedgerKind;
  household_id: number | null;
  currency: string;
};

export type FinanceTransactionInput = {
  category_id: number;
  amount: number;
  occurred_on: string;
  description: string | null;
  // Расход на цель этой же книги: сервер сам добавит запись в историю цели
  goal_id?: number | null;
};

/** Тело PATCH операции: только меняемые поля. goal_id: null — отвязать от цели. */
export type FinanceTransactionChanges = Partial<FinanceTransactionInput>;

// ---- Справочник продуктов (шаг 65) ----

export type FoodCategory =
  | "meat"
  | "fish"
  | "eggs"
  | "dairy"
  | "grains"
  | "bakery"
  | "vegetables"
  | "fruits"
  | "legumes"
  | "nuts"
  | "fats"
  | "sweets"
  | "drinks"
  | "sauces"
  | "supplements"
  | "other";

/**
 * Продукт справочника. Значения на 100 г приходят строками.
 * Пример: { id: 14, name: "Яйцо куриное (сырое)", category: "eggs",
 *           calories_per_100g: "143.00", protein_per_100g: "12.60", fat_per_100g: "9.50",
 *           carbs_per_100g: "0.70", serving_name: "1 яйцо", serving_grams: "55.00",
 *           household_id: null, source: "builtin", can_edit: false }
 */
export type Food = {
  id: number;
  name: string;
  category: FoodCategory;
  calories_per_100g: string;
  protein_per_100g: string;
  fat_per_100g: string;
  carbs_per_100g: string;
  serving_name: string | null;
  serving_grams: string | null;
  household_id: number | null;
  source: "builtin" | "personal" | "household";
  can_edit: boolean;
};

export type FoodList = { items: Food[]; total: number };

export type FoodInput = {
  name: string;
  category: FoodCategory;
  calories_per_100g: number;
  protein_per_100g: number;
  fat_per_100g: number;
  carbs_per_100g: number;
  serving_name: string | null;
  serving_grams: number | null;
  household_id: number | null;
};

/** Ответ GET /foods/{id}/nutrition: пищевая ценность заданной массы. */
export type FoodNutrition = {
  food_id: number;
  amount_g: string;
  calories: string;
  protein_g: string;
  fat_g: string;
  carbs_g: string;
};

export type MealFromFoodInput = {
  food_id: number;
  // Нужно указать ровно одно из двух: граммы или число порций
  amount_g?: number;
  servings?: number;
  eaten_at: string;
  meal_type: MealType;
  notes: string | null;
};

// ---- Нормы питания и прогресс целей (шаг 66) ----

export type ActivityLevel = "sedentary" | "light" | "moderate" | "active";

/** Настройки расчёта норм. Ответ GET /users/{id}/nutrition/settings. */
export type NutritionSettings = {
  activity_level: ActivityLevel;
  meals_per_day: number;
  // Строка вида "2.0" или null (считать автоматически)
  protein_g_per_kg: string | null;
  calorie_override: number | null;
};

export type NutritionSettingsInput = {
  activity_level: ActivityLevel;
  meals_per_day: number;
  protein_g_per_kg: number | null;
  calorie_override: number | null;
};

/**
 * Норма питания на день. Ответ GET /users/{id}/nutrition/targets?target_date=…
 * Если ready = false, числовые поля пустые, а в missing перечислено, чего не хватает
 * ("weight", "birth_date").
 */
export type NutritionTarget = {
  date: string;
  ready: boolean;
  missing: string[];
  warnings: string[];
  weight_kg: string | null;
  age: number | null;
  sex_used: string | null;
  bmr: number | null;
  base_kcal: number | null;
  exercise_kcal: number | null;
  tdee: number | null;
  goal_type: GoalType | null;
  goal_adjustment_kcal: number | null;
  calories: number | null;
  protein_g: number | null;
  fat_g: number | null;
  carbs_g: number | null;
  fiber_g: number | null;
  water_ml: number | null;
  is_training_day: boolean;
  training_minutes: number;
  explanation: string[];
};

export type GoalProgressStatus =
  | "no_data"
  | "reached"
  | "on_track"
  | "faster"
  | "slower"
  | "stalled"
  | "wrong_direction";

/** Прогресс цели. Элемент ответа GET /users/{id}/goals/progress. */
export type GoalProgress = {
  goal_id: number;
  goal_type: GoalType;
  target_weight_kg: string | null;
  start_weight_kg: string | null;
  current_weight_kg: string | null;
  change_kg: string | null;
  remaining_kg: string | null;
  progress_percent: number | null;
  desired_rate_kg_per_week: string | null;
  actual_rate_kg_per_week: string | null;
  status: GoalProgressStatus;
  eta_date: string | null;
  target_date: string | null;
  message: string;
};


// ---------- Рецепты и план питания (шаг 67) ----------
// Числа с дробной частью backend присылает строками ("331.00"), чтобы не терять точность.

/** Тип приёма пищи в плане (в дневнике питания есть ещё "other"). */
export type PlanMealType = "breakfast" | "lunch" | "dinner" | "snack";

/** Где будет приём пищи: дома, на работе или вне дома. */
export type MealLocation = "home" | "work" | "away";

export type PlannedMealStatus = "planned" | "eaten" | "skipped";

export type RecipeSource = "builtin" | "personal" | "household";

/** Ингредиент рецепта с вычисленной пищевой ценностью. */
export type RecipeIngredient = {
  food_id: number;
  name: string;
  amount_g: string;
  serving_name: string | null;
  serving_grams: string | null;
  calories: string;
  protein_g: string;
  fat_g: string;
  carbs_g: string;
};

/** Рецепт на одну порцию. Ответ GET /recipes. */
export type Recipe = {
  id: number;
  name: string;
  meal_types: PlanMealType[];
  portable: boolean;
  prep_minutes: number;
  keeps_days: number;
  instructions: string | null;
  household_id: number | null;
  source: RecipeSource;
  can_edit: boolean;
  calories: string;
  protein_g: string;
  fat_g: string;
  carbs_g: string;
  ingredients: RecipeIngredient[];
};

export type RecipeList = { items: Recipe[]; total: number };

/** Ингредиент в запросе: продукт и масса на одну порцию. */
export type RecipeIngredientInput = { food_id: number; amount_g: number };

/** Тело POST /recipes. */
export type RecipeInput = {
  name: string;
  meal_types: PlanMealType[];
  portable: boolean;
  prep_minutes: number;
  keeps_days: number;
  instructions: string | null;
  household_id: number | null;
  ingredients: RecipeIngredientInput[];
};

export type PlannedMealItem = {
  food_id: number | null;
  name: string;
  amount_g: string;
  calories: string;
  protein_g: string;
  fat_g: string;
  carbs_g: string;
};

/** Приём пищи в плане питания. */
export type PlannedMeal = {
  id: number;
  plan_date: string;
  planned_at: string;
  meal_type: PlanMealType;
  location: MealLocation;
  status: PlannedMealStatus;
  recipe_id: number | null;
  title: string;
  portion_scale: string;
  calories: string;
  protein_g: string;
  fat_g: string;
  carbs_g: string;
  notes: string | null;
  meal_entry_id: number | null;
  items: PlannedMealItem[];
};

/** Тело POST /users/{id}/meal-plan/meals: либо recipe_id, либо items. */
export type PlannedMealInput = {
  planned_at: string;
  meal_type: PlanMealType;
  location: MealLocation;
  recipe_id?: number;
  portion_scale?: number;
  items?: { food_id: number; amount_g: number }[];
  title?: string;
};

/** Тело PATCH /users/{id}/meal-plan/meals/{mealId}. Передавайте только изменённые поля. */
export type PlannedMealChanges = {
  planned_at?: string;
  meal_type?: PlanMealType;
  location?: MealLocation;
  recipe_id?: number;
  portion_scale?: number;
};

export type DayTargetBrief = {
  ready: boolean;
  calories: number | null;
  protein_g: number | null;
  fat_g: number | null;
  carbs_g: number | null;
  is_training_day: boolean;
  training_minutes: number;
};

export type MealPlanDay = {
  date: string;
  target: DayTargetBrief;
  planned_calories: string;
  planned_protein_g: string;
  planned_fat_g: string;
  planned_carbs_g: string;
  meals: PlannedMeal[];
  warnings: string[];
};

/** Ответ GET /users/{id}/meal-plan?start=… — семь дней плана. */
export type MealPlanWeek = {
  start: string;
  end: string;
  timezone: string;
  target_ready: boolean;
  warnings: string[];
  days: MealPlanDay[];
};

export type MealPlanGenerateInput = {
  start: string;
  days: number;
  overwrite: boolean;
  batch_days: number;
};

export type MealPlanGenerateResult = {
  created_meals: number;
  replaced_meals: number;
  skipped_days: string[];
  warnings: string[];
};

// ---------- Список закупок и план готовки (шаг 68) ----------

export type ShoppingItem = {
  key: string;
  food_id: number | null;
  name: string;
  category: FoodCategory;
  amount_g: string;
  serving_name: string | null;
  serving_grams: string | null;
  servings: string | null;
  used_in: string[];
  checked: boolean;
  // Только в семейном списке: кто это ест и кто отметил «куплено»
  members: string[];
  checked_by: string | null;
};

export type ShoppingList = {
  start: string;
  end: string;
  items: ShoppingItem[];
  checked_count: number;
  meals_count: number;
  // Только в семейном списке: чьи планы учтены
  members: string[];
};

export type CookingMealRef = {
  id: number;
  plan_date: string;
  meal_type: PlanMealType;
  planned_at: string;
  location: MealLocation;
  portion_scale: string;
  // Только в семейном плане готовки: для кого порция
  user_id: number | null;
  user_name: string | null;
};

export type CookingSession = {
  recipe_id: number;
  recipe_name: string;
  cook_date: string;
  cook_when: "evening_before" | "same_day";
  portions: string;
  estimated_minutes: number;
  keeps_days: number;
  instructions: string | null;
  meals: CookingMealRef[];
  ingredients: { name: string; amount_g: string }[];
};

export type CookingPlan = {
  start: string;
  end: string;
  sessions: CookingSession[];
  total_minutes: number;
};

// ---------- Семейное планирование (шаг 69) ----------

export type FamilyPlanningMember = {
  user_id: number;
  name: string;
  role: HouseholdRole;
  plans_together: boolean;
  is_me: boolean;
};

export type FamilyPlanningState = {
  household_id: number;
  members: FamilyPlanningMember[];
  together_count: number;
};

/** Приём пищи участника в семейном виде: без калорий и БЖУ. */
export type FamilyPlannedMeal = {
  id: number;
  planned_at: string;
  meal_type: PlanMealType;
  location: MealLocation;
  status: PlannedMealStatus;
  title: string;
  recipe_id: number | null;
  portion_scale: string;
  // Тот же рецепт в тот же день и приём пищи есть ещё у кого-то из семьи
  shared: boolean;
};

export type FamilyPlanMemberDay = {
  user_id: number;
  name: string;
  meals: FamilyPlannedMeal[];
};

export type FamilyPlanDay = {
  date: string;
  members: FamilyPlanMemberDay[];
};

export type FamilyPlanWeek = {
  household_id: number;
  start: string;
  end: string;
  members: FamilyPlanningMember[];
  days: FamilyPlanDay[];
};

export type FamilyPlanGenerateInput = MealPlanGenerateInput & {
  shared_meal_types: PlanMealType[];
};

export type FamilyPlanGenerateResult = {
  members: {
    user_id: number;
    name: string;
    created_meals: number;
    replaced_meals: number;
    skipped_days: string[];
  }[];
  shared_meals: number;
  warnings: string[];
};

// ---------- Фото прогресса (шаг 70) ----------

export type PhotoAngle = "front" | "side" | "back" | "other";

export type ProgressPhoto = {
  id: number;
  // Дата съёмки ГГГГ-ММ-ДД
  taken_on: string;
  angle: PhotoAngle;
  note: string | null;
  content_type: string;
  size_bytes: number;
  created_at: string;
  // Путь к файлу на сервере; скачивается запросом с токеном
  url: string;
};

export type ProgressPhotoChanges = {
  taken_on?: string;
  angle?: PhotoAngle;
  note?: string | null;
};


// ---- Релиз 1.1: повторяющиеся платежи, бюджетные периоды, нагрузка, цели, удаление аккаунта ----

/** Как часто повторяется платёж или доход. semimonthly — два раза в месяц в два заданных дня. */
export type RuleFrequency = "weekly" | "biweekly" | "semimonthly" | "monthly" | "yearly";
/** Бюджетный период: календарный месяц или «от дохода до дохода». */
export type CycleMode = "calendar" | "income";
/** Состояние одного повторения: ждёт / оплачено (получено) / пропущено. */
export type OccurrenceStatus = "pending" | "posted" | "skipped";
/** Насколько серьёзен совет. */
export type Severity = "info" | "warning" | "danger";

/** Повторяющийся доход или обязательный платёж. Суммы приходят строками: "35000.00". */
export type RecurringRule = {
  id: number;
  ledger_id: number;
  kind: FinanceKind;
  category_id: number;
  category_name: string;
  name: string;
  amount: string;
  frequency: RuleFrequency;
  start_on: string;
  day_of_month: number | null;
  // Второй день месяца у «два раза в месяц», например 25
  second_day_of_month: number | null;
  // Только у платежей; у доходов всегда null
  end_on: string | null;
  // Только у платежей: списывается сам. Доход всегда подтверждается
  auto_post: boolean;
  // Основной или дополнительный. Границы бюджетного периода задают основные доходы
  is_primary: boolean;
  is_active: boolean;
  // Сколько правило приносит или стоит за месяц; null у «раз в две недели» (среднее не считаем)
  monthly_amount: string | null;
  // Ближайшая необработанная дата или null, если правило закончилось
  next_due_on: string | null;
  created_by_user_id: number | null;
  can_edit: boolean;
};

/** Тело запроса на создание правила. Пример: { kind: "expense", name: "Аренда", amount: 35000, frequency: "monthly", start_on: "2026-11-03", day_of_month: 3 }. */
export type RecurringRuleInput = {
  kind: FinanceKind;
  name: string;
  amount: number;
  category_id?: number | null;
  frequency: RuleFrequency;
  start_on: string;
  day_of_month?: number | null;
  second_day_of_month?: number | null;
  end_on?: string | null;
  auto_post?: boolean;
  is_primary?: boolean;
};

/** Частичное изменение правила: только те поля, которые меняются. */
export type RecurringRuleChanges = Partial<Omit<RecurringRuleInput, "kind">> & { is_active?: boolean };

/** Одно повторение правила: что, когда, сколько и в каком состоянии. */
export type Occurrence = {
  rule_id: number;
  rule_name: string;
  kind: FinanceKind;
  category_name: string;
  due_on: string;
  planned_amount: string;
  amount: string;
  status: OccurrenceStatus;
  // true, если дата прошла, а выплата не отмечена
  overdue: boolean;
  transaction_id: number | null;
  // Основной или дополнительный доход / платёж
  is_primary: boolean;
};

/**
 * Ожидаемое поступление, о котором пора спросить «Поступил ли платёж?» (±2 дня от плановой даты).
 * Элемент ответа GET /finance/income-prompts.
 */
export type IncomePrompt = {
  ledger_id: number;
  ledger_kind: LedgerKind;
  household_name: string | null;
  currency: string;
  rule_id: number;
  rule_name: string;
  due_on: string;
  planned_amount: string;
  is_primary: boolean;
};

/**
 * Деньги одной книги для главной: сколько всего и сколько свободно в текущем периоде.
 * Элемент ответа GET /finance/home.
 */
export type FinanceHomeLedger = {
  ledger_id: number;
  kind: LedgerKind;
  household_id: number | null;
  household_name: string | null;
  currency: string;
  // Баланс-кошелёк: только фактические операции по сегодняшний день и корректировки баланса.
  // Ожидаемые доходы и неоплаченные платежи не входят
  total: string;
  // Баланс минус неоплаченные обязательные платежи до следующего основного дохода; null — дохода нет
  free: string | null;
  // Дата следующего основного дохода: «Свободно до 10 нояб.»
  free_until: string | null;
  spending_status: SpendingStatus;
  // Текст вместо числа: «Нет следующего дохода: …», «Не хватает 600 ₽ до 31 окт»
  spending_note: string | null;
  period_start: string;
  period_end: string;
};

/** Корректировка баланса: разница между фактическим остатком и насчитанным. amount со знаком, например "2300.00" или "-500.00". */
export type BalanceAdjustment = {
  id: number;
  amount: string;
  adjusted_on: string;
  note: string | null;
  created_by_user_id: number | null;
  created_by_name: string | null;
  created_at: string;
};

/** Баланс книги и последние корректировки (новые сначала). Ответ GET/POST /finance/ledgers/{id}/balance. */
export type LedgerBalance = {
  ledger_id: number;
  currency: string;
  total: string;
  adjustments_total: string;
  adjustments: BalanceAdjustment[];
};

/** Тело POST /finance/ledgers/{id}/balance: «сколько сейчас на самом деле». Пример: { actual: 52300, note: "сверка с банком" }. */
export type BalanceSetInput = {
  actual: number;
  note?: string;
};

/** Совет, уже написанный словами. */
export type AdviceItem = {
  code: string;
  severity: Severity;
  text: string;
};

/** Один бюджетный период. */
export type Cycle = {
  start: string;
  end: string;
  is_current: boolean;
  days_total: number;
  days_left: number | null;
  income_received: string;
  income_expected: string;
  income_total: string;
  mandatory_paid: string;
  mandatory_pending: string;
  mandatory_total: string;
  other_spent: string;
  free_after_mandatory: string;
  // Прогноз периода вместе с ожидаемым доходом. «Сколько можно тратить сейчас» — в CyclesReport.spending
  available: string;
  // Доля обязательных платежей в доходе: 0.78 = 78 %
  mandatory_share: number | null;
  status: "ok" | "tight" | "gap";
  items: Occurrence[];
};

/** ok — хватает; gap — не хватает; no_income — нет следующего основного дохода; income_today — доход ожидается сегодня. */
export type SpendingStatus = "ok" | "gap" | "no_income" | "income_today";

/**
 * «Баланс → Свободно → Можно тратить в день»: один расчёт сервера для главной и «Финансы → Обзор».
 * free = balance − mandatory_due; daily_allowance = free ÷ days_left. Ожидаемые доходы не входят.
 * Пример: { balance: "86000.00", mandatory_due: "35000.00", free: "51000.00", next_income_on: "2026-11-10",
 *           days_left: 13, daily_allowance: "3923.08", status: "ok", note: null }
 */
export type SpendingPlan = {
  balance: string;
  mandatory_due: string;
  free: string | null;
  next_income_on: string | null;
  days_left: number | null;
  daily_allowance: string | null;
  status: SpendingStatus;
  note: string | null;
};

/** Ответ GET /finance/ledgers/{id}/cycles. */
export type CyclesReport = {
  ledger_id: number;
  currency: string;
  mode: CycleMode;
  today: string;
  spending: SpendingPlan;
  cycles: Cycle[];
  advice: AdviceItem[];
};

/** Итоги за произвольный период (месяц или бюджетный период). */
export type PeriodSummary = {
  ledger_id: number;
  start: string;
  end: string;
  currency: string;
  income: string;
  expense: string;
  balance: string;
  categories: CategorySummary[];
};

export type LoadItem = { name: string; monthly_amount: string };

/** Оценка финансовой нагрузки. Ответ GET /finance/ledgers/{id}/load. */
export type LoadReport = {
  ledger_id: number;
  currency: string;
  income_monthly: string;
  mandatory_monthly: string;
  free_monthly: string;
  // Обязательные платежи в процентах от дохода: 71.4 = 71,4 %
  mandatory_share: number | null;
  status: "no_income" | "comfortable" | "moderate" | "high" | "critical";
  avg_other_expense_monthly: string | null;
  left_after_expenses: string | null;
  safe_extra_payment: string;
  emergency_fund_target: string;
  mandatory_items: LoadItem[];
  advice: AdviceItem[];
};

/** Что будет, если взять ещё один ежемесячный платёж. */
export type LoadSimulation = {
  ledger_id: number;
  currency: string;
  payment: string;
  income_monthly: string;
  mandatory_monthly: string;
  new_mandatory_monthly: string;
  new_free_monthly: string;
  new_mandatory_share: number | null;
  verdict: "ok" | "risky" | "not_recommended";
  text: string;
  advice: AdviceItem[];
};

/** Вид цели: накопление, простой долг, кредит с процентами. */
export type FinanceGoalKind = "savings" | "debt" | "loan";

export type FinanceGoalContributor = {
  user_id: number | null;
  name: string;
  total: string;
  // Доля от общей суммы взносов, от 0 до 1
  share: number;
};

/** Финансовая цель и её состояние. */
export type FinanceGoal = {
  id: number;
  ledger_id: number;
  // true — цель общая (в семейной книге), false — личная
  shared: boolean;
  kind: FinanceGoalKind;
  name: string;
  target_amount: string;
  start_amount: string;
  interest_rate: string | null;
  payment_day: number | null;
  next_payment_on: string | null;
  currency: string;
  // Доля выполнения от 0 до 1
  progress: number;
  // Накопление: сколько осталось накопить. Долг и кредит: остаток основного долга
  remaining: string;
  paid_total: string;
  done: boolean;
  last_interest: string | null;
  interest_paid_total: string | null;
  contributors: FinanceGoalContributor[];
  can_edit: boolean;
  created_by_user_id: number | null;
  created_at: string;
};

export type FinanceGoalEntry = {
  id: number;
  goal_id: number;
  user_id: number | null;
  user_name: string;
  paid_on: string;
  amount: string;
  interest_part: string | null;
  principal_part: string | null;
  balance_after: string | null;
  note: string | null;
  // Расход, из которого создана запись; null — взнос внесён вручную. Такая запись меняется через «Операции»
  transaction_id: number | null;
  can_delete: boolean;
};

/** Цель вместе с историей взносов (новые сверху). */
export type FinanceGoalDetail = FinanceGoal & { entries: FinanceGoalEntry[] };

/** Тело запроса на создание цели. Пример кредита: { kind: "loan", name: "Кредит", target_amount: 100000, interest_rate: 60, payment_day: 15 }. */
export type FinanceGoalInput = {
  kind: FinanceGoalKind;
  name: string;
  target_amount: number;
  start_amount?: number;
  interest_rate?: number | null;
  payment_day?: number | null;
};

export type FinanceGoalChanges = Partial<Omit<FinanceGoalInput, "kind">>;

export type FinanceGoalEntryInput = {
  amount: number;
  paid_on?: string | null;
  note?: string | null;
};

/** Что произойдёт при удалении аккаунта. Ответ GET /auth/delete-account/preview. */
export type DeletionPreview = {
  email: string | null;
  households_to_delete: { id: number; name: string }[];
  households_to_leave: { id: number; name: string; new_owner_name: string | null }[];
  // Сколько записей будет стёрто: weight_records, meal_entries, training_sessions, progress_photos, finance_transactions
  counts: Record<string, number>;
};
