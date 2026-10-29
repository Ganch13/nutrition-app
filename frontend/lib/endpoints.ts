// Все запросы к backend, которые использует интерфейс. Каждая функция —
// единственное место, где записан адрес эндпоинта. Адреса сверены с backend/main.py.

import { apiBlob, apiRequest, endSession, storeAccessToken } from "./api";
import type {
  AccessKey,
  CreatedAccessKey,
  CycleMode,
  CyclesReport,
  DeletionPreview,
  FinanceGoal,
  FinanceGoalChanges,
  FinanceGoalDetail,
  FinanceGoalEntryInput,
  FinanceGoalInput,
  LoadReport,
  LoadSimulation,
  IncomePrompt,
  FinanceHomeLedger,
  BalanceSetInput,
  LedgerBalance,
  Occurrence,
  PeriodSummary,
  RecurringRule,
  RecurringRuleChanges,
  RecurringRuleInput,
  DailyNutritionSummary,
  GoalInput,
  GoalStatus,
  Intensity,
  LoginResponse,
  MealEntry,
  MealEntryInput,
  ProfilePatch,
  ProfileUpdateInput,
  RegisterInput,
  TrainingSession,
  TrainingSessionInput,
  TrainingSessionStatus,
  UserGoal,
  UserProfile,
  WeightRecord,
  WeightRecordInput,
  Workout,
  WorkoutInput,
  FinanceCategory,
  FinanceKind,
  FinanceSummary,
  FinanceTransaction,
  FinanceTransactionInput,
  FinanceTransactionChanges,
  ExpenseSummary,
  ExpenseSummaryCheck,
  ExpenseSummaryCheckInput,
  ExpenseSummaryCreateInput,
  Ledger,
  LedgerCreateInput,
  UserHousehold,
  HouseholdInvite,
  HouseholdMember,
  HouseholdRole,
  ScheduleEvent,
  ScheduleEventInput,
  ScheduleSeriesInput,
  ScheduleWeek,
  Food,
  FoodCategory,
  FoodInput,
  FoodList,
  FoodNutrition,
  MealFromFoodInput,
  GoalProgress,
  NutritionSettings,
  NutritionSettingsInput,
  NutritionTarget,
  PlanMealType,
  Recipe,
  RecipeInput,
  RecipeList,
  PlannedMeal,
  PlannedMealInput,
  PlannedMealChanges,
  MealPlanWeek,
  MealPlanGenerateInput,
  MealPlanGenerateResult,
  ShoppingList,
  CookingPlan,
  FamilyPlanningState,
  FamilyPlanWeek,
  FamilyPlanGenerateInput,
  FamilyPlanGenerateResult,
  PhotoAngle,
  ProgressPhoto,
  ProgressPhotoChanges,
} from "./types";


/** Настройки запроса с телом JSON. */
function withBody(method: "POST" | "PATCH" | "PUT", data: unknown): RequestInit {
  return { method, body: JSON.stringify(data) };
}

/** POST /auth/register. Создаёт пользователя; возвращает его профиль. */
export function registerUser(data: RegisterInput): Promise<UserProfile> {
  return apiRequest<UserProfile>("/auth/register", withBody("POST", data));
}

/** POST /auth/login. Возвращает токен: { access_token: "eyJ...", token_type: "bearer" }. */
export function loginUser(email: string, password: string): Promise<LoginResponse> {
  return apiRequest<LoginResponse>("/auth/login", withBody("POST", { email, password }));
}

/**
 * POST /auth/change-password. Меняет пароль и сохраняет новый токен: на этом устройстве человек остаётся в приложении,
 * на остальных устройствах сессии закрываются. Пример: changePassword("старый-пароль-123", "новый-длинный-пароль-456").
 */
export async function changePassword(currentPassword: string, newPassword: string): Promise<void> {
  const token = await apiRequest<LoginResponse>(
    "/auth/change-password",
    withBody("POST", { current_password: currentPassword, new_password: newPassword }),
  );
  storeAccessToken(token.access_token);
}

/** GET /auth/delete-account/preview. Что будет стёрто и что станет с семьями при удалении аккаунта (ничего не меняет). */
export function getDeletionPreview(): Promise<DeletionPreview> {
  return apiRequest<DeletionPreview>("/auth/delete-account/preview");
}

/**
 * POST /auth/delete-account. Безвозвратно удаляет аккаунт; нужен пароль.
 * Пример: deleteAccount("мой-пароль-123456"). После успеха сессия закрывается, открывается страница входа
 * с сообщением «Аккаунт удалён». Неверный пароль даёт ошибку 403 «Пароль указан неверно».
 */
export async function deleteAccount(password: string): Promise<void> {
  await apiRequest<void>("/auth/delete-account", withBody("POST", { password }));
  try {
    sessionStorage.setItem("lad_notice", "Аккаунт удалён. Все ваши данные стёрты.");
  } catch {
    // Сообщение необязательно: без хранилища браузера просто откроется страница входа
  }
  endSession("/login");
}

/** GET /users/me. Профиль владельца токена. */
export function getProfile(): Promise<UserProfile> {
  return apiRequest<UserProfile>("/users/me");
}

/** PATCH /users/{userId}. Сохраняет профиль; возвращает обновлённый профиль. */
export function updateProfile(userId: number, data: ProfileUpdateInput): Promise<UserProfile> {
  return apiRequest<UserProfile>(`/users/${userId}`, withBody("PATCH", data));
}

/** PATCH /users/{userId} с частью полей, например { home_hidden_blocks: ["weight"] }. */
export function patchProfile(userId: number, data: ProfilePatch): Promise<UserProfile> {
  return apiRequest<UserProfile>(`/users/${userId}`, withBody("PATCH", data));
}

