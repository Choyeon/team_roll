/* Admin screens for accounts, sessions, audit trail, export and system health. */

import { api } from "../lib/api.js";
import { run, tryLoad } from "../lib/action.js";
import { can, loadSession } from "../lib/store.js";
import { ROLE_LABEL, bytes, dateTime, duration, jsonDetail, number } from "../lib/format.js";
import { defineComponent, onMounted, ref } from "../lib/vue.js";
import {
  Alert,
  AppModal,
  Busy,
  ConfirmDialog,
  ListCard,
  PageHead,
  Pager,
  StatusPill,
} from "../components/ui.js";

const ROLES = [
  { value: "super", label: "超级管理员（可管理账号）" },
  { value: "admin", label: "管理员（可管理活动与记录）" },
  { value: "viewer", label: "只读（仅查看仪表盘）" },
];

function emptyAdmin() {
  return { username: "", password: "", display_name: "", role: "admin" };
}

export const AdminsView = defineComponent({
  name: "AdminsView",
  components: { Alert, AppModal, ConfirmDialog, ListCard, PageHead, StatusPill },
  setup() {
    const items = ref([]);
    const loading = ref(true);
    const error = ref("");
    const editing = ref(null);
    const form = ref(emptyAdmin());
    const formError = ref("");
    const busy = ref(false);
    const removing = ref(null);

    async function load() {
      loading.value = true;
      const payload = await tryLoad(error, () => api.get("/admin/admins"));
      if (payload) items.value = payload;
      loading.value = false;
    }

    function openCreate() {
      editing.value = { mode: "create", id: null };
      form.value = emptyAdmin();
      formError.value = "";
    }

    function openEdit(admin) {
      editing.value = { mode: "edit", id: admin.id };
      form.value = {
        username: admin.username,
        password: "",
        display_name: admin.display_name,
        role: admin.role,
        is_active: admin.is_active,
      };
      formError.value = "";
    }

    async function save() {
      formError.value = "";
      const payload = {
        display_name: form.value.display_name.trim(),
        role: form.value.role,
      };
      if (form.value.password) {
        if (form.value.password.length < 10) {
          formError.value = "密码至少 10 个字符";
          return;
        }
        payload.password = form.value.password;
      }
      if (editing.value.mode === "create") {
        if (!/^[A-Za-z0-9][A-Za-z0-9_.-]{2,63}$/.test(form.value.username.trim())) {
          formError.value = "用户名需以字母或数字开头，仅允许字母、数字、下划线、点和连字符，长度 3-64";
          return;
        }
        if (!form.value.password) {
          formError.value = "新建账号必须设置初始密码";
          return;
        }
        payload.username = form.value.username.trim();
      } else {
        payload.is_active = form.value.is_active;
      }
      busy.value = true;
      const action =
        editing.value.mode === "create"
          ? () => api.post("/admin/admins", payload)
          : () => api.patch(`/admin/admins/${editing.value.id}`, payload);
      const result = await run(action, editing.value.mode === "create" ? "账号已创建" : "账号已更新");
      busy.value = false;
      if (!result) {
        formError.value = "保存失败：请检查用户名是否重复，或是否触发了「最后一个超级管理员」保护。";
        return;
      }
      editing.value = null;
      load();
    }

    async function remove() {
      const result = await run(() => api.del(`/admin/admins/${removing.value.id}`));
      removing.value = null;
      if (result) load();
    }

    onMounted(load);
    return {
      items, loading, error, editing, form, formError, busy, removing, ROLES,
      load, openCreate, openEdit, save, remove, ROLE_LABEL, dateTime, number, can,
    };
  },
  template: `
    <section class="admin__section stack">
      <PageHead title="管理员账号" subtitle="仅超级管理员可见；停用账号会立即下线其全部会话。">
        <button v-if="can('manage_admins')" class="btn" type="button" @click="load">刷新</button>
        <button v-if="can('manage_admins')" class="btn btn--primary" type="button" @click="openCreate">新建账号</button>
      </PageHead>

      <Alert v-if="!can('manage_admins')" tone="warning"
             text="当前角色无权管理账号，请联系超级管理员。"/>

      <ListCard v-else title="管理员列表" :count="items.length" :loading="loading"
               loading-text="正在加载账号…" :error="error" empty-text="还没有账号。" @retry="load">
        <table class="table">
          <caption class="sr-only">管理员列表</caption>
          <thead>
            <tr><th>用户名</th><th class="is-secondary">昵称</th><th>角色</th><th>状态</th><th>最近登录</th><th class="is-secondary">失败次数</th><th></th></tr>
          </thead>
          <tbody>
            <tr v-for="admin in items" :key="admin.id">
              <td data-label="用户名" class="strong">{{ admin.username }}</td>
              <td data-label="昵称" class="is-secondary">{{ admin.display_name || '—' }}</td>
              <td data-label="角色"><StatusPill :value="admin.role === 'super' ? 'brand' : 'neutral'" :label="ROLE_LABEL[admin.role]"/></td>
              <td data-label="状态"><StatusPill :value="admin.is_active ? 'valid' : 'void'" :label="admin.is_active ? '启用' : '停用'"/></td>
              <td data-label="最近登录" class="multi nowrap">{{ admin.last_login_at ? dateTime(admin.last_login_at) : '从未' }}<span class="cell-sub mono">{{ admin.last_login_ip || '' }}</span></td>
              <td data-label="失败次数" class="num is-secondary">
                {{ number(admin.failed_login_count) }}
                <span v-if="admin.locked_until" class="cell-sub">锁定至 {{ dateTime(admin.locked_until) }}</span>
              </td>
              <td>
                <div class="table__actions">
                  <button class="btn btn--sm" type="button" @click="openEdit(admin)">编辑</button>
                  <button class="btn btn--sm btn--danger" type="button" @click="removing = admin">删除</button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </ListCard>

      <AppModal v-if="editing" :title="editing.mode === 'create' ? '新建账号' : '编辑账号'" @close="editing = null">
        <div class="stack">
          <label class="field">
            <span class="field__label">用户名</span>
            <input id="ad-username" class="input" v-model="form.username" :disabled="editing.mode === 'edit'" maxlength="64" autocomplete="off">
          </label>
          <label class="field">
            <span class="field__label">昵称</span>
            <input id="ad-display" class="input" v-model="form.display_name" maxlength="80">
          </label>
          <div class="form-grid">
            <label class="field">
              <span class="field__label">角色</span>
              <select id="ad-role" class="select" v-model="form.role">
                <option v-for="role in ROLES" :key="role.value" :value="role.value">{{ role.label }}</option>
              </select>
            </label>
            <label class="field">
              <span class="field__label">{{ editing.mode === 'create' ? '初始密码' : '重置密码（留空不改）' }}</span>
              <input id="ad-password" class="input" type="password" v-model="form.password" minlength="10" autocomplete="new-password">
            </label>
          </div>
          <label class="checkbox" v-if="editing.mode === 'edit'">
            <input id="ad-active" type="checkbox" v-model="form.is_active">
            <span>账号启用（停用会立即下线其会话）</span>
          </label>
          <p class="faint text-xs">密码使用 pbkdf2_sha256 加盐存储；连续登录失败会临时锁定账号。</p>
          <Alert v-if="formError" tone="danger" :text="formError"/>
        </div>
        <template #footer>
          <button class="btn" type="button" @click="editing = null">取消</button>
          <button class="btn btn--primary" type="button" :disabled="busy" @click="save">{{ busy ? '保存中…' : '保存' }}</button>
        </template>
      </AppModal>

      <ConfirmDialog v-if="removing" title="删除账号"
        :message="'将删除管理员「' + removing.username + '」及其会话，历史审计记录会保留。'"
        confirm-label="删除" @result="(ok) => ok ? remove() : removing = null"/>
    </section>`,
});

