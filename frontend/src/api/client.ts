const API_BASE = "/api";
let novelVideoSession: Promise<void> | undefined;

async function ensureNovelVideoSession(): Promise<void> {
  if (!novelVideoSession) {
    novelVideoSession = fetch(`${API_BASE}/core/novel-video/session`, {
      method: "POST",
      credentials: "same-origin",
    }).then((response) => {
      if (!response.ok) throw new Error("Novel-video local proxy session was refused.");
    }).catch((error) => {
      novelVideoSession = undefined;
      throw error;
    });
  }
  return novelVideoSession;
}

function isHtml(value: string): boolean {
  return /^\s*</.test(value) || /<html[\s>]/i.test(value);
}

function messageFor(status: number, detail: unknown): string {
  if (status >= 500) return "服务暂时不可用，请稍后重试";
  if (status === 401 || status === 403) return "当前操作没有权限";
  if (status === 404) return "请求的内容不存在";
  if (status === 422) {
    return typeof detail === "string" && detail.trim() && !isHtml(detail)
      ? detail
      : "提交的数据格式不正确";
  }
  if (typeof detail === "string" && detail.trim() && !isHtml(detail)) {
    return detail;
  }
  return `请求失败（状态码 ${status}）`;
}

export class ApiError extends Error {
  readonly status: number;
  readonly detail: unknown;

  constructor(status: number, detail: unknown) {
    super(messageFor(status, detail));
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

function isJsonBody(body: BodyInit | null | undefined): boolean {
  if (typeof body !== "string") return false;
  try {
    JSON.parse(body);
    return true;
  } catch {
    return false;
  }
}

async function errorDetail(response: Response): Promise<unknown> {
  const body = await response.text();
  if (!body) return undefined;
  try {
    const parsed: unknown = JSON.parse(body);
    if (parsed && typeof parsed === "object" && "detail" in parsed) {
      return (parsed as { detail: unknown }).detail;
    }
    return parsed;
  } catch {
    return body;
  }
}

function isExpiredNovelVideoSession(detail: unknown): boolean {
  if (!detail || typeof detail !== "object" || !("code" in detail)) return false;
  const code = (detail as { code?: unknown }).code;
  return code === "session_required" || code === "session_expired";
}

export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const isNovelVideoRequest = path.startsWith("/core/novel-video");
  if (isNovelVideoRequest) {
    await ensureNovelVideoSession();
  }
  const headers = new Headers(options.headers);
  if (isJsonBody(options.body) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  for (let attempt = 0; attempt < 2; attempt += 1) {
    const response = await fetch(`${API_BASE}${path}`, { ...options, headers });
    if (!response.ok) {
      const detail = await errorDetail(response);
      if (isNovelVideoRequest && response.status === 403 && isExpiredNovelVideoSession(detail)) {
        novelVideoSession = undefined;
        if (attempt === 0) {
          await ensureNovelVideoSession();
          continue;
        }
      }
      throw new ApiError(response.status, detail);
    }
    if (response.status === 204) return undefined as T;
    return response.json() as Promise<T>;
  }
  throw new Error("Novel-video request retry limit was exceeded.");
}

export function userMessage(error: unknown): string {
  if (error instanceof ApiError) return messageFor(error.status, error.detail);
  if (error instanceof TypeError) {
    return "无法连接本地服务，请检查后端是否运行";
  }
  if (error instanceof Error) return error.message;
  return "发生未知错误";
}