/** GET /users/{userId}/weight-records. История веса, новые записи первыми (через дефис!). */
export function getWeightRecords(userId: number): Promise<WeightRecord[]> {
  return apiRequest<WeightRecord[]>(`/users/${userId}/weight-records`);
}

/** POST /users/{userId}/weight-records. Добавляет запись веса. */
export function createWeightRecord(userId: number, data: WeightRecordInput): Promise<WeightRecord> {
  return apiRequest<WeightRecord>(`/users/${userId}/weight-records`, withBody("POST", data));
}

/** DELETE /users/{userId}/weight-records/{recordId}. Ответ 204 без тела. */
export function deleteWeightRecord(userId: number, recordId: number): Promise<void> {
  return apiRequest<void>(`/users/${userId}/weight-records/${recordId}`, { method: "DELETE" });
}

/** GET /users/{userId}/goals. Сначала активные, внутри группы по приоритету (1 — высший). */
export function getGoals(userId: number): Promise<UserGoal[]> {
  return apiRequest<UserGoal[]>(`/users/${userId}/goals`);
}

/** POST /users/{userId}/goals. Создаёт цель. */
export function createGoal(userId: number, data: GoalInput): Promise<UserGoal> {
  return apiRequest<UserGoal>(`/users/${userId}/goals`, withBody("POST", data));
}

/** PATCH /users/{userId}/goals/{goalId}. Меняет статус цели, например на "paused". */
export function updateGoalStatus(userId: number, goalId: number, status: GoalStatus): Promise<UserGoal> {
  return apiRequest<UserGoal>(`/users/${userId}/goals/${goalId}`, withBody("PATCH", { status }));
}

/** GET /users/{userId}/nutrition/daily-summary?target_date=2026-10-23. Итоги дня. */
export function getDailySummary(userId: number, date: string): Promise<DailyNutritionSummary> {
  return apiRequest<DailyNutritionSummary>(
    `/users/${userId}/nutrition/daily-summary?target_date=${date}`,
  );
}

/** GET /users/{userId}/nutrition/daily-entries?target_date=2026-10-23. Приёмы пищи за день. */
export function getDailyEntries(userId: number, date: string): Promise<MealEntry[]> {
  return apiRequest<MealEntry[]>(`/users/${userId}/nutrition/daily-entries?target_date=${date}`);
}

/** POST /users/{userId}/meal-entries. Добавляет приём пищи. */
export function createMealEntry(userId: number, data: MealEntryInput): Promise<MealEntry> {
  return apiRequest<MealEntry>(`/users/${userId}/meal-entries`, withBody("POST", data));
}

/** DELETE /users/{userId}/meal-entries/{entryId}. Ответ 204 без тела. */
export function deleteMealEntry(userId: number, entryId: number): Promise<void> {
  return apiRequest<void>(`/users/${userId}/meal-entries/${entryId}`, { method: "DELETE" });
}

/** GET /users/{userId}/training-sessions. Все сессии, новые первыми. */
export function getTrainingSessions(userId: number): Promise<TrainingSession[]> {
  return apiRequest<TrainingSession[]>(`/users/${userId}/training-sessions`);
}

/** POST /users/{userId}/training-sessions. Создаёт сессию со статусом "planned". */
export function createTrainingSession(userId: number, data: TrainingSessionInput): Promise<TrainingSession> {
  return apiRequest<TrainingSession>(`/users/${userId}/training-sessions`, withBody("POST", data));
}

/** PATCH /users/{userId}/training-sessions/{sessionId}. Например { status: "completed" }. */
export function updateTrainingSession(
  userId: number,
  sessionId: number,
  changes: { status?: TrainingSessionStatus; notes?: string | null },
): Promise<TrainingSession> {
  return apiRequest<TrainingSession>(
    `/users/${userId}/training-sessions/${sessionId}`,
    withBody("PATCH", changes),
  );
}

/** GET /users/{userId}/training-sessions/{sessionId}/workouts. Блоки сессии по времени. */
export function getWorkouts(userId: number, sessionId: number): Promise<Workout[]> {
  return apiRequest<Workout[]>(`/users/${userId}/training-sessions/${sessionId}/workouts`);
}

/** POST .../workouts. Время блока должно лежать внутри сессии. */
export function createWorkout(userId: number, sessionId: number, data: WorkoutInput): Promise<Workout> {
  return apiRequest<Workout>(
    `/users/${userId}/training-sessions/${sessionId}/workouts`,
    withBody("POST", data),
  );
}

/** PATCH .../workouts/{workoutId}. Фактическая интенсивность, заметки и отметка «Выполнил». */
export function updateWorkout(
  userId: number,
  sessionId: number,
  workoutId: number,
  changes: { actual_intensity?: Intensity | null; notes?: string | null; completed?: boolean },
): Promise<Workout> {
  return apiRequest<Workout>(
    `/users/${userId}/training-sessions/${sessionId}/workouts/${workoutId}`,
    withBody("PATCH", changes),
  );
}


/** DELETE /users/{userId}/goals/{goalId}. Удаляет цель навсегда; ответ 204 без тела. */
export function deleteGoal(userId: number, goalId: number): Promise<void> {
  return apiRequest<void>(`/users/${userId}/goals/${goalId}`, { method: "DELETE" });
}

/** DELETE /users/{userId}/training-sessions/{sessionId}. Удаляет сессию вместе с блоками. */
export function deleteTrainingSession(userId: number, sessionId: number): Promise<void> {
  return apiRequest<void>(`/users/${userId}/training-sessions/${sessionId}`, { method: "DELETE" });
}

