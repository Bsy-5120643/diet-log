"use client";

import { useState } from "react";

export interface WeightQuickAddProps {
  /** 默认日期 YYYY-MM-DD */
  date: string;
  /** 已有体重时作为回显值 */
  currentWeight?: number | null;
  pending?: boolean;
  onSubmit: (payload: { weight_kg: number; logged_on: string }) => Promise<void>;
}

export function WeightQuickAdd({
  date,
  currentWeight = null,
  pending = false,
  onSubmit,
}: WeightQuickAddProps) {
  const [value, setValue] = useState(
    currentWeight != null ? String(currentWeight) : ""
  );
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    const weight = Number(value);
    if (!Number.isFinite(weight) || weight < 20 || weight > 400) {
      setError("请输入 20~400 之间的体重");
      return;
    }
    setError(null);
    await onSubmit({ weight_kg: weight, logged_on: date });
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-2">
    <div className="flex items-center gap-2">
      <input
        type="number"
        step="0.1"
        inputMode="decimal"
        value={value}
        onChange={(event) => setValue(event.target.value)}
        placeholder="今日体重"
        className="w-full rounded-lg border border-black/15 px-3 py-2 text-[15px] outline-none focus:border-black/40"
      />
      <span className="shrink-0 text-[13px] text-black/40">kg</span>
    </div>
    {error && <p className="text-[12px] text-red-600">{error}</p>}
    <button
      type="submit"
      disabled={pending}
      className="w-full rounded-lg border border-black/20 px-3 py-2 text-[13px] font-medium hover:bg-black/[0.04] disabled:opacity-40"
    >
      {pending ? "记录中…" : "记录体重"}
    </button>
  </form>
  );
}
