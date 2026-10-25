"use client";

import { MacroBar } from "./MacroBar";
import type { MacroValues } from "@/lib/api/endpoints";

export interface MacroBarListProps {
  consumed: MacroValues;
  /** null 时三条都按「未设目标」渲染，不报错 */
  targets: MacroValues | null;
  /**
   * 因原始数据缺失而无法计算的字段名。
   * 命中时该条显示为「-」而不是 0 —— 0 会被误读成「确实摄入了 0」。
   */
  incompleteFields?: string[];
}

const MACROS: { key: keyof MacroValues; label: string; color: string }[] = [
  { key: "protein_g", label: "蛋白质", color: "#378ADD" },
  { key: "carb_g", label: "碳水", color: "#EF9F27" },
  { key: "fat_g", label: "脂肪", color: "#D4537E" },
];

export function MacroBarList({
  consumed,
  targets,
  incompleteFields = [],
}: MacroBarListProps) {
  return (
    <div className="space-y-4">
      {MACROS.map((macro) => {
        const missing = incompleteFields.includes(macro.key);
        const raw = consumed[macro.key];

        return (
          <MacroBar
            key={macro.key}
            label={macro.label}
            // 数据缺失 -> null，UI 显示「-」；否则正常显示数值
            consumed={missing ? null : Number(raw ?? 0)}
            target={targets ? Number(targets[macro.key] ?? 0) : null}
            color={macro.color}
          />
        );
      })}
    </div>
  );
}