/** DELETE .../workouts/{workoutId}. Удаляет один блок тренировки. */
export function deleteWorkout(userId: number, sessionId: number, workoutId: number): Promise<void> {
  return apiRequest<void>(
    `/users/${userId}/training-sessions/${sessionId}/workouts/${workoutId}`,
    { method: "DELETE" },
  );
}

/** POST /households. Создаёт домохозяйство; создатель становится владельцем.
 *  Пример: createHousehold("Дом") → { id: 1, name: "Дом", created_at: "..." } */
export function createHousehold(name: string): Promise<Omit<UserHousehold, "role">> {
  return apiRequest<Omit<UserHousehold, "role">>("/households", withBody("POST", { name }));
}

/** GET /households/{id}/members. Участники с именами; доступно любому участнику. */
export function getHouseholdMembers(householdId: number): Promise<HouseholdMember[]> {
  return apiRequest<HouseholdMember[]>(`/households/${householdId}/members`);
}

/** POST /households/{id}/invites. Новый код на 7 дней (владелец или администратор). */
export function createHouseholdInvite(householdId: number): Promise<HouseholdInvite> {
  return apiRequest<HouseholdInvite>(`/households/${householdId}/invites`, { method: "POST" });
}

/** GET /households/{id}/invites. Действующие коды (владелец или администратор). */
export function getHouseholdInvites(householdId: number): Promise<HouseholdInvite[]> {
  return apiRequest<HouseholdInvite[]>(`/households/${householdId}/invites`);
}

/** DELETE /households/{id}/invites/{inviteId}. Отзывает неиспользованный код. */
export function deleteHouseholdInvite(householdId: number, inviteId: number): Promise<void> {
  return apiRequest<void>(`/households/${householdId}/invites/${inviteId}`, { method: "DELETE" });
}

/** POST /households/join. Вступление по коду, например joinHousehold("K7M2-9QXP"). */
export function joinHousehold(code: string): Promise<UserHousehold> {
  return apiRequest<UserHousehold>("/households/join", withBody("POST", { code }));
}

/** PATCH /households/{id}/members/{userId}. Меняет роль (только владелец). */
export function changeMemberRole(
  householdId: number,
  userId: number,
  role: Exclude<HouseholdRole, "owner">,
): Promise<HouseholdMember> {
  return apiRequest<HouseholdMember>(
    `/households/${householdId}/members/${userId}`,
    withBody("PATCH", { role }),
  );
}

/** DELETE /households/{id}/members/{userId}. Удаляет участника или выход (userId = ваш id). */
export function removeHouseholdMember(householdId: number, userId: number): Promise<void> {
  return apiRequest<void>(`/households/${householdId}/members/${userId}`, { method: "DELETE" });
}



/** GET /households. Домохозяйства пользователя с его ролью в каждом. */
export function getHouseholds(): Promise<UserHousehold[]> {
  return apiRequest<UserHousehold[]>("/households");
}

/** GET /finance/ledgers. Личная книга (если есть) и семейные книги. */
export function getLedgers(): Promise<Ledger[]> {
  return apiRequest<Ledger[]>("/finance/ledgers");
}

/** POST /finance/ledgers. Создаёт личную или семейную книгу. */
export function createLedger(data: LedgerCreateInput): Promise<Ledger> {
  return apiRequest<Ledger>("/finance/ledgers", withBody("POST", data));
}

/** GET /finance/ledgers/{ledgerId}/categories. */
export function getFinanceCategories(ledgerId: number): Promise<FinanceCategory[]> {
  return apiRequest<FinanceCategory[]>(`/finance/ledgers/${ledgerId}/categories`);
}

/** POST /finance/ledgers/{ledgerId}/categories. Например { name: "Подарки", kind: "expense" }. */
export function createFinanceCategory(
  ledgerId: number,
  data: { name: string; kind: FinanceKind },
): Promise<FinanceCategory> {
  return apiRequest<FinanceCategory>(`/finance/ledgers/${ledgerId}/categories`, withBody("POST", data));
}

/** DELETE /finance/ledgers/{ledgerId}/categories/{categoryId}. */
export function deleteFinanceCategory(ledgerId: number, categoryId: number): Promise<void> {
  return apiRequest<void>(`/finance/ledgers/${ledgerId}/categories/${categoryId}`, { method: "DELETE" });
}

/** GET /finance/ledgers/{ledgerId}/transactions?month=2026-10. Новые первыми. */
export function getFinanceTransactions(ledgerId: number, month: string): Promise<FinanceTransaction[]> {
  return apiRequest<FinanceTransaction[]>(`/finance/ledgers/${ledgerId}/transactions?month=${month}`);
}

/** POST /finance/ledgers/{ledgerId}/transactions. Добавляет операцию. */
export function createFinanceTransaction(
  ledgerId: number,
  data: FinanceTransactionInput,
): Promise<FinanceTransaction> {
  return apiRequest<FinanceTransaction>(`/finance/ledgers/${ledgerId}/transactions`, withBody("POST", data));
}

/**
 * PATCH /finance/ledgers/{ledgerId}/transactions/{transactionId}. Меняет операцию; запись в цели меняется вместе с ней.
 * Пример: { amount: 3000 } или { goal_id: null } (отвязать от цели).
 */
export function updateFinanceTransaction(
  ledgerId: number,
  transactionId: number,
  data: FinanceTransactionChanges,
): Promise<FinanceTransaction> {
  return apiRequest<FinanceTransaction>(`/finance/ledgers/${ledgerId}/transactions/${transactionId}`, withBody("PATCH", data));
}

/**
 * POST /finance/ledgers/{ledgerId}/summaries/check. Сверка сводки с уже записанными расходами, ничего не сохраняет.
 * Пример: { period_start: "2026-10-19", period_end: "2026-10-25", lines: [{ category_id: 3, amount: 8000 }] }.
 */
