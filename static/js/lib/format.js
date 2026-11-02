/* Presentation helpers: dates, numbers, status labels. */

const dtf = new Intl.DateTimeFormat("zh-CN", {
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});
const tf = new Intl.DateTimeFormat("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
const nf = new Intl.NumberFormat("zh-CN");

export const STATUS_LABEL = { active: "进行中", paused: "已暂停", ended: "已结束" };
export const ROLL_STATUS_LABEL = { valid: "有效", void: "已作废" };
export const ROLE_LABEL = { super: "超级管理员", admin: "管理员", viewer: "只读" };

/** Backend datetimes are aware UTC; parse defensively for older naive values. */
function toDate(value) {
  if (!value) return null;
  if (value instanceof Date) return Number.isNaN(value.getTime()) ? null : value;
  const text = String(value);
  const date = new Date(/([zZ]|[+-]\d{2}:?\d{2})$/.test(text) ? text : `${text.replace(" ", "T")}Z`);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function dateTime(value) {
  const date = toDate(value);
  return date ? dtf.format(date) : "—";
}

export function clock(value) {
  const date = toDate(value);
  return date ? tf.format(date) : "—";
}

export function dateOnly(value) {
  const date = toDate(value);
  return date ? date.toLocaleDateString("zh-CN") : "—";
}

export function fromNow(value) {
  const date = toDate(value);
  if (!date) return "—";
  const seconds = Math.round((date.getTime() - Date.now()) / 1000);
  const abs = Math.abs(seconds);
  const units = abs >= 86400 ? [86400, "天"] : abs >= 3600 ? [3600, "小时"] : abs >= 60 ? [60, "分钟"] : [1, "秒"];
  const amount = Math.round(abs / units[0]);
  return seconds >= 0 ? `${amount}${units[1]}后` : `${amount}${units[1]}前`;
}

export function utcOffsetMinutes() {
  return -new Date().getTimezoneOffset();
}

export function number(value) {
  return value === null || value === undefined ? "—" : nf.format(value);
}

export function percent(value, digits = 0) {
  if (value === null || value === undefined) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

export function bytes(value) {
  if (!value) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const index = Math.min(units.length - 1, Math.floor(Math.log(value) / Math.log(1024)));
  return `${(value / 1024 ** index).toFixed(index ? 1 : 0)} ${units[index]}`;
}

export function duration(seconds) {
  if (!seconds || seconds < 0) return "—";
  const parts = [];
  const days = Math.floor(seconds / 86400);
  if (days) parts.push(`${days}天`);
  parts.push(`${String(Math.floor((seconds % 86400) / 3600)).padStart(2, "0")}:${String(Math.floor((seconds % 3600) / 60)).padStart(2, "0")}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`);
  return parts.join(" ");
}

export function prettyJson(value) {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value !== "object") return String(value);
  try {
    return JSON.stringify(value, null, 1);
  } catch {
    return String(value);
  }
}

/** Audit details arrive as a JSON string; render them readably without throwing. */
export function jsonDetail(value) {
  if (!value) return "";
  if (typeof value === "object") return prettyJson(value);
  try {
    return prettyJson(JSON.parse(value));
  } catch {
    return String(value);
  }
}
