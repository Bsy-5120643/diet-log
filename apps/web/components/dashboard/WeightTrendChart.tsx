"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export interface WeightPoint {
  date: string;
  weight_kg: number;
}

export interface WeightTrendChartProps {
  data: WeightPoint[];
  height?: number;
}

function formatDay(iso: string): string {
  const parts = iso.split("-");
  return parts[1] + "/" + parts[2];
}

export function WeightTrendChart({
  data,
  height = 200,
}: WeightTrendChartProps) {
  // 体重波动通常只有 1~2kg，Y 轴从 0 起会把折线压平。
  // 这里按数据范围留白，只画有意义的区间。
  const values = data.map((point) => point.weight_kg);
  const min = values.length ? Math.min(...values) : 0;
  const max = values.length ? Math.max(...values) : 0;
  const padding = Math.max((max - min) * 0.3, 0.5);
  const domain: [number, number] = [
    Math.max(0, min - padding),
    max + padding,
  ];

  return (
    <div className="w-full" style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 12, left: -16, bottom: 0 }}>
          <CartesianGrid stroke="#E8E6E1" strokeDasharray="3 3" vertical={false} />
          <XAxis
            dataKey="date"
            tickFormatter={formatDay}
            interval={data.length > 7 ? 1 : 0}
          />
          <YAxis domain={domain} width={44} tick={{ fontSize: 12 }} />
          <Tooltip formatter={(value) => [Number(value).toFixed(1) + " kg", "体重"]} />
          <Line type="monotone" dataKey="weight_kg" stroke="#111111" strokeWidth={2} dot={{ r: 3 }} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