export function checkExpenseSummary(ledgerId: number, data: ExpenseSummaryCheckInput): Promise<ExpenseSummaryCheck> {
  return apiRequest<ExpenseSummaryCheck>(`/finance/ledgers/${ledgerId}/summaries/check`, withBody("POST", data));
}

/** POST /finance/ledgers/{ledgerId}/summaries. Сохраняет сводку; при пересечении без mode сервер ответит 409. */
export function createExpenseSummary(ledgerId: number, data: ExpenseSummaryCreateInput): Promise<ExpenseSummary> {
  return apiRequest<ExpenseSummary>(`/finance/ledgers/${ledgerId}/summaries`, withBody("POST", data));
}

/** DELETE /finance/ledgers/{ledgerId}/summaries/{summaryId}. Удаляет сводку целиком (баланс и цели откатываются). */
export function deleteExpenseSummary(ledgerId: number, summaryId: number): Promise<void> {
  return apiRequest<void>(`/finance/ledgers/${ledgerId}/summaries/${summaryId}`, { method: "DELETE" });
}

/** DELETE /finance/ledgers/{ledgerId}/transactions/{transactionId}. */
export function deleteFinanceTransaction(ledgerId: number, transactionId: number): Promise<void> {
  return apiRequest<void>(`/finance/ledgers/${ledgerId}/transactions/${transactionId}`, { method: "DELETE" });
}

/** PUT .../budgets/{categoryId}. Задаёт месячный лимит; null убирает его. */
export function setFinanceBudget(
  ledgerId: number,
  categoryId: number,
  monthlyLimit: number | null,
): Promise<void> {
  return apiRequest<void>(
    `/finance/ledgers/${ledgerId}/budgets/${categoryId}`,
    withBody("PUT", { monthly_limit: monthlyLimit }),
  );
}

/** GET /finance/ledgers/{ledgerId}/summary?month=2026-10. Итоги месяца. */
export function getFinanceSummary(ledgerId: number, month: string): Promise<FinanceSummary> {
  return apiRequest<FinanceSummary>(`/finance/ledgers/${ledgerId}/summary?month=${month}`);
}

// ---------- Расписание (шаг 64) ----------

/** GET /users/{userId}/schedule/week?start=2026-10-26. События, тренировки и пересечения на 7 дней. */
export function getScheduleWeek(userId: number, start: string): Promise<ScheduleWeek> {
  return apiRequest<ScheduleWeek>(`/users/${userId}/schedule/week?start=${start}`);
}

/** POST /users/{userId}/schedule-events. Одно событие. */
export function createScheduleEvent(userId: number, data: ScheduleEventInput): Promise<ScheduleEvent> {
  return apiRequest<ScheduleEvent>(`/users/${userId}/schedule-events`, withBody("POST", data));
}

/** PATCH /users/{userId}/schedule-events/{eventId}. Меняет переданные поля. */
export function updateScheduleEvent(
  userId: number,
  eventId: number,
  changes: Partial<ScheduleEventInput>,
): Promise<ScheduleEvent> {
  return apiRequest<ScheduleEvent>(`/users/${userId}/schedule-events/${eventId}`, withBody("PATCH", changes));
}

/** DELETE /users/{userId}/schedule-events/{eventId}?scope=one|following. Ответ 204. */
export function deleteScheduleEvent(
  userId: number,
  eventId: number,
  scope: "one" | "following" = "one",
): Promise<void> {
  return apiRequest<void>(`/users/${userId}/schedule-events/${eventId}?scope=${scope}`, { method: "DELETE" });
}

/** POST /users/{userId}/schedule-events/series. События по дням недели на несколько недель. */
export function createScheduleSeries(
  userId: number,
  data: ScheduleSeriesInput,
): Promise<{ series_id: string; events: ScheduleEvent[] }> {
  return apiRequest<{ series_id: string; events: ScheduleEvent[] }>(
    `/users/${userId}/schedule-events/series`,
    withBody("POST", data),
  );
}

// ---------- Справочник продуктов (шаг 65) ----------

/** GET /foods?q=творог&category=dairy&limit=20. Поиск среди встроенных, своих и семейных продуктов. */
export function getFoods(params: {
  q?: string;
  category?: FoodCategory | "";
  limit?: number;
  offset?: number;
}): Promise<FoodList> {
  const search = new URLSearchParams();
  if (params.q) search.set("q", params.q);
  if (params.category) search.set("category", params.category);
  search.set("limit", String(params.limit ?? 50));
  if (params.offset) search.set("offset", String(params.offset));
  return apiRequest<FoodList>(`/foods?${search.toString()}`);
}

/** POST /foods. Свой продукт (или семейный, если указан household_id). */
export function createFood(data: FoodInput): Promise<Food> {
  return apiRequest<Food>("/foods", withBody("POST", data));
}

/** PATCH /foods/{id}. Меняет свой продукт. */
export function updateFood(foodId: number, changes: Partial<Omit<FoodInput, "household_id">>): Promise<Food> {
  return apiRequest<Food>(`/foods/${foodId}`, withBody("PATCH", changes));
}

/** DELETE /foods/{id}. Ответ 204. */
export function deleteFood(foodId: number): Promise<void> {
  return apiRequest<void>(`/foods/${foodId}`, { method: "DELETE" });
}

/** GET /foods/{id}/nutrition?amount_g=150. КБЖУ заданной массы (считает сервер). */
export function getFoodNutrition(foodId: number, amountG: number): Promise<FoodNutrition> {
  return apiRequest<FoodNutrition>(`/foods/${foodId}/nutrition?amount_g=${amountG}`);
}

