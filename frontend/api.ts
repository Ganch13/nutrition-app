
const API_URL = process.env.NEXT_PUBLIC_API_URL;

if (!API_URL) {
  throw new Error("Не задан NEXT_PUBLIC_API_URL в .env.local");
}

function getErrorMessage(
  status: number,
  responseText: string,
): string {
  let detail: unknown;

  try {
    const body = JSON.parse(responseText);
    detail = body.detail;
  } catch {
    detail = responseText;
  }

  if (typeof detail === "string") {
    if (status === 401) {
      return "Неверный email или пароль либо требуется войти заново.";
    }

    if (status === 403) {
      return "У вас недостаточно прав для этого действия.";
    }

    if (status === 404) {
      return "Запрашиваемые данные не найдены.";
    }

    if (status >= 500) {
      return "Ошибка сервера. Попробуйте позже.";
    }

    return detail;
  }

  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (
          typeof item === "object" &&
          item !== null &&
          "msg" in item &&
          typeof item.msg === "string"
        ) {
          return item.msg;
        }

        return null;
      })
      .filter((message): message is string => message !== null);

    if (messages.length > 0) {
      return messages.join(" ");
    }
  }

  if (status === 401) {
    return "Необходимо войти в приложение.";
  }

  if (status === 403) {
    return "У вас недостаточно прав для этого действия.";
  }

  if (status === 404) {
    return "Запрашиваемые данные не найдены.";
  }

  if (status >= 500) {
    return "Ошибка сервера. Попробуйте позже.";
  }

  return `Не удалось выполнить запрос (HTTP ${status}).`;
}

export async function apiRequest<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const token =
    typeof window !== "undefined"
      ? sessionStorage.getItem("access_token")
      : null;

  const headers = new Headers(options.headers);

  if (
    options.body !== undefined &&
    !headers.has("Content-Type")
  ) {
    headers.set("Content-Type", "application/json");
  }

  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    const errorText = await response.text();

    if (
      response.status === 401 &&
      path !== "/auth/login" &&
      typeof window !== "undefined"
    ) {
      sessionStorage.removeItem("access_token");
      window.location.assign("/login");
    }

    throw new Error(
      getErrorMessage(response.status, errorText),
    );
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}
