"use client";

import { SCORE_MAX } from "@/lib/api/health";

/**
 * 按「拿到分 / 该项满分」的比例配色。
 *
 * 用比例而不是绝对值：热量满分 40、习惯满分 30，
 * 拿 24 分在两项里的含金量完全不同，用绝对值会误导。
 */
function ratioColor(ratio: number): string {
  if (ratio >= 0.8) return "#639922";
  if (ratio >= 0.5) return "#EF9F27";
  return "#E24B4A";
}

const ITEMS: {
  key: "heat" | "macro" | "habit";
  label: string;
  max: number;
  hint: string;
}[] = [
  { key: "heat", label: "热量达标", max: SCORE_MAX.heat, hint: "接近目标得分高，低于基础代谢记 0" },
  { key: "macro", label: "宏量营养素", max: SCORE_MAX.macro, hint: "蛋白质 / 碳水 / 脂肪各占 10 分" },
  { key: "habit", label: "记录习惯", max: SCORE_MAX.habit, hint: "三餐 15 分 + 连续打卡 15 分" },
];

export interface ScoreBreakdownProps {
  breakdown: {
    heat: number;
    macro: number;
    habit: number;
  };
}

/** 三个维度的得分条。宽度与颜色都随得分动态变化。 */
export function ScoreBreakdown({ breakdown }: ScoreBreakdownProps) {
  return (
    <div className="space-y-4">
      {ITEMS.map((item) => {
        const got = breakdown[item.key] ?? 0;
        const ratio = item.max > 0 ? Math.min(1, got / item.max) : 0;
        const color = ratioColor(ratio);

        return (
          <div key={item.key}>
            <div className="mb-1.5 flex items-baseline justify-between">
              <span className="text-[14px]">{item.label}</span>
              <span className="text-[13px] tabular-nums text-black/50">
                <span className="font-medium" style={{ color }}>
                  {got.toFixed(1)}
                </span>
                {" / "}
                {item.max}
              </span>
            </div>

            <div className="h-2 overflow-hidden rounded-full bg-black/[0.07]">
              <div
                className="h-full rounded-full transition-[width] duration-300"
                style={{
                  width: `${Math.round(ratio * 100)}%`,
                  backgroundColor: color,
                }}
              />
            </div>

            <p className="mt-1 text-[12px] text-black/35">{item.hint}</p>
          </div>
        );
      })}
    </div>
  );
}