/** POST /users/{userId}/meal-entries/from-food. Приём пищи из справочника; КБЖУ считает сервер. */
export function createMealFromFood(userId: number, data: MealFromFoodInput): Promise<MealEntry> {
  return apiRequest<MealEntry>(`/users/${userId}/meal-entries/from-food`, withBody("POST", data));
}

// ---------- Нормы питания и прогресс целей (шаг 66) ----------

/** GET /users/{userId}/nutrition/settings. Настройки расчёта норм (по умолчанию, если не сохранены). */
export function getNutritionSettings(userId: number): Promise<NutritionSettings> {
  return apiRequest<NutritionSettings>(`/users/${userId}/nutrition/settings`);
}

/** PUT /users/{userId}/nutrition/settings. Сохраняет настройки целиком. */
export function saveNutritionSettings(userId: number, data: NutritionSettingsInput): Promise<NutritionSettings> {
  return apiRequest<NutritionSettings>(`/users/${userId}/nutrition/settings`, withBody("PUT", data));
}

/** GET /users/{userId}/nutrition/targets?target_date=2026-10-27. Норма на день с объяснением расчёта. */
export function getNutritionTarget(userId: number, date: string): Promise<NutritionTarget> {
  return apiRequest<NutritionTarget>(`/users/${userId}/nutrition/targets?target_date=${date}`);
}

/** GET /users/{userId}/goals/progress. Прогресс активных целей. */
export function getGoalProgress(userId: number): Promise<GoalProgress[]> {
  return apiRequest<GoalProgress[]>(`/users/${userId}/goals/progress`);
}

// ---------- Рецепты (шаг 67) ----------

/** GET /recipes?q=курица&meal_type=lunch&portable=true. Встроенные, свои и семейные рецепты. */
export function getRecipes(params: {
  q?: string;
  mealType?: PlanMealType | "";
  portable?: boolean;
  limit?: number;
  offset?: number;
}): Promise<RecipeList> {
  const search = new URLSearchParams();
  if (params.q) search.set("q", params.q);
  if (params.mealType) search.set("meal_type", params.mealType);
  if (params.portable !== undefined) search.set("portable", String(params.portable));
  search.set("limit", String(params.limit ?? 50));
  if (params.offset) search.set("offset", String(params.offset));
  return apiRequest<RecipeList>(`/recipes?${search.toString()}`);
}

/** POST /recipes. Свой рецепт (или семейный, если указан household_id). */
export function createRecipe(data: RecipeInput): Promise<Recipe> {
  return apiRequest<Recipe>("/recipes", withBody("POST", data));
}

/** PATCH /recipes/{id}. Меняет свой рецепт; ingredients, если передан, заменяет список целиком. */
export function updateRecipe(recipeId: number, changes: Partial<Omit<RecipeInput, "household_id">>): Promise<Recipe> {
  return apiRequest<Recipe>(`/recipes/${recipeId}`, withBody("PATCH", changes));
}

/** DELETE /recipes/{id}. Ответ 204. */
export function deleteRecipe(recipeId: number): Promise<void> {
  return apiRequest<void>(`/recipes/${recipeId}`, { method: "DELETE" });
}

// ---------- План питания (шаг 67) ----------

/** GET /users/{userId}/meal-plan?start=2026-10-26. Семь дней плана с нормой на каждый день. */
export function getMealPlanWeek(userId: number, start: string): Promise<MealPlanWeek> {
  return apiRequest<MealPlanWeek>(`/users/${userId}/meal-plan?start=${start}`);
}

/** POST /users/{userId}/meal-plan/generate. Составляет план автоматически. */
export function generateMealPlan(userId: number, data: MealPlanGenerateInput): Promise<MealPlanGenerateResult> {
  return apiRequest<MealPlanGenerateResult>(`/users/${userId}/meal-plan/generate`, withBody("POST", data));
}

/** POST /users/{userId}/meal-plan/meals. Добавляет приём пищи вручную. */
export function createPlannedMeal(userId: number, data: PlannedMealInput): Promise<PlannedMeal> {
  return apiRequest<PlannedMeal>(`/users/${userId}/meal-plan/meals`, withBody("POST", data));
}

/** PATCH /users/{userId}/meal-plan/meals/{mealId}. Время, место, рецепт, размер порции. */
export function updatePlannedMeal(userId: number, mealId: number, changes: PlannedMealChanges): Promise<PlannedMeal> {
  return apiRequest<PlannedMeal>(`/users/${userId}/meal-plan/meals/${mealId}`, withBody("PATCH", changes));
}

/** DELETE /users/{userId}/meal-plan/meals/{mealId}. Ответ 204. */
export function deletePlannedMeal(userId: number, mealId: number): Promise<void> {
  return apiRequest<void>(`/users/${userId}/meal-plan/meals/${mealId}`, { method: "DELETE" });
}

/** POST …/meals/{mealId}/eat. «Съел»: создаёт запись в дневнике питания. */
export function eatPlannedMeal(userId: number, mealId: number): Promise<PlannedMeal> {
  return apiRequest<PlannedMeal>(`/users/${userId}/meal-plan/meals/${mealId}/eat`, { method: "POST" });
}

/** POST …/meals/{mealId}/skip. «Пропустил». */
export function skipPlannedMeal(userId: number, mealId: number): Promise<PlannedMeal> {
  return apiRequest<PlannedMeal>(`/users/${userId}/meal-plan/meals/${mealId}/skip`, { method: "POST" });
}

/** POST …/meals/{mealId}/reset. Возвращает в план; созданная запись питания удаляется. */
export function resetPlannedMeal(userId: number, mealId: number): Promise<PlannedMeal> {
  return apiRequest<PlannedMeal>(`/users/${userId}/meal-plan/meals/${mealId}/reset`, { method: "POST" });
}

