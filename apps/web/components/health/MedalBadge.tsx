"use client";

const MEDALS: Record<number, { background: string; text: string; label: string }> = {
  1: { background: "#E0A020", text: "#FFFFFF", label: "金牌" },
  2: { background: "#A8A8A8", text: "#FFFFFF", label: "银牌" },
  3: { background: "#B87333", text: "#FFFFFF", label: "铜牌" },
};

export interface MedalBadgeProps {
  /** 名次，从 1 开始 */
  rank: number;
  size?: number;
}

/**
 * 名次徽章：前三名显示金 / 银 / 铜牌，其余显示灰色数字。
 */
export function MedalBadge({ rank, size = 28 }: MedalBadgeProps) {
  const medal = MEDALS[rank];
  const background = medal?.background ?? "#EDEBE6";
  const color = medal?.text ?? "#5F5E5A";

  return (
    <span
      className="inline-flex shrink-0 items-center justify-center rounded-full font-medium tabular-nums"
      style={{
        width: size,
        height: size,
        fontSize: size * 0.45,
        backgroundColor: background,
        color,
      }}
      title={medal?.label ?? `第 ${rank} 名`}
      aria-label={medal?.label ?? `第 ${rank} 名`}
    >
      {rank}
    </span>
  );
}

/** 前三名的头像外圈颜色；其余返回 null（不描边） */
export function medalRingColor(rank: number): string | null {
  return MEDALS[rank]?.background ?? null;
}
