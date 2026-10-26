// Все запросы к backend, которые использует интерфейс. Каждая функция —
// единственное место, где записан адрес эндпоинта. Адреса сверены с backend/main.py.

import { apiRequest } from "./api";
import type {
  DailyNutritionSummary,
  GoalInput,
  GoalStatus,
  Intensity,
  LoginResponse,
  MealEntry,
  MealEntryInput,
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
  Ledger,
  LedgerCreateInput,
  UserHousehold,
  HouseholdInvite,
  HouseholdMember,
  HouseholdRole,
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

/** GET /users/me. Профиль владельца токена. */
export function getProfile(): Promise<UserProfile> {
  return apiRequest<UserProfile>("/users/me");
}

/** PATCH /users/{userId}. Сохраняет профиль; возвращает обновлённый профиль. */
export function updateProfile(userId: number, data: ProfileUpdateInput): Promise<UserProfile> {
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

/** PATCH .../workouts/{workoutId}. Фактическая интенсивность и заметки. */
export function updateWorkout(
  userId: number,
  sessionId: number,
  workoutId: number,
  changes: { actual_intensity?: Intensity | null; notes?: string | null },
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