/* Application root: shell chrome, route table, auth guard, toasts. */

import { cycleTheme, initTheme, loadSession, logout, notify, store } from "./lib/store.js";
import { navigate, route, start } from "./lib/router.js";
import { computed, createApp, defineComponent, h } from "./lib/vue.js";
import { ActivityView, HomeView, LoginView, NotFoundView } from "./views/public.js";
import {
  ADMIN_SECTIONS,
  ActivitiesView,
  ActivityFormView,
  AdminNav,
  DashboardView,
  RollsView,
  allowed,
} from "./views/admin_core.js";
import { AdminsView, AuditView, ExportView, SessionsView, SystemView } from "./views/admin_manage.js";
import { Toasts } from "./components/ui.js";

const SECTION_VIEWS = {
  dashboard: DashboardView,
  activities: ActivitiesView,
  rolls: RollsView,
  admins: AdminsView,
  sessions: SessionsView,
  audit: AuditView,
  export: ExportView,
  system: SystemView,
};

const AdminShellView = defineComponent({
  name: "AdminShellView",
  setup() {
    const active = computed(() => {
      const key = route.value?.params.section || "dashboard";
      const found = ADMIN_SECTIONS.find((item) => item.key === key);
      return found && allowed(found.capability) ? found : null;
    });
    return { active };
  },
  render() {
    if (!this.active) return h(NotFoundView);
    return h("div", { class: "admin" }, [
      h(AdminNav, { active: this.active.key }),
      h(SECTION_VIEWS[this.active.key]),
    ]);
  },
});

const AppView = defineComponent({
  name: "TeamRollApp",
  components: { NotFoundView, Toasts },
  setup() {
    const themeLabel = computed(() => ({ auto: "跟随系统", light: "浅色", dark: "深色" })[store.theme]);
    function signOut() {
      logout().then(() => {
        notify("已退出登录", "success");
        navigate("/", { replace: true });
      });
    }
    return { store, route, themeLabel, cycleTheme, signOut };
  },
  template: `
    <header class="appbar">
      <a class="appbar__brand" href="/" data-link>
        <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden="true" fill="currentColor">
          <path d="M12 2 3 6.5v11L12 22l9-4.5v-11L12 2Zm0 2.3 6.4 3.2-6.4 3.2-6.4-3.2L12 4.3ZM5 9.2l6 3v6.3l-6-3V9.2Zm8 9.3v-6.3l6-3v6.3l-6 3Z"/>
        </svg>
        <span>Team Roll</span>
      </a>
      <nav class="appbar__nav spacer" aria-label="主导航">
        <a class="btn btn--ghost btn--sm" href="/" data-link>活动列表</a>
        <a v-if="store.auth === 'authed'" class="btn btn--ghost btn--sm" href="/admin" data-link>管理后台</a>
      </nav>
      <div class="appbar__user">
        <button class="btn btn--ghost btn--sm" type="button" @click="cycleTheme" :title="'当前主题：' + themeLabel">
          {{ themeLabel }}
        </button>
        <template v-if="store.auth === 'authed'">
          <span class="muted" style="font-size:var(--text-sm)">{{ store.me.display_name || store.me.username }}</span>
          <button class="btn btn--sm" type="button" @click="signOut">退出</button>
        </template>
        <a v-else-if="store.auth === 'anon'" class="btn btn--primary btn--sm" href="/login" data-link>管理员登录</a>
      </div>
    </header>
    <main id="main">
      <component v-if="route" :is="route.view" :key="'view' + route.name + (route.params.activity_id || route.params.section || '')"/>
      <NotFoundView v-else/>
    </main>
    <footer class="page center faint" style="font-size:var(--text-xs)">
      Team Roll · Roll 点结果实时同步 · <a href="/sitemap.xml">站点地图</a> · <a href="/robots.txt">robots</a>
    </footer>
    <Toasts/>`,
});

const ROUTES = [
  { name: "home", path: "/", view: HomeView, title: "Team Roll - 团队 Roll 点工具" },
  { name: "activity", path: "/activity/:activity_id", view: ActivityView, title: "Roll 点活动 | Team Roll" },
  { name: "login", path: "/login", view: LoginView, title: "管理员登录 | Team Roll" },
  { name: "activity-new", path: "/admin/activities/new", view: ActivityFormView, title: "新建活动 | 管理后台" },
  {
    name: "activity-edit",
    path: "/admin/activities/:activity_id/edit",
    view: ActivityFormView,
    title: "编辑活动 | 管理后台",
  },
  { name: "admin", path: "/admin/:section?", view: AdminShellView, title: "管理后台 | Team Roll" },
];

function guard() {
  if (location.pathname.startsWith("/admin") && store.auth !== "authed") {
    navigate(`/login?next=${encodeURIComponent(location.pathname + location.search)}`, { replace: true });
  }
}

async function boot() {
  initTheme();
  window.addEventListener("team-roll:unauthorized", () => {
    store.me = null;
    store.auth = "anon";
    if (location.pathname.startsWith("/admin")) {
      notify("登录状态已失效，请重新登录", "warn");
      guard();
    }
  });
  window.addEventListener("team-roll:navigated", guard);

  await loadSession();
  start(ROUTES);
  guard();

  const app = createApp(AppView);
  app.config.errorHandler = (err) => {
    notify(err?.message || "界面出现异常", "error");
    console.error(err);
  };
  app.mount("#app");
}

boot().catch((err) => {
  console.error(err);
  const target = document.querySelector("#app .boot");
  if (target) target.textContent = `界面加载失败：${err?.message || err}`;
});
