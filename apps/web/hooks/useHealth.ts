"use client";

import useSWR from "swr";

import { fetchHealthScore, fetchLeaderboard } from "@/lib/api/health";
import type { HealthScoreOut, LeaderboardOut } from "@/lib/api/health";
import { swrKeys } from "@/lib/api/keys";

export interface UseOptions {
  /** 传 false 则不发请求（用于未激活的 Tab），SWR 会保持 data 为 undefined */
  enabled?: boolean;
}

/**
 * 某天的健康指数。
 *
 * 用 SWR 而不是手写 useEffect：切日期时能立刻拿到上次缓存，不闪空白。
 */
export function useHealthScore(date: string, options?: UseOptions) {
  const enabled = options?.enabled ?? true;

  const query = useSWR(
    enabled ? swrKeys.healthScore(date) : null,
    ([, d]) => fetchHealthScore(String(d))
  );

  return {
    score: (query.data ?? null) as HealthScoreOut | null,
    loading: enabled ? query.isLoading : false,
    error: query.error as Error | undefined,
    refresh: query.mutate,
  };
}

export interface UseLeaderboardResult {
  data: LeaderboardOut | null;
  loading: boolean;
  error: Error | undefined;
  refresh: () => void;
}

/**
 * 排行榜。
 *
 * `goal` 传 null 表示「全部」。切换目标时 SWR 按 key 分别缓存，
 * 来回切不需要重新请求（直接命中缓存，配合骨架屏只在首次出现）。
 */
export function useLeaderboard(
  goal: string | null,
  limit = 20,
  options?: UseOptions
): UseLeaderboardResult {
  const enabled = options?.enabled ?? true;

  const query = useSWR(
    enabled ? swrKeys.leaderboard(goal, limit) : null,
    ([, g, l]) =>
      fetchLeaderboard({
        // key 里用 "all" 代表全部，这里还原成 null，避免真的传 goal=all
        goal: g === "all" ? null : String(g),
        limit: Number(l),
      })
  );

  return {
    data: (query.data ?? null) as LeaderboardOut | null,
    loading: enabled ? query.isLoading : false,
    error: query.error as Error | undefined,
    refresh: () => {
      void query.mutate();
    },
  };
}