export const SessionsView = defineComponent({
  name: "SessionsView",
  components: { ListCard, PageHead, StatusPill },
  setup() {
    const items = ref([]);
    const loading = ref(true);
    const error = ref("");

    async function load() {
      loading.value = true;
      const payload = await tryLoad(error, () => api.get("/admin/sessions"));
      if (payload) items.value = payload;
      loading.value = false;
    }

    async function revoke(session) {
      if (await run(() => api.del(`/admin/sessions/${session.id}`))) load();
    }

    async function revokeOthers() {
      if (await run(() => api.del("/admin/sessions"))) load();
    }

    onMounted(load);
    return { items, loading, error, load, revoke, revokeOthers, dateTime, can };
  },
  template: `
    <section class="admin__section stack">
      <PageHead title="在线会话" subtitle="同一账号只保留最新会话。这里可以强制下线其他设备。">
        <button class="btn" type="button" @click="load">刷新</button>
        <button v-if="can('manage')" class="btn btn--danger" type="button" @click="revokeOthers">下线我的其他会话</button>
      </PageHead>

      <ListCard title="会话列表" :count="items.length" :loading="loading"
                loading-text="正在加载会话…" :error="error" empty-text="没有活跃会话。" @retry="load">
        <table class="table">
          <caption class="sr-only">会话列表</caption>
          <thead><tr><th>账号</th><th>IP</th><th class="is-secondary">登录时间</th><th>最近活动</th><th class="is-secondary">过期</th><th>设备</th><th></th></tr></thead>
          <tbody>
            <tr v-for="session in items" :key="session.id">
              <td data-label="账号">{{ session.username }}<StatusPill v-if="session.current" value="brand" label="当前"/></td>
              <td data-label="IP" class="mono faint">{{ session.ip || '—' }}</td>
              <td data-label="登录时间" class="nowrap is-secondary">{{ dateTime(session.created_at) }}</td>
              <td data-label="最近活动" class="nowrap">{{ dateTime(session.last_seen_at) }}</td>
              <td data-label="过期" class="nowrap is-secondary">{{ dateTime(session.expires_at) }}</td>
              <td data-label="设备" class="cell-sub--wide truncate" :title="session.user_agent">{{ session.user_agent || '—' }}</td>
              <td>
                <div class="table__actions">
                  <button v-if="!session.current && can('manage')" class="btn btn--sm btn--danger" type="button" @click="revoke(session)">强制下线</button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </ListCard>
    </section>`,
});

