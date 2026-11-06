/* Admin shell plus the operational screens: dashboard, activities, rolls. */

import { api } from "../lib/api.js";
import { run } from "../lib/action.js";
import { can, notify, store } from "../lib/store.js";
import { navigate, params as routeParams, query as routeQuery } from "../lib/router.js";
import {
  ROLL_STATUS_LABEL,
  STATUS_LABEL,
  dateTime,
  number,
  percent,
  utcOffsetMinutes,
} from "../lib/format.js";
import { computed, defineComponent, onBeforeUnmount, onMounted, ref } from "../lib/vue.js";
import { BarChart, DonutChart, TrendChart } from "../components/charts.js";
import { AppModal, Busy, ConfirmDialog, EmptyState, Pager, StatusPill } from "../components/ui.js";

const STATUS_COLORS = { active: "var(--success)", paused: "var(--warning)", ended: "var(--danger)" };

/** The admin navigation table, shared by the shell and the standalone form pages. */
export const ADMIN_SECTIONS = [
  { key: "dashboard", label: "仪表盘", capability: "read" },
  { key: "activities", label: "活动管理", capability: "read" },
  { key: "rolls", label: "Roll 记录", capability: "read" },
  { key: "admins", label: "管理员", capability: "manage_admins" },
  { key: "sessions", label: "在线会话", capability: "manage" },
  { key: "audit", label: "审计日志", capability: "manage" },
  { key: "export", label: "数据导出", capability: "manage" },
  { key: "system", label: "系统状态", capability: "read" },
];

export const AdminNav = defineComponent({
  name: "AdminNav",
  props: { active: { type: String, default: "dashboard" } },
  setup() {
    const sections = computed(() => ADMIN_SECTIONS.filter((item) => allowed(item.capability)));
    return { sections };
  },
  template: `
    <nav class="admin__nav" aria-label="管理后台导航">
      <a v-for="item in sections" :key="item.key"
         :href="item.key === 'dashboard' ? '/admin' : '/admin/' + item.key" data-link
         :aria-current="active === item.key ? 'page' : null">{{ item.label }}</a>
    </nav>`,
});

export function allowed(capability) {
  return capability === "read" || Boolean(store.me && store.me.capabilities.includes(capability));
}

function emptyActivity() {
  return {
    name: "",
    description: "",
    roll_min: 1,
    roll_max: 100,
    max_participations: 1,
    max_participants: 0,
  };
}

