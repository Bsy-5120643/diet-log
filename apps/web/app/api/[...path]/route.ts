import { NextRequest, NextResponse } from "next/server";

import { REFRESH_COOKIE } from "@/lib/auth/cookie";

/**
 * BFF 代理：把前端请求转发到 Render 上的 FastAPI。
 *
 * 存在的意义有两个：
 * 1. Cookie 落在前端自己的域上 —— Vercel 与 Render 不同站，
 *    后端直接 Set-Cookie 会被浏览器当第三方 Cookie 拦掉
 * 2. 后端地址不暴露给浏览器
 *
 * Token 处理：
 * - refresh token 由本文件写入/读取 httpOnly Cookie，前端 JS 永远拿不到
 * - access token 由前端自己存在内存里（见 lib/api/client.ts）
 */

const BACKEND_API_URL = process.env.BACKEND_API_URL ?? "http://localhost:8000";
const REFRESH_MAX_AGE = 30 * 24 * 60 * 60; // 30 天

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

interface RouteContext {
  params: Promise<{ path: string[] }>;
}

async function handle(req: NextRequest, ctx: RouteContext) {
  const { path } = await ctx.params;
  const segments = Array.isArray(path) ? path.join("/") : "";
  const target = `${BACKEND_API_URL}/api/v1/${segments}${req.nextUrl.search}`;

  const method = req.method.toUpperCase();
  const hasBody = !["GET", "HEAD"].includes(method);
  let body: string | undefined = hasBody ? await req.text() : undefined;

  // refresh / logout 的凭证来自 Cookie，前端无从也无需提供
  if (segments === "auth/refresh" || segments === "auth/logout") {
    const refreshToken = req.cookies.get(REFRESH_COOKIE)?.value ?? "";
    body = JSON.stringify({ refresh_token: refreshToken });
  }

  const headers = new Headers();
  const incomingAuth = req.headers.get("authorization");
  if (incomingAuth) headers.set("Authorization", incomingAuth);
  const contentType = req.headers.get("content-type");
  if (contentType) headers.set("Content-Type", contentType);

  let upstream: Response;
  try {
    upstream = await fetch(target, { method, headers, body, redirect: "manual" });
  } catch {
    return NextResponse.json(
      { detail: { code: "backend_unreachable", message: "服务暂时不可用" } },
      { status: 502 }
    );
  }

  const isAuthExchange =
    segments === "auth/login" ||
    segments === "auth/register" ||
    segments === "auth/refresh";

  // 登录类响应：把 refresh token 摘出来存 Cookie，只把 access token 回给前端
  if (isAuthExchange && upstream.ok) {
    const data = (await upstream.json()) as {
      user: unknown;
      tokens: { access_token: string; refresh_token?: string; token_type: string; expires_in: number };
    };
    const refreshToken = data.tokens.refresh_token;

    const res = NextResponse.json({
      user: data.user,
      tokens: {
        access_token: data.tokens.access_token,
        token_type: data.tokens.token_type,
        expires_in: data.tokens.expires_in,
      },
    });

    if (refreshToken) {
      res.cookies.set(REFRESH_COOKIE, refreshToken, cookieOptions());
    }
    return res;
  }

  // 登出：清掉 Cookie
  if (segments === "auth/logout") {
    const res = new NextResponse(null, { status: upstream.status });
    res.cookies.set(REFRESH_COOKIE, "", { ...cookieOptions(), maxAge: 0 });
    return res;
  }

  const contentTypeOut = upstream.headers.get("content-type");
  const payload = upstream.status === 204 ? null : await upstream.text();

  return new NextResponse(payload, {
    status: upstream.status,
    headers: contentTypeOut ? { "Content-Type": contentTypeOut } : undefined,
  });
}

function cookieOptions() {
  return {
    httpOnly: true,
    sameSite: "lax" as const,
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: REFRESH_MAX_AGE,
  };
}

export const GET = handle;
export const POST = handle;
export const PUT = handle;
export const PATCH = handle;
export const DELETE = handle;