export const AuditView = defineComponent({
  name: "AuditView",
  components: { ConfirmDialog, ListCard, PageHead, Pager },
  setup() {
    const items = ref([]);
    const meta = ref({ page: 1, pages: 1, total: 0, page_size: 50 });
    const actions = ref([]);
    const filters = ref({ q: "", action: "", actor: "", date_from: "", date_to: "" });
    const loading = ref(true);
    const error = ref("");
    const purging = ref(false);
    const purgeDays = ref(90);

    async function load(page = 1) {
      loading.value = true;
      const payload = await tryLoad(error, () => api.get("/admin/audit-logs", { ...filters.value, page, page_size: 50 }));
      if (payload) {
        items.value = payload.items;
        meta.value = payload.meta;
      }
      loading.value = false;
    }

    async function loadActions() {
      const payload = await api.get("/admin/audit-actions").catch(() => null);
      if (payload) actions.value = payload.actions;
    }

    async function purge() {
      const result = await run(() => api.post("/admin/maintenance/audit/purge", undefined, { days: purgeDays.value }));
      purging.value = false;
      if (result) load(1);
    }

    onMounted(() => {
      loadActions();
      load(1);
    });
    return { items, meta, actions, filters, loading, error, purging, purgeDays, load, purge, dateTime, jsonDetail, number, can };
  },
  template: `
    <section class="admin__section stack">
      <PageHead title="审计日志" subtitle="记录建活动、改规则、作废记录、账号变更等管理动作。">
        <a class="btn" href="/api/v1/admin/export/audit.csv" download>导出 CSV</a>
        <button v-if="can('dangerous')" class="btn btn--danger" type="button" @click="purging = true">清理旧日志</button>
      </PageHead>

      <div class="filters card">
        <label class="field">
          <span class="field__label">关键词</span>
          <input id="au-q" class="input" v-model="filters.q" type="search" placeholder="对象 ID / 详情" @keyup.enter="load(1)">
        </label>
        <label class="field">
          <span class="field__label">操作</span>
          <select id="au-action" class="select" v-model="filters.action" @change="load(1)">
            <option value="">全部</option>
            <option v-for="action in actions" :key="action" :value="action">{{ action }}</option>
          </select>
        </label>
        <label class="field">
          <span class="field__label">管理员</span>
          <input id="au-actor" class="input" v-model="filters.actor" maxlength="64" @keyup.enter="load(1)">
        </label>
        <label class="field">
          <span class="field__label">起始日期</span>
          <input id="au-from" class="input" type="date" v-model="filters.date_from" @change="load(1)">
        </label>
        <label class="field">
          <span class="field__label">结束日期</span>
          <input id="au-to" class="input" type="date" v-model="filters.date_to" @change="load(1)">
        </label>
        <button class="btn" type="button" @click="load(1)">查询</button>
      </div>

      <ListCard :count="items.length" :loading="loading" loading-text="正在加载日志…"
                :error="error" empty-text="没有符合条件的日志。" @retry="load(1)">
        <template #head><span class="muted text-xs">共 {{ number(meta.total) }} 条</span></template>
        <table class="table">
          <caption class="sr-only">审计日志</caption>
          <thead><tr><th>时间</th><th>操作</th><th>管理员</th><th class="is-secondary">对象</th><th class="is-secondary">IP</th><th>详情</th></tr></thead>
          <tbody>
            <tr v-for="row in items" :key="row.id">
              <td data-label="时间" class="nowrap">{{ dateTime(row.created_at) }}</td>
              <td data-label="操作" class="mono">{{ row.action }}</td>
              <td data-label="管理员">{{ row.actor_label }}</td>
              <td data-label="对象" class="mono faint is-secondary">{{ row.target_type }}<template v-if="row.target_id"> · {{ row.target_id }}</template></td>
              <td data-label="IP" class="mono faint is-secondary">{{ row.ip || '—' }}</td>
              <td data-label="详情"><details v-if="row.detail"><summary class="faint">查看</summary>
                <pre class="audit-detail">{{ jsonDetail(row.detail) }}</pre></details><span v-else>—</span></td>
            </tr>
          </tbody>
        </table>
      </ListCard>

      <Pager v-if="meta.pages > 1" :meta="meta" @go="load"/>

      <ConfirmDialog v-if="purging" title="清理审计日志" :danger="true" confirm-label="清理"
        :message="'将删除 ' + purgeDays + ' 天前的全部审计日志，导出前请确认已备份。'"
        @result="(ok) => ok ? purge() : purging = false">
        <template #default>
          <p class="muted">将删除 {{ purgeDays }} 天前的全部审计日志，导出前请确认已备份。</p>
          <label class="field">
            <span class="field__label">保留天数</span>
            <input id="pu-days" class="input" type="number" v-model.number="purgeDays" min="7" max="3650">
          </label>
        </template>
      </ConfirmDialog>
    </section>`,
});