// ---------- Закупки и готовка (шаг 68) ----------

/** GET /users/{userId}/shopping-list?start=2026-10-26&days=7. Продукты всех запланированных приёмов пищи. */
export function getShoppingList(userId: number, start: string, days: number): Promise<ShoppingList> {
  return apiRequest<ShoppingList>(`/users/${userId}/shopping-list?start=${start}&days=${days}`);
}

/** PUT /users/{userId}/shopping-list/checks. Ставит или снимает отметку «куплено». */
export function setShoppingCheck(userId: number, start: string, key: string, checked: boolean): Promise<void> {
  return apiRequest<void>(`/users/${userId}/shopping-list/checks`, withBody("PUT", { start, key, checked }));
}

/** DELETE /users/{userId}/shopping-list/checks?start=2026-10-26. Снимает все отметки периода. */
export function clearShoppingChecks(userId: number, start: string): Promise<void> {
  return apiRequest<void>(`/users/${userId}/shopping-list/checks?start=${start}`, { method: "DELETE" });
}

/** GET /users/{userId}/cooking-plan?start=2026-10-26&days=7. Что и когда готовить. */
export function getCookingPlan(userId: number, start: string, days: number): Promise<CookingPlan> {
  return apiRequest<CookingPlan>(`/users/${userId}/cooking-plan?start=${start}&days=${days}`);
}

// ---------- Семейное планирование (шаг 69) ----------

/** GET /households/{id}/planning. Кто из семьи включил «Планировать вместе». */
export function getFamilyPlanning(householdId: number): Promise<FamilyPlanningState> {
  return apiRequest<FamilyPlanningState>(`/households/${householdId}/planning`);
}

/** PUT /households/{id}/planning/me. Включает или выключает ваше участие в общем плане. */
export function setMyFamilyPlanning(householdId: number, plansTogether: boolean): Promise<FamilyPlanningState> {
  return apiRequest<FamilyPlanningState>(
    `/households/${householdId}/planning/me`,
    withBody("PUT", { plans_together: plansTogether }),
  );
}

/** GET /households/{id}/meal-plan?start=2026-10-26. Планы всей семьи на 7 дней (без калорий). */
export function getFamilyPlanWeek(householdId: number, start: string): Promise<FamilyPlanWeek> {
  return apiRequest<FamilyPlanWeek>(`/households/${householdId}/meal-plan?start=${start}`);
}

/** POST /households/{id}/meal-plan/generate. Планы всем участникам и общий ужин. */
export function generateFamilyPlan(
  householdId: number,
  data: FamilyPlanGenerateInput,
): Promise<FamilyPlanGenerateResult> {
  return apiRequest<FamilyPlanGenerateResult>(`/households/${householdId}/meal-plan/generate`, withBody("POST", data));
}

/** GET /households/{id}/shopping-list?start=2026-10-26&days=7. Общий список закупок семьи. */
export function getFamilyShoppingList(householdId: number, start: string, days: number): Promise<ShoppingList> {
  return apiRequest<ShoppingList>(`/households/${householdId}/shopping-list?start=${start}&days=${days}`);
}

/** PUT /households/{id}/shopping-list/checks. Отметка «куплено» в общем списке. */
export function setFamilyShoppingCheck(
  householdId: number,
  start: string,
  key: string,
  checked: boolean,
): Promise<void> {
  return apiRequest<void>(`/households/${householdId}/shopping-list/checks`, withBody("PUT", { start, key, checked }));
}

/** DELETE /households/{id}/shopping-list/checks?start=2026-10-26. Снимает все отметки общего списка. */
export function clearFamilyShoppingChecks(householdId: number, start: string): Promise<void> {
  return apiRequest<void>(`/households/${householdId}/shopping-list/checks?start=${start}`, { method: "DELETE" });
}

/** GET /households/{id}/cooking-plan?start=2026-10-26&days=7. Общий план готовки. */
export function getFamilyCookingPlan(householdId: number, start: string, days: number): Promise<CookingPlan> {
  return apiRequest<CookingPlan>(`/households/${householdId}/cooking-plan?start=${start}&days=${days}`);
}

// ---------- Фото прогресса (шаг 70) ----------

/** GET /users/{userId}/progress-photos?limit=200. Фото, новые сверху. */
export function getProgressPhotos(userId: number): Promise<ProgressPhoto[]> {
  return apiRequest<ProgressPhoto[]>(`/users/${userId}/progress-photos?limit=200`);
}

/**
 * POST /users/{userId}/progress-photos. Тело запроса — сам файл, а не JSON.
 * Пример: uploadProgressPhoto(1, blob, "2026-10-27", "front", "Утром") →
 * POST /users/1/progress-photos?taken_on=2026-10-27&angle=front&note=%D0%A3%D1%82%D1%80%D0%BE%D0%BC
 */
export function uploadProgressPhoto(
  userId: number,
  file: Blob,
  takenOn: string,
  angle: PhotoAngle,
  note: string | null,
): Promise<ProgressPhoto> {
  const query = new URLSearchParams({ taken_on: takenOn, angle });
  if (note) query.set("note", note);
  return apiRequest<ProgressPhoto>(`/users/${userId}/progress-photos?${query.toString()}`, {
    method: "POST",
    body: file,
    headers: { "Content-Type": file.type },
  });
}

/** PATCH /users/{userId}/progress-photos/{photoId}. Дата, ракурс или подпись. */
export function updateProgressPhoto(
  userId: number,
  photoId: number,
  changes: ProgressPhotoChanges,
): Promise<ProgressPhoto> {
  return apiRequest<ProgressPhoto>(`/users/${userId}/progress-photos/${photoId}`, withBody("PATCH", changes));
}

