"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";

import {
  ACTIVITY_LEVELS,
  ACTIVITY_META,
  GOAL_META,
  GOAL_TYPES,
  type GoalValues,
  goalSchema,
} from "@/lib/validation/schemas";

export type GoalFormValues = GoalValues;

interface GoalFormProps {
  defaultValues?: Partial<GoalValues>;
  submitLabel?: string;
  pending?: boolean;
  errorMessage?: string | null;
  onSubmit: (values: GoalValues) => void | Promise<void>;
}

const inputClass =
  "w-full rounded-lg border border-black/15 px-3 py-2 text-[15px] outline-none focus:border-black/40";

export function GoalForm({
  defaultValues,
  submitLabel = "保存目标",
  pending = false,
  errorMessage = null,
  onSubmit,
}: GoalFormProps) {
  const {
    register,
    handleSubmit,
    watch,
    formState: { errors },
  } = useForm<GoalValues>({
    resolver: zodResolver(goalSchema),
    defaultValues: {
      sex: "male",
      goal_type: "maintain",
      activity_level: "moderate",
      deficit_pct: 0.2,
      ...defaultValues,
    },
    mode: "onBlur",
  });

  const goalType = watch("goal_type");

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-5" noValidate>
      <Field label="性别" error={errors.sex?.message}>
        <div className="flex gap-2">
          {SEX_OPTIONS.map((opt) => (
            <label
              key={opt.value}
              className="flex-1 cursor-pointer rounded-lg border border-black/15 px-3 py-2 text-center text-[15px] has-[:checked]:border-black has-[:checked]:bg-black/5"
            >
              <input
                type="radio"
                value={opt.value}
                {...register("sex")}
                className="sr-only"
              />
              {opt.label}
            </label>
          ))}
        </div>
      </Field>

      <Field label="年龄" suffix="岁" error={errors.age?.message}>
        <input
          type="number"
          inputMode="numeric"
          step={1}
          {...register("age")}
          className={inputClass}
        />
      </Field>

      <Field label="身高" suffix="cm" error={errors.height_cm?.message}>
        <input
          type="number"
          inputMode="decimal"
          step={0.1}
          {...register("height_cm")}
          className={inputClass}
        />
      </Field>

      <Field label="体重" suffix="kg" error={errors.weight_kg?.message}>
        <input
          type="number"
          inputMode="decimal"
          step={0.1}
          {...register("weight_kg")}
          className={inputClass}
        />
      </Field>

      <Field label="活动水平" error={errors.activity_level?.message}>
        <select {...register("activity_level")} className={inputClass}>
          {ACTIVITY_LEVELS.map((level) => (
            <option key={level} value={level}>
              {ACTIVITY_META[level].label} · {ACTIVITY_META[level].hint}
            </option>
          ))}
        </select>
      </Field>

      <Field label="目标" error={errors.goal_type?.message}>
        <div className="grid grid-cols-3 gap-2">
          {GOAL_TYPES.map((type) => (
            <label
              key={type}
              className="cursor-pointer rounded-lg border border-black/15 px-3 py-2 text-center text-[15px] has-[:checked]:border-black has-[:checked]:bg-black/5"
            >
              <input
                type="radio"
                value={type}
                {...register("goal_type")}
                className="sr-only"
              />
              {GOAL_META[type].label}
            </label>
          ))}
        </div>
        {goalType === "cut" && (
          <p className="mt-2 text-[13px] text-black/50">
            热量缺口 20%，蛋白质按 2.0 g/kg 配比以减少肌肉流失
          </p>
        )}
      </Field>

      {errorMessage && (
        <p className="rounded-lg bg-red-50 px-3 py-2 text-[14px] text-red-700">
          {errorMessage}
        </p>
      )}

      <button
        type="submit"
        disabled={pending}
        className="w-full rounded-lg bg-black px-4 py-3 text-[15px] font-medium text-white disabled:opacity-40"
      >
        {pending ? "保存中…" : submitLabel}
      </button>
    </form>
  );
}

const SEX_OPTIONS = [
  { value: "male", label: "男" },
  { value: "female", label: "女" },
] as const;

function Field({
  label,
  suffix,
  error,
  children,
}: {
  label: string;
  suffix?: string;
  error?: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="mb-1.5 flex items-baseline justify-between">
        <label className="text-[14px] font-medium text-black/80">{label}</label>
        {suffix && <span className="text-[13px] text-black/40">{suffix}</span>}
      </div>
      {children}
      {error && <p className="mt-1 text-[13px] text-red-600">{error}</p>}
    </div>
  );
}