export const DashboardView = defineComponent({
  name: "DashboardView",
  components: { BarChart, Busy, DonutChart, TrendChart, StatusPill },
  setup() {
    const data = ref(null);
    const rooms = ref({});
    const loading = ref(true);
    const days = ref(14);
    let timer = null;

    async function load() {
      loading.value = !data.value;
      const payload = await run(() =>
        api.get("/admin/dashboard", { trend_days: days.value, tz_offset_minutes: utcOffsetMinutes() }),
      );
      if (payload) data.value = payload;
      loading.value = false;
    }

    async function loadRooms() {
      const payload = await api.get("/admin/dashboard/rooms").catch(() => null);
      if (payload) rooms.value = payload.rooms;
    }

    onMounted(() => {
      load();
      loadRooms();
      timer = setInterval(() => {
        load();
        loadRooms();
      }, 60000);
    });
    onBeforeUnmount(() => clearInterval(timer));

    const segments = computed(() =>
      (data.value?.status_breakdown ?? []).map((row) => ({
        label: STATUS_LABEL[row.status] || row.status,
        value: row.activities,
        color: STATUS_COLORS[row.status] || "var(--chart-1)",
      })),
    );
    const topBars = computed(() =>
      (data.value?.top_activities ?? []).map((row) => ({
        label: row.name,
        value: row.roll_count,
        display: `${row.roll_count} · ${percent(row.completion)}`,
      })),
    );
    const roomList = computed(() => Object.entries(rooms.value));

    return { data, days, loading, load, segments, topBars, roomList, number, percent, dateTime, refresh: load };
  },
  template: `
    <section class="admin__section stack">
      <div class="page-head">
        <div>
          <h1 style="margin:0">仪表盘</h1>
          <p class="muted" style="margin:0">汇总 Roll 点活动、参与度与实时连接。</p>
        </div>
        <div class="row">
          <label class="field">
            <span class="sr-only">趋势统计天数</span>
            <select class="select" v-model.number="days" @change="refresh">
              <option :value="7">近 7 天</option>
              <option :value="14">近 14 天</option>
              <option :value="30">近 30 天</option>
            </select>
          </label>
          <button class="btn" type="button" @click="refresh">刷新</button>
        </div>
      </div>

      <Busy v-if="loading" text="正在统计…"/>
      <template v-else-if="data">
        <div class="kpi-grid">
          <div class="card metric">
            <span class="metric__hint">活动总数</span>
            <span class="metric__value">{{ number(data.kpis.activities_total) }}</span>
            <span class="metric__hint">进行中 {{ data.kpis.activities_active }} · 已结束 {{ data.kpis.activities_ended }}</span>
          </div>
          <div class="card metric">
            <span class="metric__hint">Roll 记录</span>
            <span class="metric__value">{{ number(data.kpis.rolls_total) }}</span>
            <span class="metric__hint">有效 {{ data.kpis.rolls_valid }} · 作废 {{ data.kpis.rolls_void }}</span>
          </div>
          <div class="card metric">
            <span class="metric__hint">参与人数</span>
            <span class="metric__value">{{ number(data.kpis.participants_unique) }}</span>
            <span class="metric__hint">今日 {{ data.kpis.rolls_today }} 次 · 近 7 天 {{ data.kpis.rolls_last_7_days }} 次</span>
          </div>
          <div class="card metric">
            <span class="metric__hint">区间平均填充率</span>
            <span class="metric__value">{{ percent(data.kpis.avg_fill_rate, 1) }}</span>
            <span class="metric__hint">中位数 {{ percent(data.kpis.median_fill_rate, 1) }}</span>
          </div>
          <div class="card metric">
            <span class="metric__hint">实时连接</span>
            <span class="metric__value">{{ number(data.live_connections) }}</span>
            <span class="metric__hint">{{ roomList.length ? '' : '当前没有在线房间' }}</span>
          </div>
        </div>

        <div class="card">
          <p class="panel-title">每日 Roll 点趋势</p>
          <TrendChart :data="data.trend"/>
        </div>

        <div class="grid-2">
          <div class="card">
            <p class="panel-title">活动状态分布</p>
            <DonutChart :segments="segments"/>
          </div>
          <div class="card">
            <p class="panel-title">最活跃的活动</p>
            <BarChart :data="topBars"/>
          </div>
        </div>

        <div class="grid-2">
          <div class="card card--pad-none">
            <div class="card__head"><h2 style="margin:0;font-size:var(--text-lg)">最新 Roll 记录</h2></div>
            <div class="table-wrap">
              <table class="table">
                <thead><tr><th>时间</th><th>玩家</th><th class="num">数值</th><th>活动</th></tr></thead>
                <tbody>
                  <tr v-for="roll in data.recent_rolls" :key="roll.id">
                    <td class="nowrap">{{ dateTime(roll.timestamp) }}</td>
                    <td>{{ roll.name }}</td>
                    <td class="num">{{ number(roll.number) }}</td>
                    <td><a :href="'/activity/' + roll.activity_id" data-link class="truncate" style="display:inline-block;max-width:12rem">{{ roll.activity_name }}</a></td>
                  </tr>
                </tbody>
              </table>
              <EmptyState v-if="!data.recent_rolls.length" text="还没有 Roll 记录。"/>
            </div>
          </div>
          <div class="card card--pad-none">
            <div class="card__head"><h2 style="margin:0;font-size:var(--text-lg)">最新管理操作</h2></div>
            <div class="table-wrap">
              <table class="table">
                <thead><tr><th>时间</th><th>操作</th><th>管理员</th><th>对象</th></tr></thead>
                <tbody>
                  <tr v-for="row in data.recent_audit" :key="row.id">
                    <td class="nowrap">{{ dateTime(row.created_at) }}</td>
                    <td class="mono">{{ row.action }}</td>
                    <td>{{ row.actor_label }}</td>
                    <td class="mono faint">{{ row.target_id || '—' }}</td>
                  </tr>
                </tbody>
              </table>
              <EmptyState v-if="!data.recent_audit.length" text="暂无审计记录。"/>
            </div>
          </div>
        </div>
      </template>
    </section>`,
});

