"use client";

/**
 * 前端请求层。
 *
 * 所有请求都打向自己的 /api/*，由 BFF 代理转发到 Render 上的 FastAPI。
 * 这样做的原因：Vercel 与 Render 不同站，后端直接 Set-Cookie 会被
 * 浏览器当第三方 Cookie 拦掉。
 *
 * Token 分工：
 * - access token：存在模块变量（内存）里，刷新页面即失效，XSS 也拿不走持久化凭证
 * - refresh token：httpOnly Cookie，前端 JS 完全读不到，只由 BFF 使用
 */

let accessToken: string | null = null;

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

export function getAccessToken(): string | null {
  return accessToken;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

function buildHeaders(init: RequestInit, withAuth: boolean): Headers {
  const headers = new Headers(init.headers);
  if (withAuth && accessToken) {
    headers.set("Authorization", `Bearer ${accessToken}`);
  }
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  return headers;
}

async function toApiError(res: Response): Promise<ApiError> {
  let code = "unknown_error";
  let message = "请求失败，请稍后重试";

  try {
    const data = (await res.json()) as {
      detail?: string | { code?: string; message?: string };
    };
    if (typeof data.detail === "string") {
      message = data.detail;
    } else if (data.detail) {
      code = data.detail.code ?? code;
      message = data.detail.message ?? message;
    }
  } catch {
    // body 不是 JSON，用默认文案
  }

  return new ApiError(res.status, code, message);
}

async function readCode(res: Response): Promise<string> {
  try {
    const data = (await res.clone().json()) as { detail?: { code?: string } };
    return data.detail?.code ?? "";
  } catch {
    return "";
  }
}

async function tryRefresh(): Promise<boolean> {
  const res = await fetch("/api/auth/refresh", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  if (!res.ok) return false;

  const data = (await res.json()) as { access_token: string };
  accessToken = data.access_token;
  return true;
}

export async function apiFetch<T>(
  path: string,
  init: RequestInit = {},
  options: { auth?: boolean } = {}
): Promise<T> {
  const withAuth = options.auth !== false;

  const send = () =>
    fetch(`/api/${path}`, { ...init, headers: buildHeaders(init, withAuth) });

  let res = await send();

  // 只有明确是 access token 过期才刷新；别的一律 401 直接抛
  if (res.status === 401 && withAuth) {
    const code = await readCode(res);
    if (code === "token_expired" && (await tryRefresh())) {
      res = await send();
    }
  }

  if (!res.ok) throw await toApiError(res);
  if (res.status === 204) return undefined as T;

  return (await res.json()) as T;
}
