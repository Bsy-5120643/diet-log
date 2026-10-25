"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { GoalForm, type GoalFormValues } from "@/components/goals/GoalForm";
import { ApiError } from "@/lib/api/client";
import { estimateGoal, updateGoal } from "@/lib/api/endpoints";
import type { GoalEstimate } from "@/lib/api/endpoints";

export default function OnboardingGoalsPage() {
  const router = useRouter();
  const [estimate, setEstimate] = useState<GoalEstimate | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(values: GoalFormValues) {
    setError(null);
    try {
      // 先算一遍给用户看，再落库
      const preview = await estimateGoal(values);
      setEstimate(preview);

      await updateGoal(values);
      router.push("/today");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "保存失败，请稍后重试");
    }
  }

  return (
    <main className="mx-auto w-full max-w-[480px] px-6 py-12">
      <h1 className="text-[26px] font-medium tracking-tight">设置你的目标</h1>
      <p className="mt-1.5 text-[14px] text-black/50">
        我们用 Mifflin-St Jeor 公式估算你的每日能量消耗，据此给出热量与三大营养素目标
      </p>

      <div className="mt-8">
        <GoalForm onSubmit={onSubmit} submitLabel="开始记录" errorMessage={error} />
      </div>

      {estimate && (
        <section className="mt-8 rounded-xl bg-black/[0.03] p-5">
          <h2 className="text-[15px] font-medium">为你计算的目标</h2>
          <dl className="mt-3 space-y-2 text-[14px]">
            <Row label="基础代谢 BMR" value={`${estimate.bmr_kcal.toFixed(1)} kcal`} />
            <Row label="每日总消耗 TDEE" value={`${estimate.tdee_kcal.toFixed(1)} kcal`} />
            <Row label="目标摄入" value={`${estimate.target_kcal} kcal`} />
            <Row label="实际缺口" value={`${(estimate.deficit_pct * 100).toFixed(1)}%`} />
            <div className="my-3 h-px bg-black/10" />
            <Row label="蛋白质" value={`${estimate.protein_g} g`} />
            <Row label="脂肪" value={`${estimate.fat_g} g`} />
            <Row label="碳水化合物" value={`${estimate.carb_g} g`} />
            <Row label="膳食纤维（参考）" value={`${estimate.fiber_g} g`} />
          </dl>
        </section>
      )}
    </main>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between">
      <dt className="text-black/60">{label}</dt>
      <dd className="font-medium tabular-nums">{value}</dd>
    </div>
  );
}