export const ActivitiesView = defineComponent({
  name: "ActivitiesView",
  components: { Busy, ConfirmDialog, Pager, StatusPill },
  setup() {
    const items = ref([]);
    const meta = ref({ page: 1, pages: 1, total: 0, page_size: 20 });
    const status = ref("");
    const q = ref("");
    const loading = ref(true);
    const removing = ref(null);

    async function load(page = meta.value.page) {
      loading.value = true;
      const payload = await run(() => api.get("/admin/activities", { status: status.value, q: q.value, page, page_size: 20 }));
      if (payload) {
        items.value = payload.items;
        meta.value = payload.meta;
      }
      loading.value = false;
    }

    async function setStatus(activity, next) {
      const label = STATUS_LABEL[next];
      const result = await run(() => api.put(`/admin/activities/${activity.id}/status`, { status: next }), `已切换到「${label}」`);
      if (result) load();
    }

    async function remove() {
      const result = await run(() => api.del(`/admin/activities/${removing.value.id}`));
      removing.value = null;
      if (result) load();
    }

    onMounted(() => load(1));
    return {
      items, meta, status, q, loading, removing,
      load, setStatus, remove,
      STATUS_LABEL, dateTime, number, percent, can,
    };
  },
  template: `
    <section class="admin__section stack">
      <div class="page-head">
        <div>
          <h1 style="margin:0">活动管理</h1>
          <p class="muted" style="margin:0">创建、调整规则、暂停/结束活动，或删除整份 Roll 历史。</p>
        </div>
        <a v-if="can('manage')" class="btn btn--primary" href="/admin/activities/new" data-link>新建活动</a>
      </div>

      <div class="filters card">
        <label class="field">
          <span class="field__label">状态</span>
          <select class="select" v-model="status" @change="load(1)">
            <option value="">全部</option>
            <option value="active">进行中</option>
            <option value="paused">已暂停</option>
            <option value="ended">已结束</option>
          </select>
        </label>
        <label class="field" style="flex:1 1 12rem">
          <span class="field__label">关键词</span>
          <input class="input" v-model="q" type="search" placeholder="名称 / 描述 / ID" @keyup.enter="load(1)">
        </label>
        <button class="btn" type="button" @click="load(1)">查询</button>
      </div>

      <Busy v-if="loading" text="正在加载活动…"/>
      <div v-else class="card card--pad-none">
        <div class="table-wrap">
          <table class="table">
            <caption class="sr-only">活动列表</caption>
            <thead>
              <tr>
                <th>活动</th><th>状态</th><th class="num">区间</th><th class="num">有效</th>
                <th class="num">作废</th><th class="num">人数</th><th class="num">最高</th><th class="num">完成度</th>
                <th>创建</th><th></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="activity in items" :key="activity.id">
                <td>
                  <a :href="'/activity/' + activity.id" data-link class="strong">{{ activity.name }}</a>
                  <div class="faint mono" style="font-size:var(--text-2xs)">{{ activity.id }}</div>
                </td>
                <td><StatusPill :value="activity.status" :label="STATUS_LABEL[activity.status]"/></td>
                <td class="num">{{ number(activity.roll_min) }}-{{ number(activity.roll_max) }}</td>
                <td class="num">{{ number(activity.roll_count) }}</td>
                <td class="num">{{ number(activity.void_count) }}</td>
                <td class="num">{{ number(activity.participants) }}<span v-if="activity.max_participants" class="faint">/{{ number(activity.max_participants) }}</span></td>
                <td class="num">{{ activity.top_number ?? '—' }}</td>
                <td class="num">{{ percent(activity.roll_count / (activity.roll_max - activity.roll_min + 1)) }}</td>
                <td class="nowrap">{{ activity.created_by || '—' }}<div class="faint">{{ dateTime(activity.created_at) }}</div></td>
                <td>
                  <div class="table__actions" v-if="can('manage')">
                    <a class="btn btn--sm" :href="'/admin/activities/' + activity.id + '/edit'" data-link>编辑</a>
                    <button v-if="activity.status === 'active'" class="btn btn--sm" type="button" @click="setStatus(activity, 'paused')">暂停</button>
                    <button v-if="activity.status === 'paused'" class="btn btn--sm" type="button" @click="setStatus(activity, 'active')">恢复</button>
                    <button v-if="activity.status !== 'ended'" class="btn btn--sm" type="button" @click="setStatus(activity, 'ended')">结束</button>
                    <button v-if="activity.status === 'ended'" class="btn btn--sm" type="button" @click="setStatus(activity, 'active')">重开</button>
                    <a class="btn btn--sm" :href="'/admin/rolls?activity=' + activity.id" data-link>Roll</a>
                    <button v-if="can('dangerous')" class="btn btn--sm btn--danger" type="button" @click="removing = activity">删除</button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <EmptyState v-if="!items.length" text="没有活动，点右上角新建一个。"/>
      </div>

      <Pager v-if="meta.pages > 1" :meta="meta" @go="load"/>

      <ConfirmDialog v-if="removing" title="删除活动"
        :message="'将永久删除「' + removing.name + '」及其 ' + removing.roll_count + ' 条 Roll 记录，无法恢复。'"
        confirm-label="删除" @result="(ok) => ok ? remove() : removing = null"/>
    </section>`,
});

