"use client";

import { useEffect, useState } from "react";
import useSWR from "swr";

import { createFoodEntry, searchFoods } from "@/lib/api/endpoints";
import type { FoodOut } from "@/lib/api/endpoints";
import { swrKeys } from "@/lib/api/keys";

export interface FoodSearchPanelProps {
  date: string;
  /** 添加成功后回调，用于触发看板刷新 */
  onAdded: () => void | Promise<void>;
}

const MEALS: { value: string; label: string }[] = [
  { value: "breakfast", label: "早餐" },
  { value: "lunch", label: "午餐" },
  { value: "dinner", label: "晚餐" },
  { value: "snack", label: "加餐" },
  { value: "late_night", label: "夜宵" },
];

export function FoodSearchPanel({ date, onAdded }: FoodSearchPanelProps) {
  const [keyword, setKeyword] = useState("");
  // 防抖后的关键词，避免每敲一个字就发请求
  const [debounced, setDebounced] = useState("");
  const [selected, setSelected] = useState<FoodOut | null>(null);
  const [quantity, setQuantity] = useState("100");
  const [mealType, setMealType] = useState("lunch");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(keyword.trim()), 250);
    return () => clearTimeout(timer);
  }, [keyword]);

  const { data, isLoading } = useSWR(swrKeys.foods(debounced, 1), ([, q]) =>
    searchFoods(String(q), 1, 20)
  );

  const items = data?.items ?? [];

  async function handleAdd() {
    if (!selected) return;
    const grams = Number(quantity);
    if (!Number.isFinite(grams) || grams <= 0 || grams > 5000) {
      setError("请输入 0~5000 之间的克数");
      return;
    }

    setError(null);
    setPending(true);
    try {
      await createFoodEntry({
        food_id: selected.id,
        meal_type: mealType,
        quantity_g: grams,
        entry_date: date,
      });
      // 清空选择，保留关键词方便连续添加
      setSelected(null);
      await onAdded();
    } catch (err) {
      setError(err instanceof Error ? err.message : "添加失败");
    } finally {
      setPending(false);
    }
  }

  return (
    <section className="rounded-xl border border-black/[0.08] bg-white p-5">
      <h2 className="text-[15px] font-medium">添加饮食</h2>
      <p className="mt-0.5 text-[13px] text-black/45">搜索食物，记录到 {date}</p>

      <div className="mt-4">
        <input
          type="search"
          value={keyword}
          onChange={(event) => setKeyword(event.target.value)}
          placeholder="搜索食物，如：鸡胸肉、西红柿"
          className="w-full rounded-lg border border-black/15 px-3 py-2.5 text-[15px] outline-none focus:border-black/40"
        />
      </div>

      {!selected && (
        <div className="mt-3 max-h-[280px] overflow-y-auto">
          {isLoading && (
            <p className="px-1 py-3 text-[13px] text-black/40">搜索中…</p>
          )}
          {!isLoading && debounced && items.length === 0 && (
            <p className="px-1 py-3 text-[13px] text-black/40">
              没有找到「{debounced}」，换个关键词试试
            </p>
          )}
          {!isLoading && items.length > 0 && (
            <ul className="divide-y divide-black/[0.06]">
              {items.map((food) => (
                <li key={food.id}>
                  <button
                    type="button"
                    onClick={() => setSelected(food)}
                    className="w-full px-1 py-2.5 text-left hover:bg-black/[0.03]"
                  >
                    <div className="flex items-baseline justify-between gap-3">
                      <span className="text-[14px]">{food.name}</span>
                      <span className="shrink-0 text-[13px] tabular-nums text-black/50">
                        {food.energy_kcal.toFixed(0)} kcal/100g
                      </span>
                    </div>
                    {food.match_on === "alias" && food.matched_alias && (
                      <span className="text-[12px] text-black/40">
                        匹配别名：{food.matched_alias}
                      </span>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {selected && (
        <div className="mt-3 rounded-lg bg-black/[0.03] p-4">
          <div className="flex items-baseline justify-between">
            <span className="text-[15px] font-medium">{selected.name}</span>
            <button
              type="button"
              onClick={() => setSelected(null)}
              className="text-[13px] text-black/40 hover:text-black"
            >
              换一个
            </button>
          </div>
          <p className="mt-1 text-[12px] tabular-nums text-black/45">
            每 100g：{selected.energy_kcal.toFixed(0)} kcal · 蛋白{" "}
            {selected.protein_g ?? "-"} g
          </p>

          <div className="mt-4 flex items-center gap-2">
            <input
              type="number"
              inputMode="decimal"
              step="10"
              value={quantity}
              onChange={(event) => setQuantity(event.target.value)}
              className="w-24 rounded-lg border border-black/15 px-3 py-2 text-[15px] tabular-nums outline-none focus:border-black/40"
            />
            <span className="text-[13px] text-black/50">克</span>
          </div>

          <div className="mt-3 flex flex-wrap gap-2">
            {MEALS.map((meal) => (
              <button
                key={meal.value}
                type="button"
                onClick={() => setMealType(meal.value)}
                className={
                  "rounded-lg border px-3 py-1.5 text-[13px] " +
                  (mealType === meal.value
                    ? "border-black bg-black text-white"
                    : "border-black/15 hover:bg-black/[0.04]")
                }
              >
                {meal.label}
              </button>
            ))}
          </div>

          {error && <p className="mt-3 text-[13px] text-red-600">{error}</p>}

          <button
            type="button"
            onClick={handleAdd}
            disabled={pending}
            className="mt-4 w-full rounded-lg bg-black px-4 py-2.5 text-[14px] font-medium text-white disabled:opacity-40"
          >
            {pending ? "添加中…" : "添加"}
          </button>
        </div>
      )}
    </section>
  );
}