/** DELETE /users/{userId}/progress-photos/{photoId}. Удаляет фото вместе с файлом. */
export function deleteProgressPhoto(userId: number, photoId: number): Promise<void> {
  return apiRequest<void>(`/users/${userId}/progress-photos/${photoId}`, { method: "DELETE" });
}

/** Скачивает файл фото по его адресу из ответа сервера (photo.url). */
export function getProgressPhotoFile(url: string): Promise<Blob> {
  return apiBlob(url);
}


// ---- Релиз 1.1: повторяющиеся платежи и доходы, бюджетные периоды, нагрузка, цели ----

/** GET /finance/ledgers/{id}/recurring. Все правила книги: повторяющиеся доходы и обязательные платежи. */
export function getRecurringRules(ledgerId: number): Promise<RecurringRule[]> {
  return apiRequest<RecurringRule[]>(`/finance/ledgers/${ledgerId}/recurring`);
}

/** POST /finance/ledgers/{id}/recurring. Пример: { kind: "income", name: "Аванс", amount: 50000, frequency: "monthly", start_on: "2026-10-10" }. */
export function createRecurringRule(ledgerId: number, data: RecurringRuleInput): Promise<RecurringRule> {
  return apiRequest<RecurringRule>(`/finance/ledgers/${ledgerId}/recurring`, withBody("POST", data));
}

/** PATCH /finance/ledgers/{id}/recurring/{ruleId}. Например { is_active: false } ставит правило на паузу. */
export function updateRecurringRule(
  ledgerId: number,
  ruleId: number,
  changes: RecurringRuleChanges,
): Promise<RecurringRule> {
  return apiRequest<RecurringRule>(`/finance/ledgers/${ledgerId}/recurring/${ruleId}`, withBody("PATCH", changes));
}

/** DELETE /finance/ledgers/{id}/recurring/{ruleId}. Уже созданные операции остаются. */
export function deleteRecurringRule(ledgerId: number, ruleId: number): Promise<void> {
  return apiRequest<void>(`/finance/ledgers/${ledgerId}/recurring/${ruleId}`, { method: "DELETE" });
}

/** POST .../recurring/{ruleId}/occurrences/{dueOn}/confirm. «Оплачено»: создаёт операцию. Сумму и дату можно уточнить. */
export function confirmOccurrence(
  ledgerId: number,
  ruleId: number,
  dueOn: string,
  actual?: { amount?: number; occurred_on?: string },
): Promise<FinanceTransaction> {
  return apiRequest<FinanceTransaction>(
    `/finance/ledgers/${ledgerId}/recurring/${ruleId}/occurrences/${dueOn}/confirm`,
    withBody("POST", actual ?? {}),
  );
}

/** POST .../recurring/{ruleId}/occurrences/{dueOn}/skip. Пропускает это повторение (операция не создаётся). */
export function skipOccurrence(ledgerId: number, ruleId: number, dueOn: string): Promise<void> {
  return apiRequest<void>(`/finance/ledgers/${ledgerId}/recurring/${ruleId}/occurrences/${dueOn}/skip`, {
    method: "POST",
  });
}

/** DELETE .../recurring/{ruleId}/occurrences/{dueOn}. «Отменить отметку»: выплата снова ожидается. */
export function undoOccurrence(ledgerId: number, ruleId: number, dueOn: string): Promise<void> {
  return apiRequest<void>(`/finance/ledgers/${ledgerId}/recurring/${ruleId}/occurrences/${dueOn}`, {
    method: "DELETE",
  });
}

/** GET /finance/income-prompts. Поступления во всех книгах, о которых пора спросить «Поступил ли платёж?». */
export function getIncomePrompts(): Promise<IncomePrompt[]> {
  return apiRequest<IncomePrompt[]>("/finance/income-prompts");
}

/** GET /finance/home. Деньги для главной: по каждой книге сколько всего и сколько свободно в периоде. */
export function getFinanceHome(): Promise<FinanceHomeLedger[]> {
  return apiRequest<FinanceHomeLedger[]>("/finance/home");
}

/** GET /finance/ledgers/{id}/balance. Баланс книги («Всего») и последние корректировки. */
export function getLedgerBalance(ledgerId: number): Promise<LedgerBalance> {
  return apiRequest<LedgerBalance>(`/finance/ledgers/${ledgerId}/balance`);
}

/**
 * POST /finance/ledgers/{id}/balance. Фактический остаток без дохода и расхода: сервер сохраняет разницу
 * как корректировку. Пример: { actual: 52300 } при «Всего» 50 000 → корректировка +2 300.
 */
export function setLedgerBalance(ledgerId: number, data: BalanceSetInput): Promise<LedgerBalance> {
  return apiRequest<LedgerBalance>(`/finance/ledgers/${ledgerId}/balance`, withBody("POST", data));
}

/** DELETE /finance/ledgers/{id}/balance/adjustments/{adjustmentId}. Отменяет корректировку, возвращает новый баланс. */
export function deleteBalanceAdjustment(ledgerId: number, adjustmentId: number): Promise<LedgerBalance> {
  return apiRequest<LedgerBalance>(`/finance/ledgers/${ledgerId}/balance/adjustments/${adjustmentId}`, {
    method: "DELETE",
  });
}

/** GET /finance/ledgers/{id}/upcoming?days=30. Просроченные и ближайшие выплаты. */
export function getUpcoming(ledgerId: number, days = 30): Promise<Occurrence[]> {
  return apiRequest<Occurrence[]>(`/finance/ledgers/${ledgerId}/upcoming?days=${days}`);
}

