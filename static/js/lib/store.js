/* Shared client state: session, theme, toasts. */

import { api } from "./api.js";
import { reactive, watch } from "./vue.js";

const THEME_KEY = "team-roll-theme";

export const store = reactive({
  auth: "loading", // loading | authed | anon
  me: null,
  toasts: [],
  theme: localStorage.getItem(THEME_KEY) || "auto",
});

export function can(capability) {
  return Boolean(store.me && store.me.capabilities.includes(capability));
}

let toastSeq = 0;

export function notify(text, type = "info", ttl = 4000) {
  const id = ++toastSeq;
  store.toasts.push({ id, text, type });
  if (ttl) setTimeout(() => dismissToast(id), ttl);
  return id;
}

export function dismissToast(id) {
  const index = store.toasts.findIndex((toast) => toast.id === id);
  if (index >= 0) store.toasts.splice(index, 1);
}

export async function loadSession() {
  try {
    store.me = await api.get("/auth/me");
    store.auth = "authed";
  } catch {
    store.me = null;
    store.auth = "anon";
  }
}

export async function login(username, password) {
  store.me = await api.post("/auth/login", { username, password });
  store.auth = "authed";
  return store.me;
}

export async function logout() {
  try {
    await api.post("/auth/logout");
  } finally {
    store.me = null;
    store.auth = "anon";
  }
}

/* --- theme --- */

function applyTheme(value) {
  const explicit = value === "light" || value === "dark" ? value : null;
  if (explicit) document.documentElement.dataset.theme = explicit;
  else delete document.documentElement.dataset.theme;
  if (value === "auto") localStorage.removeItem(THEME_KEY);
  else localStorage.setItem(THEME_KEY, value);
}

export function cycleTheme() {
  const order = ["auto", "light", "dark"];
  store.theme = order[(order.indexOf(store.theme) + 1) % order.length];
}

export function initTheme() {
  applyTheme(store.theme);
  watch(() => store.theme, applyTheme);
}
