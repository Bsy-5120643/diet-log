"use client";

import { apiFetch, setAccessToken } from "./client";
import type { GoalValues, LoginInput, RegisterInput } from "@/lib/validation/schemas";

export interface UserOut {
  id: string;
  email: string;
  nickname: string | null;
  sex: string | null;
  age: number | null;
  height_cm: number | null;
  weight_kg: number | null;
  timezone: string;
  has_goal: boolean;
}

export interface TokenPair {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export interface AuthResponse {
  user: UserOut;
  tokens: TokenPair;
}

export interface GoalOut {
  id: string;
  effective_from: string;
  source: string;
  energy_kcal: number;
  protein_g: number;
  fat_g: number;
  carb_g: number;
  fiber_g: number | null;
  sodium_mg: number | null;
  goal_type: string | null;
  activity_level: string | null;
  bmr_kcal: number | null;
  tdee_kcal: number | null;
  deficit_pct: number | null;
  updated_at: string;
}

export interface GoalEstimate {
  /** 基础代谢 */
  bmr_kcal: number;
  /** 每日总消耗 */
  tdee_kcal: number;
  /** 目标摄入热量 */
  target_kcal: number;
  /** 实际生效的缺口比例 */
  deficit_pct: number;
  protein_g: number;
  fat_g: number;
  carb_g: number;
  fiber_g: number;
  sodium_mg: number;
}

/** 只算不存，用于目标设置表单实时预览。 */
export async function estimateGoal(payload: GoalValues): Promise<GoalEstimate> {
  return apiFetch<GoalEstimate>(
    "goals/estimate",
    { method: "POST", body: JSON.stringify(payload) },
    { auth: false }
  );
}


export interface MacroValues {
  energy_kcal: number;
  protein_g: number;
  fat_g: number;
  carb_g: number;
  fiber_g: number;
  sodium_mg: number;
}

export interface MealBreakdown {
  energy_kcal: number;
  entry_count: number;
}

export interface DailySummaryOut {
  date: string;
  consumed: MacroValues;
  targets: MacroValues | null;
  remaining: MacroValues | null;
  percent: MacroValues | null;
  by_meal: Record<string, MealBreakdown>;
  entry_count: number;
  /** 原始数据缺失导致无法计算的字段，UI 应显示为 - 而非 0 */
  incomplete_fields: string[];
}

export interface DailyPointOut {
  date: string;
  energy_kcal: number;
  protein_g: number;
  fat_g: number;
  carb_g: number;
  target_kcal: number | null;
  entry_count: number;
}

export interface SummaryRangeOut {
  date_from: string;
  date_to: string;
  days: DailyPointOut[];
}

export interface WeightLogOut {
  id: string;
  logged_on: string;
  weight_kg: number;
  note: string | null;
  created_at: string;
}

export interface WeightLogListOut {
  date_from: string;
  date_to: string;
  logs: WeightLogOut[];
}

/**
 * 注册。confirmPassword 只在前端做一致性校验用，不发给后端。
 */
export async function register(
  payload: Omit<RegisterInput, "confirmPassword">
): Promise<AuthResponse> {
  const data = await apiFetch<AuthResponse>(
    "auth/register",
    { method: "POST", body: JSON.stringify(payload) },
    { auth: false }
  );
  setAccessToken(data.tokens.access_token);
  return data;
}

export async function login(payload: LoginInput): Promise<AuthResponse> {
  const data = await apiFetch<AuthResponse>(
    "auth/login",
    { method: "POST", body: JSON.stringify(payload) },
    { auth: false }
  );
  setAccessToken(data.tokens.access_token);
  return data;
}

export async function logout(): Promise<void> {
  try {
    await apiFetch<void>("auth/logout", { method: "POST", body: JSON.stringify({}) });
  } finally {
    setAccessToken(null);
  }
}

export async function fetchMe(): Promise<UserOut> {
  return apiFetch<UserOut>("auth/me");
}

export async function fetchCurrentGoal(): Promise<GoalOut> {
  return apiFetch<GoalOut>("goals/current");
}

export async function updateGoal(payload: GoalValues): Promise<GoalOut> {
  return apiFetch<GoalOut>("goals/current", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

/** 当日汇总。没记录时 consumed 全 0、targets 可能为 null，接口仍返回 200。 */
export async function fetchDailySummary(date: string): Promise<DailySummaryOut> {
  return apiFetch<DailySummaryOut>(`summary?date=${encodeURIComponent(date)}`);
}

/** 区间每日汇总，days 升序且补齐所有日期。 */
export async function fetchSummaryRange(
  dateFrom: string,
  dateTo: string
): Promise<SummaryRangeOut> {
  const query = new URLSearchParams({ from: dateFrom, to: dateTo });
  return apiFetch<SummaryRangeOut>(`summary/range?${query.toString()}`);
}

/** 查询区间内体重记录。不传则默认最近 7 天。 */
export async function fetchWeightLogs(
  dateFrom?: string,
  dateTo?: string
): Promise<WeightLogListOut> {
  const query = new URLSearchParams();
  if (dateFrom) query.set("from", dateFrom);
  if (dateTo) query.set("to", dateTo);
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiFetch<WeightLogListOut>(`weight-logs${suffix}`);
}

/** 记录某天体重；同一天重复提交会覆盖。 */
export async function createWeightLog(payload: {
  weight_kg: number;
  logged_on?: string;
  note?: string;
}): Promise<WeightLogOut> {
  return apiFetch<WeightLogOut>("weight-logs", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
export interface FoodOut {
  id: string;
  name: string;
  brand: string | null;
  energy_kcal: number;
  protein_g: number | null;
  fat_g: number | null;
  carb_g: number | null;
  fiber_g: number | null;
  sodium_mg: number | null;
  /** name 表示名称命中，alias 表示别名命中 */
  match_on: "name" | "alias";
  matched_alias: string | null;
}

export interface FoodSearchOut {
  keyword: string;
  items: FoodOut[];
  total: number;
  page: number;
  size: number;
  has_more: boolean;
}

export interface FoodEntryOut {
  id: string;
  food_id: string;
  food_name: string;
  entry_date: string;
  meal_type: string;
  meal_label: string;
  quantity_g: number;
  serving_unit: string | null;
  serving_count: number | null;
  energy_kcal: number;
  protein_g: number | null;
  fat_g: number | null;
  carb_g: number | null;
  fiber_g: number | null;
  sodium_mg: number | null;
  per_100g: Record<string, number | null>;
  note: string | null;
  created_at: string;
}

export interface FoodEntryListOut {
  date: string;
  items: FoodEntryOut[];
  total: number;
}

export interface CreateFoodEntryInput {
  food_id: string;
  meal_type: string;
  quantity_g: number;
  entry_date?: string;
  note?: string;
}

/** 搜索食物，同时匹配名称与别名。 */
export async function searchFoods(
  keyword: string,
  page = 1,
  size = 20
): Promise<FoodSearchOut> {
  const query = new URLSearchParams({ q: keyword, page: String(page), size: String(size) });
  return apiFetch<FoodSearchOut>("foods?" + query.toString());
}

/** 新增一条饮食记录。营养值由服务端计算，客户端不传。 */
export async function createFoodEntry(
  payload: CreateFoodEntryInput
): Promise<FoodEntryOut> {
  return apiFetch<FoodEntryOut>("food-entries", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function fetchFoodEntries(date: string): Promise<FoodEntryListOut> {
  return apiFetch<FoodEntryListOut>(
    "food-entries?date=" + encodeURIComponent(date)
  );
}

export async function deleteFoodEntry(id: string): Promise<void> {
  await apiFetch<void>("food-entries/" + id, { method: "DELETE" });
}
