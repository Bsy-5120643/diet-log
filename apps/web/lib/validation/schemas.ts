import { z } from "zod";

/**
 * 前后端校验规则的唯一来源。
 * 这里的每一条约束，后端 app/schemas/*.py 都有对应实现 ——
 * 前端负责即时反馈，后端负责权威校验，两边规则必须同步改。
 */

export const SEXES = ["male", "female"] as const;
export const ACTIVITY_LEVELS = [
  "sedentary",
  "light",
  "moderate",
  "active",
  "very_active",
] as const;
export const GOAL_TYPES = ["cut", "maintain", "gain"] as const;

// 与 app/services/goal_calculator.py 的常量保持一致
export const AGE_MIN = 14;
export const AGE_MAX = 100;
export const HEIGHT_MIN = 50;
export const HEIGHT_MAX = 250;
export const WEIGHT_MIN = 20;
export const WEIGHT_MAX = 400;
export const DEFICIT_MAX = 0.2;

// ---------------------------------------------------------------------------
// 认证
// ---------------------------------------------------------------------------

export const emailField = z
  .string()
  .trim()
  .min(1, "请输入邮箱")
  .email("邮箱格式不正确")
  .max(254, "邮箱过长")
  .transform((v) => v.toLowerCase());

export const registerSchema = z
  .object({
    email: emailField,
    password: z
      .string()
      .min(8, "密码至少 8 位")
      .max(128, "密码不能超过 128 位")
      .regex(/[A-Za-z]/, "密码需包含字母")
      .regex(/\d/, "密码需包含数字"),
    confirmPassword: z.string(),
    nickname: z.string().trim().max(50, "昵称不能超过 50 字").optional(),
  })
  .refine((v) => v.password === v.confirmPassword, {
    message: "两次输入的密码不一致",
    path: ["confirmPassword"],
  });

export const loginSchema = z.object({
  email: emailField,
  password: z.string().min(1, "请输入密码"),
});

// ---------------------------------------------------------------------------
// 目标
// ---------------------------------------------------------------------------

export const goalSchema = z.object({
  sex: z.enum(SEXES, { errorMap: () => ({ message: "请选择性别" }) }),

  age: z.coerce
    .number({ invalid_type_error: "请输入年龄" })
    .int("年龄需为整数")
    .min(AGE_MIN, `年龄需在 ${AGE_MIN}~${AGE_MAX} 岁之间`)
    .max(AGE_MAX, `年龄需在 ${AGE_MIN}~${AGE_MAX} 岁之间`),

  height_cm: z.coerce
    .number({ invalid_type_error: "请输入身高" })
    .gt(HEIGHT_MIN, `身高需在 ${HEIGHT_MIN}~${HEIGHT_MAX} cm 之间`)
    .max(HEIGHT_MAX, `身高需在 ${HEIGHT_MIN}~${HEIGHT_MAX} cm 之间`),

  weight_kg: z.coerce
    .number({ invalid_type_error: "请输入体重" })
    .gt(WEIGHT_MIN, `体重需在 ${WEIGHT_MIN}~${WEIGHT_MAX} kg 之间`)
    .max(WEIGHT_MAX, `体重需在 ${WEIGHT_MIN}~${WEIGHT_MAX} kg 之间`),

  activity_level: z.enum(ACTIVITY_LEVELS, {
    errorMap: () => ({ message: "请选择活动水平" }),
  }),

  goal_type: z.enum(GOAL_TYPES, {
    errorMap: () => ({ message: "请选择目标" }),
  }),

  // 减脂缺口：0~0.20；维持/增肌时后端忽略
  deficit_pct: z.coerce
    .number()
    .min(0, "缺口不能为负")
    .max(DEFICIT_MAX, `减脂缺口不得超过 ${DEFICIT_MAX * 100}%`)
    .default(DEFICIT_MAX),
});

export type RegisterInput = z.infer<typeof registerSchema>;
export type LoginInput = z.infer<typeof loginSchema>;
export type GoalInput = z.input<typeof goalSchema>;
export type GoalValues = z.output<typeof goalSchema>;

// ---------------------------------------------------------------------------
// 展示用元数据（label / 说明），避免表单里散落中文硬编码
// ---------------------------------------------------------------------------

export const ACTIVITY_META: Record<
  (typeof ACTIVITY_LEVELS)[number],
  { label: string; hint: string; factor: number }
> = {
  sedentary: { label: "久坐", hint: "几乎不运动，办公室为主", factor: 1.2 },
  light: { label: "轻度", hint: "每周运动 1~3 次", factor: 1.375 },
  moderate: { label: "中等", hint: "每周运动 3~5 次", factor: 1.55 },
  active: { label: "高强度", hint: "每周运动 6~7 次", factor: 1.725 },
  very_active: {
    label: "极高",
    hint: "体力工作或一天两练",
    factor: 1.9,
  },
};

export const GOAL_META: Record<
  (typeof GOAL_TYPES)[number],
  { label: string; hint: string }
> = {
  cut: { label: "减脂", hint: "热量缺口 20%，蛋白质拉高保肌肉" },
  maintain: { label: "维持", hint: "热量持平，维持当前体重" },
  gain: { label: "增肌", hint: "热量盈余 10%，偏干净的增重" },
};
