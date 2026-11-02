/* Tiny history router: path patterns -> view components.
   The server renders a metadata-rich shell for every route, so this only needs
   to swap views for same-document navigation. */

import { computed, reactive } from "./vue.js";

const state = reactive({ path: "/", query: {} });
let table = [];

function compile(pattern) {
  const names = [];
  const source = pattern
    .split("/")
    .filter(Boolean)
    .map((segment) => {
      if (segment.startsWith(":")) {
        const name = segment.replace(/^:/, "").replace(/\?$/, "");
        names.push(name);
        return segment.endsWith("?") ? "(?:/([^/]+))?" : "/([^/]+)";
      }
      if (segment === "*") {
        names.push("wildcard");
        return "(?:/(.*))?";
      }
      return `/${segment}`;
    })
    .join("");
  return { regexp: new RegExp(`^${source || ""}/?$`), names };
}

export function match(path) {
  for (const entry of table) {
    const found = entry.regexp.exec(path);
    if (!found) continue;
    const params = {};
    entry.names.forEach((name, index) => {
      const value = found[index + 1];
      if (value !== undefined && value !== "") params[name] = decodeURIComponent(value);
    });
    return { entry, params };
  }
  return null;
}

export const route = computed(() => {
  const hit = match(state.path);
  return hit ? { view: hit.entry.view, params: hit.params, title: hit.entry.title, name: hit.entry.name } : null;
});

export const params = computed(() => route.value?.params ?? {});
export const query = computed(() => state.query);

function apply(fullPath) {
  const url = new URL(fullPath, window.location.origin);
  const path = url.pathname.replace(/(?<=.)\/$/, "");
  state.path = path;
  state.query = Object.fromEntries(url.searchParams.entries());
  const hit = match(path);
  if (hit?.entry?.title) {
    document.title =
      typeof hit.entry.title === "function" ? hit.entry.title(state.query, state) : hit.entry.title;
  }
  if (!hit || hit.entry.scroll !== false) window.scrollTo({ top: 0 });
  window.dispatchEvent(new Event("team-roll:navigated"));
}

export function navigate(target, { replace = false } = {}) {
  const url = new URL(target, window.location.origin);
  if (url.origin !== window.location.origin) {
    window.location.assign(url.href);
    return;
  }
  const next = `${url.pathname}${url.search}`;
  if (next === `${state.path}${new URLSearchParams(state.query).toString() ? `?${new URLSearchParams(state.query)}` : ""}`) return;
  history[replace ? "replaceState" : "pushState"]({}, "", next);
  apply(next);
}

/** Anchor clicks are intercepted only for paths this router can render. */
function onDocumentClick(event) {
  if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
  const link = event.target.closest?.("a[href]");
  // Bare `data-link` attributes stringify to "", so test presence, not truthiness.
  if (!link || !link.hasAttribute("data-link") || link.target === "_blank") return;
  const url = new URL(link.href, window.location.origin);
  if (url.origin !== window.location.origin || !match(url.pathname)) return;
  event.preventDefault();
  navigate(`${url.pathname}${url.search}`);
}

export function start(entries) {
  table = entries.map((entry) => ({ ...entry, ...compile(entry.path) }));
  window.addEventListener("popstate", () => apply(location.pathname + location.search));
  document.addEventListener("click", onDocumentClick);
  apply(location.pathname + location.search);
}
