/**
 * SWR 缓存键集中管理。
 *
 * 为什么要集中：添加一条记录后要同时失效「当日汇总」「7 天趋势」「记录列表」，
 * 键散落在各组件里就容易漏掉某个，导致界面数据不一致。
 */

export const SWR_GROUPS = {
  summary: "summary",
  summaryRange: "summary-range",
  entries: "entries",
  weights: "weights",
  foods: "foods",
  healthScore: "health-score",
  leaderboard: "leaderboard",
} as const;

export const swrKeys = {
  /** 当日汇总 */
  summary: (date: string) => [SWR_GROUPS.summary, date] as const,
  /** 区间趋势 */
  summaryRange: (from: string, to: string) =>
    [SWR_GROUPS.summaryRange, from, to] as const,
  /** 某天记录列表 */
  entries: (date: string) => [SWR_GROUPS.entries, date] as const,
  /** 体重记录 */
  weights: (from: string, to: string) => [SWR_GROUPS.weights, from, to] as const,
  /** 食物搜索结果 */
  foods: (keyword: string, page: number) =>
    [SWR_GROUPS.foods, keyword, page] as const,
  /** 某天的健康指数 */
  healthScore: (date: string) => [SWR_GROUPS.healthScore, date] as const,
  /** 排行榜（goal 为 null 表示全部） */
  leaderboard: (goal: string | null, limit: number) =>
    [SWR_GROUPS.leaderboard, goal ?? "all", limit] as const,
};

/**
 * 判断一个 SWR key 是否属于某个分组。
 *
 * 用法：mutate(isGroup(SWR_GROUPS.summary)) 一次性失效所有日期的汇总缓存。
 */
export function isGroup(group: string) {
  return (key: unknown): boolean =>
    Array.isArray(key) && key.length > 0 && key[0] === group;
}