/**
 * Standalone create/edit page for an activity. It used to live in a modal,
 * which cramped five rules plus their explanations into a floating box.
 */
export const ActivityFormView = defineComponent({
  name: "ActivityFormView",
  components: { AdminNav, Busy },
  setup() {
    const activityId = computed(() => routeParams.value.activity_id || "");
    const isEdit = computed(() => Boolean(activityId.value));
    const loading = ref(isEdit.value);
    const current = ref(null);
    const form = ref(emptyActivity());
    const formError = ref("");
    const busy = ref(false);

    async function load() {
      if (!isEdit.value) return;
      loading.value = true;
      const payload = await run(() => api.get(`/admin/activities/${activityId.value}`));
      if (payload) {
        current.value = payload;
        form.value = {
          name: payload.name,
          description: payload.description,
          roll_min: payload.roll_min,
          roll_max: payload.roll_max,
          max_participations: payload.max_participations,
          max_participants: payload.max_participants,
        };
      }
      loading.value = false;
    }

    async function save() {
      formError.value = "";
      if (!form.value.name.trim()) {
        formError.value = "活动名称不能为空";
        return;
      }
      if (Number(form.value.roll_max) < Number(form.value.roll_min)) {
        formError.value = "最大值不能小于最小值";
        return;
      }
      const payload = {
        name: form.value.name.trim(),
        description: form.value.description.trim(),
        roll_min: Number(form.value.roll_min),
        roll_max: Number(form.value.roll_max),
        max_participations: Number(form.value.max_participations),
        max_participants: Number(form.value.max_participants),
      };
      busy.value = true;
      const action = isEdit.value
        ? () => api.patch(`/admin/activities/${activityId.value}`, payload)
        : () => api.post("/admin/activities", payload);
      const result = await run(action, isEdit.value ? "活动已更新" : "活动已创建");
      busy.value = false;
      if (!result) {
        formError.value = "保存失败：区间收窄会被已有数值挡住，名额已满时先作废记录。";
        return;
      }
      navigate("/admin/activities");
    }

    onMounted(load);
    return {
      activityId, isEdit, loading, current, form, formError, busy, save,
      STATUS_LABEL, number, can,
    };
  },
  template: `
    <div class="admin">
      <AdminNav active="activities"/>
      <section class="admin__section stack">
        <div class="page-head">
          <div>
            <h1 style="margin:0">{{ isEdit ? '编辑活动' : '新建活动' }}</h1>
            <p class="muted" style="margin:0">
              <template v-if="current">
                {{ current.name }} · {{ STATUS_LABEL[current.status] }} ·
                已有 {{ number(current.roll_count) }} 条有效数值、{{ number(current.participants) }} 人参与
              </template>
              <template v-else>规则保存后立即对参与页生效。</template>
            </p>
          </div>
          <div class="row">
            <a v-if="current" class="btn btn--ghost" :href="'/activity/' + activityId" data-link>查看参与页</a>
            <a class="btn btn--ghost" href="/admin/activities" data-link>返回列表</a>
          </div>
        </div>

        <Busy v-if="loading" text="正在加载活动…"/>

        <p v-else-if="isEdit && !current" class="card muted">活动不存在或已被删除，返回列表看看其他活动。</p>

        <form v-else-if="can('manage')" class="card stack" @submit.prevent="save">
          <label class="field">
            <span class="field__label">名称</span>
            <input id="af-name" class="input" v-model="form.name" maxlength="80" required autocomplete="off">
          </label>
          <label class="field">
            <span class="field__label">描述（可选）</span>
            <textarea id="af-desc" class="textarea" v-model="form.description" maxlength="2000"></textarea>
          </label>

          <p class="panel-title">Roll 规则</p>
          <div class="form-grid">
            <label class="field">
              <span class="field__label">最小值</span>
              <input id="af-min" class="input" type="number" v-model="form.roll_min" min="0" step="1" required>
            </label>
            <label class="field">
              <span class="field__label">最大值</span>
              <input id="af-max" class="input" type="number" v-model="form.roll_max" min="1" step="1" required>
            </label>
            <label class="field">
              <span class="field__label">每人可 Roll 次数</span>
              <input id="af-quota" class="input" type="number" v-model="form.max_participations" min="1" max="20" step="1" required>
              <span class="field__hint">同一个人最多能占几个数值。</span>
            </label>
            <label class="field">
              <span class="field__label">参与人数上限</span>
              <input id="af-people" class="input" type="number" v-model="form.max_participants" min="0" max="1000" step="1" required>
              <span class="field__hint">填 0 表示不限人数；满员后只有已上榜的人还能继续 Roll。</span>
            </label>
          </div>

          <p class="faint" style="font-size:var(--text-xs);margin:0">
            收窄区间时，若已有数值落在新范围外会被拒绝；先作废这些记录再保存。
            调低人数上限不会踢掉已经在榜的人，只是不再放新人进来。
          </p>
          <p v-if="formError" class="field__error" role="alert">{{ formError }}</p>

          <div class="row row--end">
            <a class="btn" href="/admin/activities" data-link>取消</a>
            <button class="btn btn--primary" type="submit" :disabled="busy">
              <span v-if="busy" class="spinner" aria-hidden="true"></span>{{ busy ? '保存中…' : '保存' }}
            </button>
          </div>
        </form>

        <p v-else class="pill pill--paused" role="status">当前角色无权修改活动，请联系管理员。</p>
      </section>
    </div>`,
});

