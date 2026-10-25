import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { REFRESH_COOKIE } from "@/lib/auth/cookie";

/**
 * 根路径入口：有登录态去 /today，没有去 /login。
 *
 * 用 cookie 是否存在的**本地判断**，而不是去后端问「我登录了吗」：
 * 前者是内存里读一下，后者要在服务端发一次请求到 Render ——
 * 免费层实例 15 分钟无活动就休眠，那样每有人访问一次首页就唤醒一次，
 * 白等 30 秒冷启动，纯粹浪费。
 *
 * 代价：cookie 存在但已过期时，这里会先跳 /today。
 * 这是可接受的 —— /today 拉数据会拿到 401，那时再处理登录态。
 */
export default async function RootPage() {
  const cookieStore = await cookies();
  redirect(cookieStore.has(REFRESH_COOKIE) ? "/today" : "/login");
}
