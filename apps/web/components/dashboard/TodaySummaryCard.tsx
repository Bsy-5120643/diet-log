"use client";

import { CalorieRing } from "./CalorieRing";
import { MacroBarList } from "./MacroBarList";
import type { DailySummaryOut } from "@/lib/api/endpoints";

export interface TodaySummaryCardProps {
  date: string;
  summary: DailySummaryOut | null;
  loading?: boolean;
  onPrevDay: () => void;
  onNextDay: () => void;
  canGoNext: boolean;
}

export function TodaySummaryCard({
  date,
  summary,
  loading = false,
  onPrevDay,
  onNextDay,
  canGoNext,
}: TodaySummaryCardProps) {
  return (
    <section className="rounded-xl border border-black/[0.08] bg-white p-5">
      <header className="mb-5 flex items-center justify-between">
        <div>
          <h2 className="text-[15px] font-medium">今日摄入</h2>
          <p className="mt-0.5 text-[13px] text-black/45">{date}</p>
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={onPrevDay}
            aria-label="前一天"
            className="rounded-md border border-black/15 px-2 py-1 text-[13px] hover:bg-black/[0.04]"
          >
            ‹
          </button>
          <button
            type="button"
            onClick={onNextDay}
            disabled={!canGoNext}
            aria-label="后一天"
            className="rounded-md border border-black/15 px-2 py-1 text-[13px] hover:bg-black/[0.04] disabled:opacity-30"
          >
            ›
          </button>
        </div>
      </header>

      {loading || !summary ? (
        <div className="mx-auto h-[168px] w-full animate-pulse rounded-full bg-black/[0.04]" />
      ) : (
        <div className="flex flex-col items-center gap-6 sm:flex-row sm:items-center sm:gap-8">
          <CalorieRing
            consumed={summary.consumed.energy_kcal}
            target={summary.targets ? summary.targets.energy_kcal : null}
          />
          <div className="w-full flex-1">
            <MacroBarList
              consumed={summary.consumed}
              targets={summary.targets}
              incompleteFields={summary.incomplete_fields}
            />
          </div>
        </div>
      )}
    </section>
  );
}
