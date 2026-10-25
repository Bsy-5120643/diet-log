"use client";

import { MedalBadge, medalRingColor } from "./MedalBadge";
import type { LeaderboardEntry, LeaderboardMe } from "@/lib/api/health";

const GOAL_OPTIONS: { value: string | null; label: string }[] = [
  { value: null, label: "全部" },
  { value: "减脂", label: "减脂" },
  { value: "增肌", label: "增肌" },
];

export interface LeaderboardListProps {
  items: LeaderboardEntry[];
  me: LeaderboardMe;
  goal: string | null;
  onGoalChange: (goal: string | null) => void;
  loading?: boolean;
}

export function LeaderboardList({
  items,
  me,
  goal,
  onGoalChange,
  loading = false,
}: LeaderboardListProps) {
  return (
    <div className="flex flex-col">
      <GoalFilterTabs value={goal} onChange={onGoalChange} />

      {loading ? (
        <div className="space-y-2 py-4">
          {[0, 1, 2].map((i) => (
            <div
              key={i}
              className="h-14 w-full animate-pulse rounded-lg bg-black/[0.04]"
            />
          ))}
        </div>
      ) : items.length === 0 ? (
        <p className="py-8 text-center text-[14px] text-black/40">
          还没有人上榜，记录 3 天以上就能出现在这里
        </p>
      ) : (
        <ul className="divide-y divide-black/[0.06]">
          {items.map((item) => (
            <li key={item.rank}>
              <LeaderboardRow entry={item} />
            </li>
          ))}
        </ul>
      )}

      <MeCard me={me} />
    </div>
  );
}

// ---------------------------------------------------------------------------

export interface GoalFilterTabsProps {
  value: string | null;
  onChange: (goal: string | null) => void;
}

function GoalFilterTabs({ value, onChange }: GoalFilterTabsProps) {
  return (
    <div className="mb-4 flex gap-2">
      {GOAL_OPTIONS.map((option) => {
        const active = value === option.value;
        return (
          <button
            key={option.label}
            type="button"
            onClick={() => onChange(option.value)}
            className={
              "rounded-lg border px-3.5 py-1.5 text-[13px] " +
              (active
                ? "border-black bg-black text-white"
                : "border-black/15 hover:bg-black/[0.04]")
            }
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------

function LeaderboardRow({ entry }: { entry: LeaderboardEntry }) {
  const ring = medalRingColor(entry.rank);

  return (
    <div className="flex items-center gap-3 py-3">
      <MedalBadge rank={entry.rank} />

      <Avatar nickname={entry.nickname} url={entry.avatar_url} ring={ring} />

      <div className="min-w-0 flex-1">
        <p className="truncate text-[14px]">{entry.nickname}</p>
      </div>

      <span className="shrink-0 text-[14px] font-medium tabular-nums">
        {entry.avg_score.toFixed(1)}
      </span>
    </div>
  );
}

function Avatar({
  nickname,
  url,
  ring,
}: {
  nickname: string;
  url: string | null;
  ring: string | null;
}) {
  const boxStyle = {
    width: 40,
    height: 40,
    boxShadow: ring ? `0 0 0 2px ${ring}` : undefined,
  };

  if (url) {
    return (
      // 头像是外链地址，用原生 img 避免 next/image 域名白名单配置
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={url}
        alt={nickname}
        className="shrink-0 rounded-full object-cover"
        style={boxStyle}
      />
    );
  }

  // 没有头像时用昵称首字做占位
  return (
    <span
      className="flex shrink-0 items-center justify-center rounded-full bg-black/[0.06] text-[15px] text-black/50"
      style={boxStyle}
      aria-hidden="true"
    >
      {nickname.slice(0, 1)}
    </span>
  );
}

// ---------------------------------------------------------------------------

/**
 * 吸底的「我的排名」卡片。
 *
 * 上榜 → 显示名次与均分；未上榜 → 显示还差几天，给冷启动用户一个明确目标。
 */
function MeCard({ me }: { me: LeaderboardMe }) {
  const needed = Math.max(0, 3 - me.logged_days);

  return (
    <div className="sticky bottom-0 mt-4 border-t border-black/[0.08] bg-white/95 pt-3 backdrop-blur">
      <div className="flex items-center justify-between gap-3 rounded-lg bg-black/[0.03] px-4 py-3">
        <span className="text-[13px] text-black/50">我的排名</span>

        {me.qualified && me.rank !== null ? (
          <span className="text-[14px] font-medium tabular-nums">
            第 {me.rank} 名
            {me.avg_score !== null && (
              <span className="ml-2 text-black/45">
                {me.avg_score.toFixed(1)} 分
              </span>
            )}
          </span>
        ) : (
          <span className="text-right text-[13px] text-black/45">
            未上榜
            {needed > 0 && (
              <span className="ml-1">· 再记 {needed} 天即可上榜</span>
            )}
          </span>
        )}
      </div>
    </div>
  );
}
