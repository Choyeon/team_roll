/* Action helper: one place for "run it, toast the result, swallow the error". */

import { notify } from "./store.js";

export async function run(action, successText) {
  try {
    const result = await action();
    if (typeof successText === "string" && successText) notify(successText, "success");
    else if (result && result.message) notify(result.message, "success");
    return result ?? true;
  } catch (err) {
    notify(err.message || "操作失败", "error", 6000);
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
