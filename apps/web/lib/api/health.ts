import { apiFetch } from "./client";

export type ScoreLevel = "excellent" | "good" | "fair" | "poor";

export interface HealthScoreOut {
  date: string;
  /** 0-100 */
  score: number;
  level: ScoreLevel;
  /** 未设目标时热量与宏量记 0，前端应引导设置目标 */
  has_goal: boolean;
  /** { heat: 40, macro: 30, habit: 22 }，分别对应各自的满分 */
  breakdown: {
    heat: number;
    macro: number;
    habit: number;
  };
  week_avg: number | null;
  scored_days: number;
  meals_logged: number;
  streak_days: number;
}

export interface LeaderboardEntry {
  rank: number;
  nickname: string;
  avatar_url: string | null;
  avg_score: number;
}

export interface LeaderboardMe {
  rank: number | null;
  avg_score: number | null;
  /** 是否满足进榜门槛（近 7 天记录 ≥ 3 天） */
  qualified: boolean;
  logged_days: number;
}

export interface LeaderboardOut {
  goal: string | null;
  date_from: string;
  date_to: string;
  items: LeaderboardEntry[];
  me: LeaderboardMe;
}

/** 各维度满分，ScoreBreakdown 用它算进度条比例 */
export const SCORE_MAX = {
  heat: 40,
  macro: 30,
  habit: 30,
} as const;

export const LEVEL_LABELS: Record<ScoreLevel, string> = {
  excellent: "优秀",
  good: "良好",
  fair: "一般",
  poor: "待改善",
};

/** 获取某天的健康指数。服务端会顺便计算并落库（幂等）。 */
export async function fetchHealthScore(date?: string): Promise<HealthScoreOut> {
  const query = date ? "?date=" + encodeURIComponent(date) : "";
  return apiFetch<HealthScoreOut>("health-score" + query);
}

export interface LeaderboardParams {
  goal?: string | null;
  limit?: number;
  days?: number;
}

export async function fetchLeaderboard(
  params: LeaderboardParams = {}
): Promise<LeaderboardOut> {
  const query = new URLSearchParams();
  if (params.goal) query.set("goal", params.goal);
  if (params.limit) query.set("limit", String(params.limit));
  if (params.days) query.set("days", String(params.days));
  const suffix = query.toString() ? "?" + query.toString() : "";
  return apiFetch<LeaderboardOut>("leaderboard" + suffix);
}
