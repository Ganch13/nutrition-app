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

const TOKEN_KEY = "access_token";

/** Сохраненный в этой вкладке access-токен (живёт 15 минут) или null. */
export function getAccessToken(): string | null {
  return typeof window !== "undefined" ? sessionStorage.getItem(TOKEN_KEY) : null;
}

/** Запоминает access-токен после входа, регистрации, обновления сессии или смены пароля. */
export function storeAccessToken(token: string): void {
  sessionStorage.setItem(TOKEN_KEY, token);
}

/**
 * Завершает сессию: просит сервер погасить её, убирает токен и открывает указанную страницу (по умолчанию вход).
 * Долгоживущая часть сессии лежит в HttpOnly-cookie, которую скрипт удалить не может, поэтому нужен запрос к серверу.
 * Если сервер недоступен, всё равно выходим (токен в этой вкладке удалён, сессия на сервере истечёт сама).
 * Пример: endSession("/login").
 */
export function endSession(redirectTo: string): void {
  sessionStorage.removeItem(TOKEN_KEY);

  let done = false;
  const finish = () => {
    if (done) return;
    done = true;
    window.location.assign(redirectTo);
  };
  // Не ждём сервер дольше 2 секунд: выход не должен зависать
  window.setTimeout(finish, 2000);
  fetch(`${API_URL}/auth/logout`, { method: "POST", credentials: "include" })
    .catch(() => undefined)
    .finally(finish);
}

/** Выход из аккаунта (кнопка «Выйти»): endSession со страницей входа. Подходит для onClick={logout}. */
export function logout(): void {
  endSession("/login");
}

/** Результат попытки продлить сессию: получили токен / сессии нет (нужен вход) / сервер недоступен. */
type RefreshResult = "ok" | "expired" | "unavailable";

// Идущий сейчас запрос на обновление: если несколько запросов страницы одновременно получили 401,
// обновление выполняется один раз, а остальные ждут его результата.
let refreshInFlight: Promise<RefreshResult> | null = null;

/**
 * Обменивает cookie сессии на новый access-токен (POST /auth/refresh) и сохраняет его.
 * Результат "expired" означает, что cookie нет или она недействительна: нужно войти заново.
 * Сетевая ошибка и ответы сервера 5xx/429 дают "unavailable": человека при этом не разлогиниваем.
 */
export function refreshSession(): Promise<RefreshResult> {
  if (refreshInFlight === null) {
    refreshInFlight = (async (): Promise<RefreshResult> => {
      try {
        const response = await fetch(`${API_URL}/auth/refresh`, {
          method: "POST",
          credentials: "include",
          // Без ограничения по времени плохая связь оставила бы приложение на экране загрузки навсегда
          signal: requestTimeout({}),
        });
        if (response.status === 401 || response.status === 403) return "expired";
        if (!response.ok) return "unavailable";
        const data: unknown = await response.json();
        const token =
          typeof data === "object" && data !== null
            ? (data as { access_token?: unknown }).access_token
            : undefined;
        if (typeof token !== "string") return "unavailable";
        storeAccessToken(token);
        return "ok";
      } catch {
        return "unavailable";
      } finally {
        refreshInFlight = null;
      }
    })();
  }
  return refreshInFlight;
}

/** Адреса, которые работают без входа или сами управляют сессией: для них токен не требуется и не обновляется. */
const SESSION_FREE_PATHS = ["/auth/login", "/auth/register", "/auth/refresh", "/auth/logout"];

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
 * Отправляет запрос к backend и возвращает «сырой» ответ Response.
 * Подставляет токен и превращает ошибки в ApiError. Если токена нет (новая вкладка) или он истёк (ответ 401),
 * один раз тихо продлевает сессию по cookie и повторяет запрос; если сессии нет, отправляет на страницу входа.
 * Её используют apiRequest (JSON) и apiBlob (файлы).
 */
