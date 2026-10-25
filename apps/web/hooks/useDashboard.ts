"use client";

import { useCallback, useState } from "react";
import useSWR, { useSWRConfig } from "swr";

import { ApiError } from "@/lib/api/client";
import {
  fetchDailySummary,
  fetchSummaryRange,
  fetchWeightLogs,
} from "@/lib/api/endpoints";
import type {
  DailySummaryOut,
  SummaryRangeOut,
  WeightLogListOut,
} from "@/lib/api/endpoints";
import { SWR_GROUPS, isGroup, swrKeys } from "@/lib/api/keys";
import { shiftDate, toISODate } from "@/lib/date";

const RANGE_DAYS = 7;

export interface UseDashboardResult {
  date: string;
  summary: DailySummaryOut | null;
  trend: SummaryRangeOut | null;
  weights: WeightLogListOut | null;
  loading: boolean;
  error: string | null;
  todayWeight: number | null;
  goPrevDay: () => void;
  goNextDay: () => void;
  setDate: (date: string) => void;
  canGoNextDay: boolean;
  /** 添加/删除记录后调用，让看板无刷新更新 */
  refreshAll: () => Promise<void>;
}

/**
 * 看板数据源。
 *
 * 用 SWR 而不是手写 useEffect：
 * - 组件重新挂载时能拿到缓存，不闪空白
 * - refreshAll() 可一次性失效所有相关 key，保证看板与记录列表同步
 */
export function useDashboard(initialDate?: string): UseDashboardResult {
  const [date, setDate] = useState(() => initialDate ?? toISODate());
  const { mutate } = useSWRConfig();

  const from = shiftDate(date, -(RANGE_DAYS - 1));

  const summaryQuery = useSWR(swrKeys.summary(date), ([, d]) =>
    fetchDailySummary(String(d))
  );
  const trendQuery = useSWR(swrKeys.summaryRange(from, date), ([, f, t]) =>
    fetchSummaryRange(String(f), String(t))
  );
  const weightsQuery = useSWR(swrKeys.weights(from, date), ([, f, t]) =>
    fetchWeightLogs(String(f), String(t))
  );

  const loading =
    summaryQuery.isLoading || trendQuery.isLoading || weightsQuery.isLoading;

  // 目标未设置不是错误，按空态渲染；其余才展示
  const error = normalizeError(
    summaryQuery.error ?? trendQuery.error ?? weightsQuery.error
  );

  const todayWeight =
    weightsQuery.data?.logs.find((log) => log.logged_on === date)?.weight_kg ??
    null;

  const today = toISODate();

  const refreshAll = useCallback(async () => {
    await Promise.all([
      mutate(isGroup(SWR_GROUPS.summary)),
      mutate(isGroup(SWR_GROUPS.summaryRange)),
      mutate(isGroup(SWR_GROUPS.entries)),
    ]);
  }, [mutate]);

  return {
    date,
    summary: summaryQuery.data ?? null,
    trend: trendQuery.data ?? null,
    weights: weightsQuery.data ?? null,
    loading,
    error,
    todayWeight,
    goPrevDay: () => setDate(shiftDate(date, -1)),
    goNextDay: () => setDate(shiftDate(date, 1)),
    setDate,
    canGoNextDay: date < today,
    refreshAll,
  };
}

function normalizeError(err: unknown): string | null {
  if (!err) return null;
  if (err instanceof ApiError && err.code === "goal_not_set") return null;
  return err instanceof Error ? err.message : "加载失败";
}
