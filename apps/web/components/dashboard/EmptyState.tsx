"use client";

import Link from "next/link";

export interface EmptyStateProps {
  title: string;
  description?: string;
  actionLabel?: string;
  actionHref?: string;
}

export function EmptyState({
  title,
  description,
  actionLabel,
  actionHref,
}: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-10 text-center">
      <div className="mb-3 h-10 w-10 rounded-full border border-black/15" />
      <p className="text-[14px] font-medium text-black/70">{title}</p>
      {description && (
        <p className="mt-1 max-w-[280px] text-[13px] leading-relaxed text-black/45">
          {description}
        </p>
      )}
      {actionLabel && actionHref && (
        <Link
          href={actionHref}
          className="mt-4 inline-flex items-center rounded-lg border border-black/20 px-4 py-2 text-[13px] font-medium hover:bg-black/[0.04]"
        >
          {actionLabel}
        </Link>
      )}
    </div>
  );
}