/** PATCH /finance/ledgers/{id}. Переключает бюджетный период: { cycle_mode: "income" } или "calendar". Только владелец и администратор. */
export function setCycleMode(ledgerId: number, mode: CycleMode): Promise<Ledger> {
  return apiRequest<Ledger>(`/finance/ledgers/${ledgerId}`, withBody("PATCH", { cycle_mode: mode }));
}

/**
 * GET /finance/ledgers/{id}/cycles?previous=0&count=2. Текущий период, следующий за ним и советы по ним.
 * Советы сервер считает только по запрошенным периодам, поэтому «Обзор» берёт ровно два.
 */
export function getCycles(ledgerId: number, previous = 0, count = 2): Promise<CyclesReport> {
  return apiRequest<CyclesReport>(`/finance/ledgers/${ledgerId}/cycles?previous=${previous}&count=${count}`);
}

/** GET /finance/ledgers/{id}/period-summary?on=2026-10-28. Итоги периода, в который попадает дата. */
export function getPeriodSummary(ledgerId: number, on?: string): Promise<PeriodSummary> {
  return apiRequest<PeriodSummary>(`/finance/ledgers/${ledgerId}/period-summary${on ? `?on=${on}` : ""}`);
}

/** GET /finance/ledgers/{id}/load. Хватает ли дохода на обязательные платежи. */
export function getLoad(ledgerId: number): Promise<LoadReport> {
  return apiRequest<LoadReport>(`/finance/ledgers/${ledgerId}/load`);
}

/** GET /finance/ledgers/{id}/load/simulate?payment=15000. Что будет, если взять ещё один платёж. */
export function simulateLoad(ledgerId: number, payment: number): Promise<LoadSimulation> {
  return apiRequest<LoadSimulation>(`/finance/ledgers/${ledgerId}/load/simulate?payment=${payment}`);
}

/** GET /finance/ledgers/{id}/goals. Цели книги (личной или семейной). */
export function getFinanceGoals(ledgerId: number): Promise<FinanceGoal[]> {
  return apiRequest<FinanceGoal[]>(`/finance/ledgers/${ledgerId}/goals`);
}

/** POST /finance/ledgers/{id}/goals. Пример: { kind: "savings", name: "Отпуск", target_amount: 200000, start_amount: 15000 }. */
export function createFinanceGoal(ledgerId: number, data: FinanceGoalInput): Promise<FinanceGoal> {
  return apiRequest<FinanceGoal>(`/finance/ledgers/${ledgerId}/goals`, withBody("POST", data));
}

/** GET /finance/ledgers/{id}/goals/{goalId}. Цель с историей взносов. */
export function getFinanceGoal(ledgerId: number, goalId: number): Promise<FinanceGoalDetail> {
  return apiRequest<FinanceGoalDetail>(`/finance/ledgers/${ledgerId}/goals/${goalId}`);
}

/** PATCH /finance/ledgers/{id}/goals/{goalId}. Название, сумма цели, ставка, день платежа. */
export function updateFinanceGoal(
  ledgerId: number,
  goalId: number,
  changes: FinanceGoalChanges,
): Promise<FinanceGoal> {
  return apiRequest<FinanceGoal>(`/finance/ledgers/${ledgerId}/goals/${goalId}`, withBody("PATCH", changes));
}

/** DELETE /finance/ledgers/{id}/goals/{goalId}. Вместе с историей взносов. */
export function deleteFinanceGoal(ledgerId: number, goalId: number): Promise<void> {
  return apiRequest<void>(`/finance/ledgers/${ledgerId}/goals/${goalId}`, { method: "DELETE" });
}

/** POST /finance/ledgers/{id}/goals/{goalId}/entries. Взнос или платёж. Пример: { amount: 20000, paid_on: "2026-10-15" }. */
export function addFinanceGoalEntry(
  ledgerId: number,
  goalId: number,
  data: FinanceGoalEntryInput,
): Promise<FinanceGoalDetail> {
  return apiRequest<FinanceGoalDetail>(`/finance/ledgers/${ledgerId}/goals/${goalId}/entries`, withBody("POST", data));
}

/** DELETE /finance/ledgers/{id}/goals/{goalId}/entries/{entryId}. Убирает взнос; проценты кредита пересчитываются. */
export function deleteFinanceGoalEntry(
  ledgerId: number,
  goalId: number,
  entryId: number,
): Promise<FinanceGoalDetail> {
  return apiRequest<FinanceGoalDetail>(`/finance/ledgers/${ledgerId}/goals/${goalId}/entries/${entryId}`, {
    method: "DELETE",
  });
}

// ---------------------------------------------------------------------------
// Личные ключи для быстрого добавления расхода с iPhone
// ---------------------------------------------------------------------------

/** GET /access-keys. Ключи пользователя: сначала действующие, новые выше. */
export function getAccessKeys(): Promise<AccessKey[]> {
  return apiRequest<AccessKey[]>("/access-keys");
}

/** POST /access-keys {"name": "iPhone"}. В ответе поле key — ключ целиком, он показывается один раз. */
export function createAccessKey(name: string): Promise<CreatedAccessKey> {
  return apiRequest<CreatedAccessKey>("/access-keys", withBody("POST", { name }));
}

/** DELETE /access-keys/{id}. Отзывает ключ: быстрая команда с ним сразу перестаёт работать. */
export function revokeAccessKey(keyId: number): Promise<AccessKey> {
  return apiRequest<AccessKey>(`/access-keys/${keyId}`, { method: "DELETE" });
}

/** Путь эндпоинта быстрого расхода (для инструкции в профиле; сам интерфейс его не вызывает). */
export const QUICK_EXPENSE_PATH = "/quick/expense";

/** Путь списка категорий для меню быстрой команды. */
export const QUICK_CATEGORIES_PATH = "/quick/categories";
