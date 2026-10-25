"use client";

export interface MacroBarProps {
  label: string;
  /** 已摄入克数；null 表示食物原始数据缺失、算不出来 */
  consumed: number | null;
  /** 目标克数；null 表示用户尚未设置目标 */
  target: number | null;
  color: string;
  showPercent?: boolean;
}

/**
 * 缺失值显示规则：
 * - consumed 为 null → 显示「-」，进度条宽度 0，并标注「数据缺失」
 * - consumed 为 0   → 正常显示 0（这是真实摄入量，与缺失语义不同）
 */
export function MacroBar({
  label,
  consumed,
  target,
  color,
  showPercent = true,
}: MacroBarProps) {
  const isMissing = consumed === null;
  const hasTarget = target !== null && target > 0;

  // 缺失时按 0 参与进度计算，总量不受影响
  const effective = isMissing ? 0 : consumed;
  const percent = hasTarget ? Math.round((effective / (target as number)) * 100) : 0;
  const isOver = hasTarget && effective > (target as number);
  const width = Math.min(Math.max(percent, 0), 100);

  return (
    <div className="space-y-1.5">
      <div className="flex items-baseline justify-between text-[13px]">
        <span className="text-black/60">{label}</span>
        <span className="tabular-nums">
          {isMissing ? (
            <span className="text-black/35">-</span>
          ) : (
            <span className="font-medium">{consumed.toFixed(1)}</span>
          )}
          <span className="text-black/40">
            {hasTarget ? " / " + (target as number).toFixed(1) : " / -"} g
          </span>
        </span>
      </div>

      <div className="h-2 overflow-hidden rounded-full bg-black/[0.07]">
        <div
          className="h-full rounded-full transition-[width] duration-300"
          style={{
            width: width + "%",
            backgroundColor: isOver ? "#E24B4A" : color,
          }}
        />
      </div>

      {showPercent && hasTarget && (
        <p className="text-[12px] tabular-nums text-black/40">
          达成 {percent}%{isOver ? "（已超额）" : ""}
        </p>
      )}

      {isMissing && (
        <p className="text-[12px] text-black/35">
          有食物缺这项数据，未计入
        </p>
      )}
    </div>
  );
}
