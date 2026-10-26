// Единая точка обращения к backend (FastAPI): подставляет адрес сервера и токен
// и превращает ошибки в понятные сообщения на русском.

const API_URL = process.env.NEXT_PUBLIC_API_URL;

if (!API_URL) {
  throw new Error("Не задан NEXT_PUBLIC_API_URL в .env.local");
}

/** Ошибка запроса к API. Кроме текста хранит HTTP-код (0 — сервер недоступен). */
export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/** Превращает любую ошибку в текст для пользователя. */
export function getErrorText(error: unknown): string {
  return error instanceof Error ? error.message : "Неизвестная ошибка";
}

/** Удаляет токен и отправляет пользователя на страницу входа. */
export function logout(): void {
  sessionStorage.removeItem("access_token");
  window.location.assign("/login");
}

const CYRILLIC = /[А-Яа-яЁё]/;

/**
 * Формирует текст ошибки по коду ответа и телу ответа.
 * FastAPI кладёт описание в поле "detail": строка (наши сообщения)
 * или список ошибок проверки данных (422).
 * Пример: status 422, тело {"detail":[{"loc":["body","password"],"msg":"..."}]}
 * даёт "password: ...".
 */
function buildMessage(status: number, responseText: string, path: string): string {
  let detail: unknown = null;
  try {
    detail = JSON.parse(responseText).detail;
  } catch {
    detail = null;
  }

  if (status === 401) {
    return path === "/auth/login"
      ? "Неверный email или пароль."
      : "Сессия истекла. Войдите снова.";
  }

  if (status >= 500) {
    return "Ошибка сервера. Попробуйте позже.";
  }

  // Русские сообщения backend показываем как есть
  if (typeof detail === "string" && CYRILLIC.test(detail)) {
    return detail;
  }

  // Список ошибок проверки данных: "поле: сообщение"
  if (Array.isArray(detail)) {
    const parts = detail
      .map((item) => {
        if (typeof item !== "object" || item === null) return null;
        const { msg, loc } = item as { msg?: unknown; loc?: unknown };
        if (typeof msg !== "string") return null;
        const field = Array.isArray(loc) ? String(loc[loc.length - 1]) : "";
        return field ? `${field}: ${msg}` : msg;
      })
      .filter((part): part is string => part !== null);

    if (parts.length > 0) return parts.join("; ");
  }

  if (status === 403) return "Недостаточно прав для этого действия.";
  if (status === 404) return "Данные не найдены.";
  if (status === 409) return "Такая запись уже существует.";
  if (typeof detail === "string") return detail;

  return `Не удалось выполнить запрос (код ${status}).`;
}

/**
 * Выполняет запрос к backend и возвращает данные нужного типа T.
 *
 * Аргументы: path — например "/users/me"; options — метод, тело и т. п.
 * Токен берётся из sessionStorage и добавляется автоматически.
 * При ответе 401 (кроме запроса входа) токен удаляется, пользователь
 * отправляется на /login. Ошибки выбрасываются как ApiError.
 */
export async function apiRequest<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const token =
    typeof window !== "undefined" ? sessionStorage.getItem("access_token") : null;

  const headers = new Headers(options.headers);

  if (options.body !== undefined && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, { ...options, headers });
  } catch {
    // fetch выбрасывает ошибку, если сервер недоступен или запрос заблокирован
    throw new ApiError(
      0,
      "Не удаётся связаться с сервером. Проверьте, что backend запущен.",
    );
  }

  if (!response.ok) {
    const message = buildMessage(response.status, await response.text(), path);

    if (
      response.status === 401 &&
      path !== "/auth/login" &&
      typeof window !== "undefined"
    ) {
      logout();
    }

    throw new ApiError(response.status, message);
  }

  // 204 No Content: тела нет (например, после удаления)
  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}