"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { GoalForm, type GoalFormValues } from "@/components/goals/GoalForm";
import { ApiError } from "@/lib/api/client";
import { fetchMe, updateGoal } from "@/lib/api/endpoints";
import type { UserOut } from "@/lib/api/endpoints";

export default function SettingsGoalsPage() {
  const router = useRouter();
  const [profile, setProfile] = useState<UserOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchMe()
      .then((me) => {
        if (!cancelled) setProfile(me);
      })
      .catch(() => {
        if (!cancelled) setLoadError("加载失败，请刷新重试");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function onSubmit(values: GoalFormValues) {
    setError(null);
    try {
      await updateGoal(values);
      router.push("/today");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "保存失败，请稍后重试");
    }
  }

  if (loadError) {
    return <main className="mx-auto max-w-[480px] px-6 py-12">{loadError}</main>;
  }

  if (!profile) {
    return (
      <main className="mx-auto max-w-[480px] px-6 py-12 text-[14px] text-black/50">
        加载中…
      </main>
    );
  }

  return (
    <main className="mx-auto w-full max-w-[480px] px-6 py-12">
      <h1 className="text-[26px] font-medium tracking-tight">调整目标</h1>
      <p className="mt-1.5 text-[14px] text-black/50">
        修改后会从今天起生效，历史记录不受影响
      </p>

      <div className="mt-8">
        <GoalForm
          defaultValues={{
            sex: (profile.sex as GoalFormValues["sex"]) ?? "male",
            age: profile.age ?? 30,
            height_cm: profile.height_cm ?? 170,
            weight_kg: profile.weight_kg ?? 65,
          }}
          onSubmit={onSubmit}
          submitLabel="保存"
          errorMessage={error}
        />
      </div>
    </main>
  );
}