export const ExportView = defineComponent({
  name: "ExportView",
  components: { Alert, PageHead },
  setup() {
    const activities = ref([]);
    const activityId = ref("");
    const rollStatus = ref("all");
    const error = ref("");

    async function load() {
      error.value = "";
      const payload = await tryLoad(error, () => api.get("/admin/activities", { page_size: 100 }));
      if (payload) activities.value = payload.items;
    }

    onMounted(load);

    function rollsUrl() {
      const query = new URLSearchParams({ status: rollStatus.value });
      if (activityId.value) query.set("activity_id", activityId.value);
      return `/api/v1/admin/export/rolls.csv?${query}`;
    }

    return { activities, activityId, rollStatus, error, load, rollsUrl };
  },
  template: `
    <section class="admin__section stack">
      <PageHead title="数据导出" subtitle="CSV 带 UTF-8 BOM，Excel 直接打开不乱码；快照 JSON 适合做迁移备份。"/>

      <Alert v-if="error" tone="danger" :text="error">
        <template #actions>
          <button class="btn btn--sm" type="button" @click="load">重试</button>
        </template>
      </Alert>

      <div class="export-grid">
        <div class="card stack-tight">
          <h2>活动清单</h2>
          <p class="muted">全部活动及统计字段。</p>
          <a class="btn btn--primary" href="/api/v1/admin/export/activities.csv" download>下载 activities.csv</a>
        </div>
        <div class="card stack-tight">
          <h2>Roll 记录</h2>
          <label class="field">
            <span class="field__label">活动</span>
            <select id="ex-activity" class="select" v-model="activityId">
              <option value="">全部活动</option>
              <option v-for="item in activities" :key="item.id" :value="item.id">{{ item.name }}</option>
            </select>
          </label>
          <label class="field">
            <span class="field__label">状态</span>
            <select id="ex-status" class="select" v-model="rollStatus">
              <option value="all">全部</option>
              <option value="valid">仅有效</option>
              <option value="void">仅作废</option>
            </select>
          </label>
          <a class="btn btn--primary" :href="rollsUrl()" download>下载 rolls.csv</a>
        </div>
        <div class="card stack-tight">
          <h2>审计日志</h2>
          <p class="muted">全部管理操作流水。</p>
          <a class="btn btn--primary" href="/api/v1/admin/export/audit.csv" download>下载 audit-log.csv</a>
        </div>
        <div class="card stack-tight">
          <h2>完整快照</h2>
          <p class="muted">活动 + Roll 历史的 JSON，可跨环境恢复。</p>
          <a class="btn btn--primary" href="/api/v1/admin/export/snapshot.json" download>下载 snapshot.json</a>
        </div>
      </div>
    </section>`,
});

