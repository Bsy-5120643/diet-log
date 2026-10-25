"use client";

import { EmptyState } from "./EmptyState";

export interface TrendCardProps {
  title: string;
  description?: string;
  /** 空数据判定：由父组件传入，避免在子组件里猜 */
  isEmpty: boolean;
  emptyHint?: string;
  emptyActionLabel?: string;
  emptyActionHref?: string;
  loading?: boolean;
  children: React.ReactNode;
}

export function TrendCard({
  title,
  description,
  isEmpty,
  emptyHint,
  emptyActionLabel,
  emptyActionHref,
  loading = false,
  children,
}: TrendCardProps) {
  return (
    <section className="rounded-xl border border-black/[0.08] bg-white p-5">
      <header className="mb-4">
        <h2 className="text-[15px] font-medium">{title}</h2>
        {description && (
          <p className="mt-0.5 text-[13px] text-black/45">{description}</p>
        )}
      </header>

      {loading ? (
        <div className="h-[200px] w-full animate-pulse rounded-lg bg-black/[0.04]" />
      ) : isEmpty ? (
        <EmptyState
          title="还没有数据"
          description={emptyHint}
          actionLabel={emptyActionLabel}
          actionHref={emptyActionHref}
        />
      ) : (
        children
      )}
    </section>
  );
}
