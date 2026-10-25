/**
 * 日期工具：全站唯一处理「今天」的地方。
 *
 * ⚠️ 禁止在组件里写 new Date().toISOString().slice(0, 10)
 *    toISOString() 会先转成 UTC，东八区 10/26 07:00 会被截成 "2026-10-25"，
 *    记录就记到前一天去了。必须用下面的 toISODate()。
 */

/** 按浏览器本地时区格式化为 YYYY-MM-DD */
export function toISODate(date: Date = new Date()): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

/** 在 YYYY-MM-DD 上加减天数，返回新的 YYYY-MM-DD（不经过 UTC） */
export function shiftDate(isoDate: string, days: number): string {
  const [year, month, day] = isoDate.split("-").map(Number);
  const date = new Date(year, month - 1, day);
  date.setDate(date.getDate() + days);
  return toISODate(date);
}

/** 该日期是否是「本地今天」或更早（用于禁止记录未来日期） */
export function isTodayOrPast(isoDate: string): boolean {
  return isoDate <= toISODate();
}
