"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { MacroValues } from "@/lib/api/endpoints";

export interface CaloriePoint {
  date: string;
  energy_kcal: number;
}

export interface CalorieTrendChartProps {
  data: CaloriePoint[];
  /** 目标线，null 时不画 */
  targetKcal?: number | null;
  height?: number;
}

/** YYYY-MM-DD -> M/D，用于 x 轴刻度 */
function formatDay(iso: string): string {
  const parts = iso.split("-");
  return parts[1] + "/" + parts[2];
}

/** 移动端隐藏部分刻度，避免挤成一团 */
function tickInterval(count: number): number {
  return count > 7 ? 1 : 0;
}

export function CalorieTrendChart({
  data,
  targetKcal = null,
  height = 200,
}: CalorieTrendChartProps) {
  return (
    <div className="w-full" style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 12, left: -16, bottom: 0 }}>
          <CartesianGrid stroke="#E8E6E1" strokeDasharray="3 3" vertical={false} />
          <XAxis
            dataKey="date"
            tickFormatter={formatDay}
            interval={tickInterval(data.length)}
            stroke="#B4B2A9"
            tick={{ fontSize: 12 }}
          />
          <YAxis stroke="#B4B2A9" tick={{ fontSize: 12 }} width={44} />
          <Tooltip
            formatter={(value) => [Number(value).toFixed(0) + " kcal", "热量"]}
            labelFormatter={(label) => String(label)}
          />
          {targetKcal != null && (
            <ReferenceLine y={targetKcal} stroke="#888780" strokeDasharray="4 4" />
          )}
          <Line
            type="monotone"
            dataKey="energy_kcal"
            stroke="#111111"
            strokeWidth={2}
            dot={{ r: 3 }}
            name="热量"
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