export const RollsView = defineComponent({
  name: "RollsView",
  components: { AppModal, Busy, ConfirmDialog, EmptyState, StatusPill },
  setup() {
    const activities = ref([]);
    const activityId = ref(routeQuery.value.activity || "");
    const status = ref("valid");
    const order = ref("number");
    const rolls = ref([]);
    const loading = ref(false);
    const editing = ref(null);
    const voiding = ref(null);
    const removing = ref(null);
    const busy = ref(false);

    const activity = computed(() => activities.value.find((item) => item.id === activityId.value) || null);

    async function loadActivities() {
      const payload = await run(() => api.get("/admin/activities", { page_size: 100 }));
      if (payload) activities.value = payload.items;
    }

    async function load() {
      if (!activityId.value) {
        rolls.value = [];
        return;
      }
      loading.value = true;
      const payload = await run(() =>
        api.get(`/admin/activities/${activityId.value}/rolls`, { status: status.value, order: order.value }),
      );
      if (payload) rolls.value = payload.rolls;
      loading.value = false;
    }

    function select() {
      navigate(`/admin/rolls${activityId.value ? `?activity=${activityId.value}` : ""}`, { replace: true });
      load();
    }

    function openAdd() {
      editing.value = { mode: "create", id: "", name: "", number: activity.value?.roll_min ?? 1, reason: "" };
    }

    function openEdit(roll) {
      editing.value = { mode: "edit", id: roll.id, name: roll.name, number: roll.number, reason: "" };
    }

    async function save() {
      if (!editing.value.name.trim()) return;
      busy.value = true;
      const body = {
        name: editing.value.name.trim(),
        number: Number(editing.value.number),
        reason: editing.value.reason.trim(),
      };
      const action =
        editing.value.mode === "create"
          ? () => api.post(`/admin/activities/${activityId.value}/rolls`, body)
          : () => api.patch(`/admin/rolls/${editing.value.id}`, body);
      const result = await run(action, editing.value.mode === "create" ? "已补录 Roll 记录" : "记录已更新");
      busy.value = false;
      if (!result) return;
      editing.value = null;
      load();
    }

    async function confirmVoid() {
      busy.value = true;
      const result = await run(
        () => api.put(`/admin/rolls/${voiding.value.id}/void`, { reason: voiding.value.reason.trim() }),
        "记录已作废，数值已释放",
      );
      busy.value = false;
      if (result) {
        voiding.value = null;
        load();
      }
    }

    async function restore(roll) {
      if (await run(() => api.put(`/admin/rolls/${roll.id}/restore`), "记录已恢复")) load();
    }

    async function remove() {
      busy.value = true;
      const result = await run(() => api.del(`/admin/rolls/${removing.value.id}`));
      busy.value = false;
      removing.value = null;
      if (result) load();
    }

    onMounted(async () => {
      await loadActivities();
      if (!activityId.value && activities.value.length) {
        activityId.value = activities.value[0].id;
        select();
      }
      load();
    });

    return {
      activities, activityId, activity, status, order, rolls, loading, editing, voiding, removing, busy,
      select, load, openAdd, openEdit, save, confirmVoid, restore, remove,
      ROLL_STATUS_LABEL, dateTime, number, can,
    };
  },
  template: `
    <section class="admin__section stack">
      <div class="page-head">
        <div>
          <h1 style="margin:0">Roll 记录</h1>
          <p class="muted" style="margin:0">这里可以作废、恢复、改名、改数值，或直接删除单条记录。</p>
        </div>
        <button v-if="can('manage') && activityId" class="btn btn--primary" type="button" @click="openAdd">补录记录</button>
      </div>

      <div class="filters card">
        <label class="field" style="flex:1 1 16rem">
          <span class="field__label">活动</span>
          <select id="r-activity" class="select" v-model="activityId" @change="select">
            <option value="" disabled>请选择活动</option>
            <option v-for="item in activities" :key="item.id" :value="item.id">
              {{ item.name }}（{{ item.roll_count }} 条）
            </option>
          </select>
        </label>
        <label class="field">
          <span class="field__label">状态</span>
          <select id="r-status" class="select" v-model="status" @change="load">
            <option value="valid">有效</option>
            <option value="void">已作废</option>
            <option value="all">全部</option>
          </select>
        </label>
        <label class="field">
          <span class="field__label">排序</span>
          <select id="r-order" class="select" v-model="order" @change="load">
            <option value="number">按数值</option>
            <option value="time">按时间</option>
            <option value="name">按名字</option>
          </select>
        </label>
        <button class="btn" type="button" @click="load">刷新</button>
      </div>

      <p v-if="!activityId" class="muted">先选择一个活动。</p>
      <Busy v-else-if="loading" text="正在加载记录…"/>
      <div v-else class="card card--pad-none">
        <div class="table-wrap">
          <table class="table">
            <caption class="sr-only">Roll 记录</caption>
            <thead>
              <tr>
                <th class="num">排名</th><th>玩家</th><th class="num">数值</th><th>状态</th>
                <th>时间</th><th>IP / 浏览器</th><th>备注</th><th></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="roll in rolls" :key="roll.id">
                <td class="num">{{ roll.rank || '—' }}</td>
                <td>{{ roll.name }}</td>
                <td class="num strong">{{ number(roll.number) }}</td>
                <td><StatusPill :value="roll.status" :label="ROLL_STATUS_LABEL[roll.status]"/></td>
                <td class="nowrap">{{ dateTime(roll.timestamp) }}</td>
                <td class="mono faint">{{ roll.ip || '—' }}
                  <div class="truncate" style="font-size:var(--text-2xs);max-width:22rem"
                       :title="roll.user_agent">{{ roll.user_agent || '' }}</div>
                </td>
                <td class="faint">{{ roll.void_reason || (roll.created_by ? '由 ' + roll.created_by + ' 补录' : '') }}</td>
                <td>
                  <div class="table__actions" v-if="can('manage')">
                    <button v-if="roll.status === 'valid'" class="btn btn--sm" type="button" @click="openEdit(roll)">修改</button>
                    <button v-if="roll.status === 'valid'" class="btn btn--sm" type="button" @click="voiding = { id: roll.id, name: roll.name, number: roll.number, reason: '' }">作废</button>
                    <button v-if="roll.status === 'void'" class="btn btn--sm" type="button" @click="restore(roll)">恢复</button>
                    <button v-if="can('dangerous')" class="btn btn--sm btn--danger" type="button" @click="removing = roll">删除</button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <EmptyState v-if="!rolls.length" text="该活动没有符合条件的记录。"/>
      </div>

      <AppModal v-if="editing" :title="editing.mode === 'create' ? '补录 Roll 记录' : '修改记录'" @close="editing = null">
        <div class="stack">
          <label class="field">
            <span class="field__label">玩家名字</span>
            <input id="e-name" class="input" v-model="editing.name" maxlength="64">
          </label>
          <div class="form-grid">
            <label class="field">
              <span class="field__label">数值</span>
              <input id="e-number" class="input" type="number" v-model="editing.number" step="1"
                     :min="activity ? activity.roll_min : 0" :max="activity ? activity.roll_max : 1000000">
            </label>
            <label class="field">
              <span class="field__label">原因（写入审计日志）</span>
              <input id="e-reason" class="input" v-model="editing.reason" maxlength="200">
            </label>
          </div>
          <p class="faint" style="font-size:var(--text-xs);margin:0">
            数值需落在 {{ activity ? activity.roll_min + '-' + activity.roll_max : '活动区间' }} 内，且不能与其他有效记录重复。
          </p>
        </div>
        <template #footer>
          <button class="btn" type="button" @click="editing = null">取消</button>
          <button class="btn btn--primary" type="button" :disabled="busy" @click="save">保存</button>
        </template>
      </AppModal>

      <AppModal v-if="voiding" title="作废记录" @close="voiding = null">
        <div class="stack">
          <p class="muted" style="margin:0">作废「{{ voiding.name }}」的数值 {{ voiding.number }}，该数值会重新开放给其他人 Roll。</p>
          <label class="field">
            <span class="field__label">作废原因</span>
            <input id="v-reason" class="input" v-model="voiding.reason" maxlength="200" placeholder="例如：重复提交">
          </label>
        </div>
        <template #footer>
          <button class="btn" type="button" @click="voiding = null">取消</button>
          <button class="btn btn--danger" type="button" :disabled="busy" @click="confirmVoid">确认作废</button>
        </template>
      </AppModal>

      <ConfirmDialog v-if="removing" title="删除记录"
        :message="'将彻底删除「' + removing.name + '」的数值 ' + removing.number + '，审计日志会保留删除快照。'"
        confirm-label="删除" @result="(ok) => ok ? remove() : removing = null"/>
    </section>`,
});
