"use client";

import Link from "next/link";
import { useState } from "react";

import { CalorieTrendChart } from "@/components/dashboard/CalorieTrendChart";
import { TodaySummaryCard } from "@/components/dashboard/TodaySummaryCard";
import { TrendCard } from "@/components/dashboard/TrendCard";
import { WeightQuickAdd } from "@/components/dashboard/WeightQuickAdd";
import { WeightTrendChart } from "@/components/dashboard/WeightTrendChart";
import { HealthScoreGauge } from "@/components/health/HealthScoreGauge";
import { LeaderboardList } from "@/components/health/LeaderboardList";
import { ScoreBreakdown } from "@/components/health/ScoreBreakdown";
import { useDashboard } from "@/hooks/useDashboard";
import { useHealthScore, useLeaderboard } from "@/hooks/useHealth";
import { createWeightLog } from "@/lib/api/endpoints";

const TABS = [
  { value: "overview", label: "看板" },
  { value: "review", label: "复盘" },
  { value: "leaderboard", label: "排行榜" },
] as const;

type TabValue = (typeof TABS)[number]["value"];

export default function DashboardPage() {
  const {
    date,
    summary,
    trend,
    weights,
    loading,
    error,
    todayWeight,
    goPrevDay,
    goNextDay,
    canGoNextDay,
    refreshAll,
  } = useDashboard();

  const [tab, setTab] = useState<TabValue>("overview");
  const [goal, setGoal] = useState<string | null>(null);

  // 只有切到对应 Tab 才发请求，避免打开页面就打三四个接口
  const health = useHealthScore(date, { enabled: tab === "review" });
  const board = useLeaderboard(goal, 20, { enabled: tab === "leaderboard" });

  async function handleWeightSubmit(payload: {
    weight_kg: number;
    logged_on: string;
  }) {
    await createWeightLog(payload);
    await refreshAll();
  }

  const trendDays = trend?.days ?? [];
  const weightLogs = weights?.logs ?? [];
  const hasAnyEntry = trendDays.some((day) => day.entry_count > 0);
  const hasAnyWeight = weightLogs.length > 0;

  return (
    <main className="mx-auto w-full max-w-[1080px] px-4 py-6 sm:px-6 sm:py-8">
      <header className="mb-5">
        <h1 className="text-[24px] font-medium tracking-tight">数据看板</h1>
        <p className="mt-1 text-[14px] text-black/50">
          摄入趋势、健康指数与榜单
        </p>
      </header>

      <nav className="mb-6 flex gap-2 border-b border-black/[0.08]">
        {TABS.map((item) => {
          const active = tab === item.value;
          return (
            <button
              key={item.value}
              type="button"
              onClick={() => setTab(item.value)}
              className={
                "-mb-px border-b-2 px-3 pb-2.5 text-[14px] " +
                (active
                  ? "border-black font-medium text-black"
                  : "border-transparent text-black/45 hover:text-black/70")
              }
            >
              {item.label}
            </button>
          );
        })}
      </nav>

      {tab === "overview" && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <TodaySummaryCard
            date={date}
            summary={summary}
            loading={loading}
            onPrevDay={goPrevDay}
            onNextDay={goNextDay}
            canGoNext={canGoNextDay}
          />

          <TrendCard
            title="近 7 天热量"
            description="每日摄入热量与目标线对比"
            isEmpty={!hasAnyEntry}
            loading={loading}
            emptyHint="记录几餐之后，这里会出现你的摄入趋势。"
            emptyActionLabel="去记录饮食"
            emptyActionHref="/today"
          >
            <CalorieTrendChart
              data={trendDays.map((day) => ({
                date: day.date,
                energy_kcal: day.energy_kcal,
              }))}
              targetKcal={trendDays[0]?.target_kcal ?? null}
            />
          </TrendCard>

          <TrendCard
            title="近 7 天体重"
            description="同一天重复记录会覆盖"
            isEmpty={!hasAnyWeight}
            loading={loading}
            emptyHint="记录第一次体重后，这里会出现你的体重变化曲线。"
          >
            <WeightTrendChart
              data={weightLogs.map((log) => ({
                date: log.logged_on,
                weight_kg: log.weight_kg,
              }))}
            />
            <div className="mt-4">
              <WeightQuickAdd
                date={date}
                currentWeight={todayWeight}
                onSubmit={handleWeightSubmit}
              />
            </div>
          </TrendCard>
        </div>
      )}

      {tab === "review" && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <section className="rounded-xl border border-black/[0.08] bg-white p-5">
            <h2 className="text-[15px] font-medium">今日健康指数</h2>
            <p className="mt-0.5 text-[13px] text-black/45">{date}</p>

            {health.loading || !health.score ? (
              <div className="flex flex-col items-center gap-3 py-8">
                <div
                  className="animate-pulse rounded-full bg-black/[0.04]"
                  style={{ width: 220, height: 118 }}
                />
                <div className="h-4 w-24 animate-pulse rounded bg-black/[0.04]" />
              </div>
            ) : (
              <div className="mt-4 flex flex-col items-center">
                <HealthScoreGauge
                  score={health.score.score}
                  level={health.score.level}
                  weekAvg={health.score.week_avg}
                />
              </div>
            )}
          </section>

          <section className="rounded-xl border border-black/[0.08] bg-white p-5">
            <h2 className="text-[15px] font-medium">得分构成</h2>
            <p className="mt-0.5 text-[13px] text-black/45">
              满分 100 = 热量 40 + 宏量 30 + 记录习惯 30
            </p>

            <div className="mt-4">
              {health.loading || !health.score ? (
                <div className="space-y-4">
                  {[0, 1, 2].map((i) => (
                    <div key={i} className="space-y-1.5">
                      <div className="h-4 w-32 animate-pulse rounded bg-black/[0.04]" />
                      <div className="h-2 w-full animate-pulse rounded-full bg-black/[0.04]" />
                    </div>
                  ))}
                </div>
              ) : (
                <ScoreBreakdown breakdown={health.score.breakdown} />
              )}
            </div>

            {health.score && !health.score.has_goal && (
              <div className="mt-5 rounded-lg bg-amber-50 px-4 py-3">
                <p className="text-[13px] text-black/70">
                  还没有设置每日目标，热量与宏量两项暂时无法评分。
                </p>
                <Link
                  href="/settings/goals"
                  className="mt-1 inline-block text-[13px] font-medium text-black underline"
                >
                  去设置目标以获取更多得分
                </Link>
              </div>
            )}

            {health.score && (
              <dl className="mt-5 grid grid-cols-2 gap-3 border-t border-black/[0.06] pt-4">
                <div>
                  <dt className="text-[12px] text-black/45">记录餐次</dt>
                  <dd className="text-[16px] font-medium tabular-nums">
                    {health.score.meals_logged}
                  </dd>
                </div>
                <div>
                  <dt className="text-[12px] text-black/45">连续打卡</dt>
                  <dd className="text-[16px] font-medium tabular-nums">
                    {health.score.streak_days} 天
                  </dd>
                </div>
              </dl>
            )}
          </section>
        </div>
      )}

      {tab === "leaderboard" && (
        <section className="rounded-xl border border-black/[0.08] bg-white p-5">
          <h2 className="text-[15px] font-medium">健康指数排行榜</h2>
          <p className="mt-0.5 text-[13px] text-black/45">
            近 7 天平均得分排名，记录满 3 天才会进榜
          </p>

          <div className="mt-4">
            {board.loading || !board.data ? (
              <div className="space-y-2">
                {[0, 1, 2, 3, 4].map((i) => (
                  <div
                    key={i}
                    className="h-14 w-full animate-pulse rounded-lg bg-black/[0.04]"
                  />
                ))}
              </div>
            ) : (
              <LeaderboardList
                items={board.data.items}
                me={board.data.me}
                goal={goal}
                onGoalChange={setGoal}
                loading={board.loading}
              />
            )}
          </div>
        </section>
      )}

      {error && (
        <p className="mt-4 rounded-lg bg-red-50 px-4 py-3 text-[14px] text-red-700">
          {error}
        </p>
      )}
    </main>
  );
}
