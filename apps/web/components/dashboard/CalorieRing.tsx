"use client";

export interface CalorieRingProps {
  /** 已摄入热量 kcal */
  consumed: number;
  /** 目标热量 kcal；null 表示用户尚未设置目标 */
  target: number | null;
  /** 环外框尺寸 px */
  size?: number;
  /** 环的厚度 px */
  thickness?: number;
}

/**
 * 今日热量环形进度。
 *
 * 刻意用原生 SVG 而非图表库：只有一个圆弧，引入 Recharts 反而更重，
 * 而且手写 SVG 对无障碍（role="img"）和 SSR 都更干净。
 */
export function CalorieRing({
  consumed,
  target,
  size = 168,
  thickness = 14,
}: CalorieRingProps) {
  const radius = (size - thickness) / 2;
  const circumference = 2 * Math.PI * radius;

  const hasTarget = target !== null && target > 0;
  const rawRatio = hasTarget ? consumed / (target as number) : 0;
  const ratio = Math.min(rawRatio, 1);
  const percent = Math.round(rawRatio * 100);
  const isOver = hasTarget && consumed > (target as number);

  const stroke = isOver ? "#E24B4A" : "#111111";

  return (
    <div
      className="relative shrink-0"
      style={{ width: size, height: size }}
      role="img"
      aria-label={
        hasTarget
          ? `已摄入 ${Math.round(consumed)} 千卡，目标 ${Math.round(target as number)} 千卡，达成 ${percent}%`
          : `已摄入 ${Math.round(consumed)} 千卡，尚未设置目标`
      }
    >
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="#E8E6E1"
          strokeWidth={thickness}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={stroke}
          strokeWidth={thickness}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - ratio)}
        />
      </svg>

      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-[26px] font-medium tabular-nums leading-none">
          {Math.round(consumed)}
        </span>
        {hasTarget ? (
          <>
            <span className="mt-1 text-[12px] text-black/40 tabular-nums">
              / {Math.round(target as number)} kcal
            </span>
            <span className="mt-1.5 text-[12px] text-black/50 tabular-nums">
              {isOver ? `超出 ${Math.round(consumed - (target as number))}` : `还差 ${Math.round((target as number) - consumed)}`}
            </span>
          </>
        ) : (
          <span className="mt-1 text-[12px] text-black/40">未设目标</span>
        )}
      </div>
    </div>
  );
}