async function sendRequest(
  path: string,
  options: RequestInit,
  alreadyRetried = false,
): Promise<Response> {
  const needsSession = !SESSION_FREE_PATHS.includes(path) && typeof window !== "undefined";

  // Токена в этой вкладке нет (вкладку открыли заново или перезапустили браузер): пробуем восстановить сессию
  if (needsSession && getAccessToken() === null) {
    const restored = await refreshSession();
    if (restored === "unavailable") throw serverUnavailable();
    if (restored === "expired") {
      logout();
      throw new ApiError(401, "Сессия истекла. Войдите снова.");
    }
  }

  const headers = new Headers(options.headers);

  if (options.body !== undefined && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const token = getAccessToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  let response: Response;
  try {
    // credentials: "include" нужен, чтобы браузер принимал и отправлял cookie сессии,
    // когда frontend и backend открыты на разных адресах (localhost:3000 и localhost:8000)
    response = await fetch(`${API_URL}${path}`, {
      ...options,
      headers,
      credentials: "include",
      signal: options.signal ?? requestTimeout(options),
    });
  } catch {
    // fetch выбрасывает ошибку, если сервер недоступен или запрос заблокирован
    throw serverUnavailable();
  }

  // Токен истёк: продлеваем сессию и повторяем запрос ровно один раз
  if (response.status === 401 && needsSession && !alreadyRetried) {
    const renewed = await refreshSession();
    if (renewed === "ok") return sendRequest(path, options, true);
    if (renewed === "unavailable") throw serverUnavailable();
  }

  if (!response.ok) {
    const message = buildMessage(response.status, await response.text(), path);

    if (response.status === 401 && needsSession) {
      logout();
    }

    throw new ApiError(response.status, message);
  }

  return response;
}

/** Тексты, когда ответа от сервера нет совсем (код 0). Их же показывает страница public/offline.html. */
export const NO_INTERNET_TEXT = "Нет подключения к интернету. Проверьте Wi-Fi или мобильную сеть.";
export const SERVER_DOWN_TEXT = "Сервер недоступен, попробуйте позже.";

/** Сколько ждать обычный ответ сервера и загрузку файла (фото), миллисекунды. */
const REQUEST_TIMEOUT_MS = 20_000;
const UPLOAD_TIMEOUT_MS = 120_000;

/**
 * Ошибка «ответа нет»: у устройства нет сети (navigator.onLine === false) — «Нет подключения к интернету»;
 * сеть есть, но сервер выключен, недоступен или не ответил вовремя — «Сервер недоступен, попробуйте позже».
 */
function serverUnavailable(): ApiError {
  const offline = typeof navigator !== "undefined" && navigator.onLine === false;
  return new ApiError(0, offline ? NO_INTERNET_TEXT : SERVER_DOWN_TEXT);
}

/**
 * Ограничение по времени для запроса: если сервер молчит дольше, запрос прерывается, и человек видит ошибку
 * с кнопкой «Повторить», а не бесконечную загрузку (так бывает на плохой мобильной связи и через VPN).
 * Загрузка файлов (фото) идёт дольше, поэтому ей даётся больше времени.
 * В старых браузерах без AbortSignal.timeout то же делается вручную через AbortController и таймер.
 */
function requestTimeout(options: RequestInit): AbortSignal | undefined {
  if (typeof AbortController === "undefined") return undefined;
  const isUpload = options.body instanceof Blob || options.body instanceof ArrayBuffer;
  const ms = isUpload ? UPLOAD_TIMEOUT_MS : REQUEST_TIMEOUT_MS;
  if (typeof AbortSignal.timeout === "function") return AbortSignal.timeout(ms);
  const controller = new AbortController();
  setTimeout(() => controller.abort(), ms);
  return controller.signal;
}

/**
 * Выполняет запрос к backend и возвращает данные нужного типа T.
 *
 * Аргументы: path — например "/users/me"; options — метод, тело и т. п.
 * Токен берётся из sessionStorage и добавляется автоматически; просроченный токен
 * обновляется незаметно (см. sendRequest). Если сессия закончилась, пользователь
 * отправляется на /login. Ошибки выбрасываются как ApiError.
 */
export async function apiRequest<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await sendRequest(path, options);

  // 204 No Content: тела нет (например, после удаления)
  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

/**
 * Скачивает файл (например, фото) с токеном и возвращает его как Blob.
 * Нужна, потому что <img src> не умеет отправлять заголовок Authorization.
 * Пример: apiBlob("/users/1/progress-photos/3/file") → Blob image/jpeg.
 */
export async function apiBlob(path: string): Promise<Blob> {
  const response = await sendRequest(path, {});
  return response.blob();
}