export const SystemView = defineComponent({
  name: "SystemView",
  components: { Alert, Busy, PageHead },
  setup() {
    const info = ref(null);
    const loading = ref(true);
    const error = ref("");
    const password = ref({ current_password: "", new_password: "", confirm: "" });
    const passwordError = ref("");
    const busy = ref(false);

    async function load() {
      loading.value = true;
      const payload = await tryLoad(error, () => api.get("/admin/system"));
      if (payload) info.value = payload;
      loading.value = false;
    }

    async function changePassword() {
      passwordError.value = "";
      if (password.value.new_password.length < 10) {
        passwordError.value = "新密码至少 10 个字符";
        return;
      }
      if (password.value.new_password !== password.value.confirm) {
        passwordError.value = "两次输入的新密码不一致";
        return;
      }
      busy.value = true;
      const result = await run(
        () =>
          api.post("/auth/password", {
            current_password: password.value.current_password,
            new_password: password.value.new_password,
          }),
        "密码已更新，其他会话已下线",
      );
      busy.value = false;
      if (!result) {
        passwordError.value = "更新失败：请确认当前密码是否正确（连续错误可能触发锁定）。";
        return;
      }
      password.value = { current_password: "", new_password: "", confirm: "" };
      await loadSession();
      load();
    }

    async function cleanup() {
      await run(() => api.post("/admin/maintenance/sessions/cleanup"));
      load();
    }

    onMounted(load);
    return { info, loading, error, load, password, passwordError, busy, changePassword, cleanup,
      bytes, duration, number, dateTime, can };
  },
  template: `
    <section class="admin__section stack">
      <PageHead title="系统状态" subtitle="运行参数、数据库体量与安全策略。">
        <a class="btn" href="/healthz" target="_blank" rel="noopener">健康检查</a>
        <button class="btn" type="button" @click="load">刷新</button>
        <button v-if="can('dangerous')" class="btn" type="button" @click="cleanup">清理过期会话</button>
      </PageHead>

      <Busy v-if="loading" text="正在读取系统信息…"/>
      <Alert v-else-if="error" tone="danger" :text="error">
        <template #actions>
          <button class="btn btn--sm" type="button" @click="load">重试</button>
        </template>
      </Alert>
      <div v-else-if="info" class="grid-2">
        <div class="card stack-tight">
          <p class="panel-title">运行环境</p>
          <dl class="defs">
            <div><dt>应用</dt><dd class="strong">{{ info.app_name }} {{ info.version }}</dd></div>
            <div><dt>环境</dt><dd>{{ info.environment }}{{ info.debug ? '（调试模式）' : '' }}</dd></div>
            <div><dt>Python</dt><dd class="mono">{{ info.python_version }}</dd></div>
            <div><dt>已运行</dt><dd>{{ duration(info.uptime_seconds) }}</dd></div>
            <div><dt>服务器时间</dt><dd>{{ dateTime(info.server_time) }}</dd></div>
            <div><dt>实时连接</dt><dd>{{ number(info.websocket_connections) }}</dd></div>
          </dl>
        </div>
        <div class="card stack-tight">
          <p class="panel-title">安全策略</p>
          <ul class="muted">
            <li>会话有效期 {{ number(info.session_ttl_minutes) }} 分钟，密码 pbkdf2_sha256 加盐存储</li>
            <li>登录限流：{{ number(info.rate_limits.login_per_window) }} 次 / {{ number(info.rate_limits.login_window_seconds) }} 秒</li>
            <li>Roll 限流：{{ number(info.rate_limits.roll_per_window) }} 次 / {{ number(info.rate_limits.roll_window_seconds) }} 秒</li>
            <li>写操作要求 CSRF 双重提交，Cookie 为 HttpOnly + SameSite</li>
          </ul>
        </div>
        <div class="card stack-tight">
          <p class="panel-title">数据库（{{ info.database.url_scheme }} · {{ bytes(info.database.file_size_bytes) }}）</p>
          <ul class="legend legend--stack">
            <li v-for="(count, table) in info.database.tables" :key="table" class="row row--between">
              <span class="mono">{{ table }}</span><span class="mono strong">{{ number(count) }}</span>
            </li>
          </ul>
        </div>
        <div class="card stack-tight">
          <p class="panel-title">修改我的密码</p>
          <label class="field">
            <span class="field__label">当前密码</span>
            <input id="sy-current" class="input" type="password" v-model="password.current_password" autocomplete="current-password">
          </label>
          <label class="field">
            <span class="field__label">新密码</span>
            <input id="sy-new" class="input" type="password" v-model="password.new_password" autocomplete="new-password" minlength="10">
          </label>
          <label class="field">
            <span class="field__label">确认新密码</span>
            <input id="sy-confirm" class="input" type="password" v-model="password.confirm" autocomplete="new-password" minlength="10">
          </label>
          <Alert v-if="passwordError" tone="danger" :text="passwordError"/>
          <button class="btn btn--primary" type="button" :disabled="busy" @click="changePassword">更新密码</button>
          <p class="faint text-xs">修改成功后其他设备的会话会被撤销。</p>
        </div>
      </div>
    </section>`,
});
