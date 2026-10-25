"use client";

import { LEVEL_LABELS } from "@/lib/api/health";
import type { ScoreLevel } from "@/lib/api/health";

/**
 * 分数配色（严格按 SPEC）：
 *   < 40   红
 *   40~69 黄
 *   >= 70  绿
 */
function scoreColor(score: number): string {
  if (score < 40) return "#E24B4A";
  if (score < 70) return "#EF9F27";
  return "#639922";
}

export interface HealthScoreGaugeProps {
  /** 0-100 */
  score: number;
  level?: ScoreLevel;
  /** 本周平均分，展示在大数字下方；没有则不显示 */
  weekAvg?: number | null;
  /** 宽度 px，高度按半圆比例推算 */
  size?: number;
}

/**
 * 半环形健康指数仪表盘。
 *
 * 用原生 SVG 而非图表库：只有一段圆弧，引入 Recharts 反而更重，
 * 且手写 SVG 对无障碍（role="img" + aria-label）更友好。
 */
export function HealthScoreGauge({
  score,
  level,
  weekAvg,
  size = 220,
}: HealthScoreGaugeProps) {
  const clamped = Math.max(0, Math.min(100, score));
  const color = scoreColor(clamped);

  // 圆心在底边中点，只画上半圆
  const width = size;
  const height = size / 2 + 18;
  const cx = width / 2;
  const cy = size / 2 + 8;
  const radius = size / 2 - 14;
  const strokeWidth = 16;

  // 半圆弧长 = π × r
  const arcLength = Math.PI * radius;
  const offset = arcLength * (1 - clamped / 100);

  const levelLabel = level ? LEVEL_LABELS[level] : "";

  return (
    <div
      className="relative flex flex-col items-center"
      style={{ width }}
      role="img"
      aria-label={`今日健康指数 ${clamped} 分，${levelLabel}`}
    >
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
        {/* 底槽 */}
        <path
          d={`M ${cx - radius} ${cy} A ${radius} ${radius} 0 0 1 ${cx + radius} ${cy}`}
          fill="none"
          stroke="#EDEBE6"
          strokeWidth={strokeWidth}
          strokeLinecap="round"
        />
        {/* 进度弧 */}
        <path
          d={`M ${cx - radius} ${cy} A ${radius} ${radius} 0 0 1 ${cx + radius} ${cy}`}
          fill="none"
          stroke={color}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={arcLength}
          strokeDashoffset={offset}
        />
      </svg>

      {/* 中间的数字，绝对定位到半圆圆心上方 */}
      <div
        className="absolute flex flex-col items-center"
        style={{ bottom: 18 }}
      >
        <span
          className="font-medium leading-none tabular-nums"
          style={{ fontSize: size * 0.22, color }}
        >
          {clamped}
        </span>
        <span className="mt-1 text-[13px] text-black/45">满分 100</span>
      </div>

      {levelLabel && (
        <span
          className="mt-1 rounded-full px-3 py-1 text-[13px] font-medium"
          style={{ backgroundColor: color + "1A", color }}
        >
          {levelLabel}
        </span>
      )}

      {weekAvg !== undefined && weekAvg !== null && (
        <p className="mt-2 text-[13px] text-black/45 tabular-nums">
          本周平均 {weekAvg.toFixed(1)} 分
        </p>
      )}
    </div>
  );
}
