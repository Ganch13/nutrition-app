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
  created_at: string;
};

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
  created_at: string;
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
  created_by_user_id: number;
  created_by_name: string;
  created_at: string;
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
};