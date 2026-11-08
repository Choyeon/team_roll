/* Action helper: one place for "run it, toast the result, swallow the error". */

import { notify } from "./store.js";

export async function run(action, successText) {
  try {
    const result = await action();
    if (typeof successText === "string" && successText) notify(successText, "success");
    else if (result && result.message) notify(result.message, "success");
    return result ?? true;
  } catch (err) {
    notify(err.message || "操作失败", "danger", 6000);
    return null;
  }
}

export function formFields(source, keys) {
  const payload = {};
  for (const key of keys) {
    const value = source[key];
    payload[key] = typeof value === "string" ? value.trim() : value;
  }
  return payload;
}

/**
 * 页面级加载走这里：失败时把错误留在页面上等用户重试，而不是只发一条六秒就消失的 toast。
 * 返回 null 表示这次没拿到数据，调用方不要覆盖已有列表。
 */
export async function tryLoad(error, action) {
  error.value = "";
  try {
    return await action();
  } catch (err) {
    error.value = err.message || "加载失败";
    return null;
  }
}
