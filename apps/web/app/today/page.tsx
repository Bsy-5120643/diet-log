"use client";

import useSWR from "swr";

import { FoodSearchPanel } from "@/components/food/FoodSearchPanel";
import { TodaySummaryCard } from "@/components/dashboard/TodaySummaryCard";
import { EmptyState } from "@/components/dashboard/EmptyState";
import { useDashboard } from "@/hooks/useDashboard";
import { deleteFoodEntry, fetchFoodEntries } from "@/lib/api/endpoints";
import { swrKeys } from "@/lib/api/keys";

export default function TodayPage() {
  const {
    date,
    summary,
    loading,
    error,
    goPrevDay,
    goNextDay,
    canGoNextDay,
    refreshAll,
  } = useDashboard();

  const entriesQuery = useSWR(swrKeys.entries(date), ([, d]) =>
    fetchFoodEntries(String(d))
  );
  const entries = entriesQuery.data?.items ?? [];

  async function handleAdded() {
    // 一次性失效汇总 / 趋势 / 记录列表，三处同时无刷新更新
    await refreshAll();
  }

  async function handleDelete(id: string) {
    await deleteFoodEntry(id);
    await refreshAll();
  }

  return (
    <main className="mx-auto w-full max-w-[1080px] px-4 py-6 sm:px-6 sm:py-8">
      <h1 className="text-[24px] font-medium tracking-tight">今日记录</h1>
      <p className="mt-1 text-[14px] text-black/50">搜索食物并添加到对应餐次</p>

      <div className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="space-y-4">
          <FoodSearchPanel date={date} onAdded={handleAdded} />

          <section className="rounded-xl border border-black/[0.08] bg-white p-5">
            <h2 className="text-[15px] font-medium">今日明细</h2>
            {entries.length === 0 ? (
              <EmptyState
                title="今天还没有记录"
                description="在上面搜索食物，添加后会实时计入右侧看板。"
              />
            ) : (
              <ul className="mt-3 divide-y divide-black/[0.06]">
                {entries.map((entry) => (
                  <li
                    key={entry.id}
                    className="flex items-center justify-between gap-3 py-2.5"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-[14px]">{entry.food_name}</p>
                      <p className="text-[12px] tabular-nums text-black/45">
                        {entry.meal_label} · {entry.quantity_g.toFixed(0)} g ·{" "}
                        {entry.energy_kcal.toFixed(0)} kcal
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => handleDelete(entry.id)}
                      className="shrink-0 text-[13px] text-black/35 hover:text-red-600"
                    >
                      删除
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>

        <div>
          <TodaySummaryCard
            date={date}
            summary={summary}
            loading={loading}
            onPrevDay={goPrevDay}
            onNextDay={goNextDay}
            canGoNext={canGoNextDay}
          />
          {error && (
            <p className="mt-3 rounded-lg bg-red-50 px-4 py-3 text-[14px] text-red-700">
              {error}
            </p>
          )}
        </div>
      </div>
    </main>
  );
}
