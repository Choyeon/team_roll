/* Public screens: activity list, the roll page, login. */

import { api } from "../lib/api.js";
import { login, notify } from "../lib/store.js";
import { navigate, params as routeParams } from "../lib/router.js";
import { STATUS_LABEL, dateTime, number, percent } from "../lib/format.js";
import { openActivitySocket } from "../lib/ws.js";
import { computed, defineComponent, onBeforeUnmount, onMounted, ref, watch } from "../lib/vue.js";
import { Busy, EmptyState, Pager, StatusPill } from "../components/ui.js";

const SPIN_MS = 900;
const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

function sortRolls(list) {
  return [...list].sort((a, b) => b.number - a.number).map((roll, index) => ({ ...roll, rank: index + 1 }));
}

export const HomeView = defineComponent({
  name: "HomeView",
  components: { Busy, EmptyState, Pager, StatusPill },
  setup() {
    const items = ref([]);
    const meta = ref({ page: 1, pages: 1, total: 0, page_size: 20 });
    const status = ref("");
    const q = ref("");
    const loading = ref(true);
    const error = ref("");
    let searchTimer = null;

    async function load(page = 1) {
      loading.value = true;
      error.value = "";
      try {
        const data = await api.get("/activities", { status: status.value, q: q.value, page, page_size: 12 });
        items.value = data.items;
        meta.value = data.meta;
      } catch (err) {
        error.value = err.message;
      } finally {
        loading.value = false;
      }
    }

    function search() {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => load(1), 250);
    }

    onMounted(() => load());
    const ratio = (activity) => {
      const size = activity.roll_max - activity.roll_min + 1;
      return size ? Math.min(1, activity.roll_count / size) : 0;
    };
    return { items, meta, status, q, loading, error, load, search, ratio, STATUS_LABEL, dateTime, number, percent };
  },
  template: `
    <div class="page stack">
      <section class="hero stack-tight">
        <h1 class="hero__title">团队 Roll 点</h1>
        <p class="hero__lead">管理员创建活动并设定数值区间，队友在同一个页面 Roll 点，结果按数值从高到低实时排行。
          每人可参与次数、区间上限都由活动规则决定，作废的数值会自动释放。</p>
        <p class="faint" style="font-size:var(--text-xs)">共 {{ meta.total }} 个公开活动 · 数据接口
          <a href="/api/v1/activities" rel="noopener">/api/v1/activities</a></p>
      </section>

      <div class="row row--between">
        <div class="tabs" role="tablist" aria-label="按状态筛选">
          <button class="tab" role="tab" v-for="tab in [['', '全部'], ['active', '进行中'], ['paused', '已暂停'], ['ended', '已结束']]"
                  :key="tab[0]" type="button" :aria-current="status === tab[0]" @click="status = tab[0]; load(1)">{{ tab[1] }}</button>
        </div>
        <label class="field" style="min-width:12rem">
          <span class="sr-only">搜索活动</span>
          <input class="input" v-model="q" type="search" placeholder="搜索活动名称…" @input="search">
        </label>
      </div>

      <Busy v-if="loading" text="正在加载活动…"/>
      <p v-else-if="error" class="pill pill--ended">{{ error }}</p>
      <EmptyState v-else-if="!items.length" text="没有符合条件的活动，换个筛选条件试试。"/>

      <div v-else class="grid-cards">
        <article v-for="activity in items" :key="activity.id" class="card activity-card">
          <div class="activity-card__head">
            <h2 style="margin:0;font-size:var(--text-lg)">
              <a :href="'/activity/' + activity.id" data-link>{{ activity.name }}</a>
            </h2>
            <StatusPill :value="activity.status" :label="STATUS_LABEL[activity.status]"/>
          </div>
          <p v-if="activity.description" class="muted truncate" style="margin:0">{{ activity.description }}</p>
          <ul class="activity-card__meta" style="margin:0;list-style:none;padding:0">
            <li>区间 {{ number(activity.roll_min) }}-{{ number(activity.roll_max) }}</li>
            <li>已 Roll {{ number(activity.roll_count) }}</li>
            <li>剩余 {{ number(activity.remaining_numbers) }}</li>
            <li>最高 {{ activity.top_number === null ? '—' : number(activity.top_number) }}</li>
            <li>每人 {{ activity.max_participations }} 次</li>
          </ul>
          <div class="bar" role="img" :aria-label="'完成度 ' + percent(ratio(activity))">
            <div class="bar__fill" :style="{ width: percent(ratio(activity)) }"></div>
          </div>
        </article>
      </div>

      <Pager v-if="meta.pages > 1" :meta="meta" @go="load"/>
    </div>`,
});

export const ActivityView = defineComponent({
  name: "ActivityView",
  components: { Busy, StatusPill },
  setup() {
    const activity = ref(null);
    const rolls = ref([]);
    const loading = ref(true);
    const missing = ref(false);
    const name = ref(localStorage.getItem("team-roll-name") || "");
    const busy = ref(false);
    const spinning = ref(false);
    const display = ref("");
    const mine = ref(null);
    const fresh = ref("");
    const socketStatus = ref("connecting");
    const connections = ref(0);
    let socket = null;
    let spinTimer = null;

    const id = computed(() => routeParams.value.activity_id);
    const range = computed(() => {
      if (!activity.value) return { size: 0, filled: 0 };
      const size = activity.value.roll_max - activity.value.roll_min + 1;
      return { size, filled: activity.value.roll_count, ratio: size ? activity.value.roll_count / size : 0 };
    });
    const canRoll = computed(
      () => activity.value && activity.value.status === "active" && !busy.value && !spinning.value,
    );
    const blockReason = computed(() => {
      if (!activity.value) return "";
      if (activity.value.status === "ended") return "活动已结束，榜单保持最终状态。";
      if (activity.value.status === "paused") return "活动已暂停，稍后再来试试。";
      if (range.value.filled >= range.value.size) return "所有数值已被 Roll 完，等待管理员作废或调整区间。";
      return "";
    });

    function applyRoll(result) {
      const others = rolls.value.filter((roll) => roll.id !== result.id);
      rolls.value = sortRolls([...others, result]);
      fresh.value = result.id;
      setTimeout(() => {
        if (fresh.value === result.id) fresh.value = "";
      }, 1800);
    }

    function resyncTotals() {
      if (!activity.value) return;
      activity.value = {
        ...activity.value,
        roll_count: rolls.value.length,
        remaining_numbers: Math.max(0, range.value.size - rolls.value.length),
        top_number: rolls.value.length ? rolls.value[0].number : null,
      };
    }

    function onFrame(frame) {
      switch (frame.type) {
        case "hello":
          activity.value = frame.activity;
          rolls.value = sortRolls(frame.rolls);
          connections.value = frame.connections;
          break;
        case "roll_result":
          applyRoll(frame.result);
          resyncTotals();
          break;
        case "roll_updated":
          if (frame.result.status === "valid") applyRoll(frame.result);
          else rolls.value = sortRolls(rolls.value.filter((roll) => roll.id !== frame.result.id));
          resyncTotals();
          break;
        case "roll_deleted":
          rolls.value = sortRolls(rolls.value.filter((roll) => roll.id !== frame.result_id));
          resyncTotals();
          break;
        case "activity_updated":
        case "activity_status":
          activity.value = { ...activity.value, ...frame.activity };
          break;
        case "activity_deleted":
          missing.value = true;
          activity.value = null;
          break;
        default:
          break;
      }
    }

    async function load() {
      loading.value = true;
      missing.value = false;
      try {
        const data = await api.get(`/activities/${id.value}`);
        activity.value = data;
        rolls.value = sortRolls(await api.get(`/activities/${id.value}/rolls`, { status: "valid", order: "number" }));
      } catch (err) {
        if (err.status === 404 || err.status === 410) missing.value = true;
        else notify(err.message, "error");
      } finally {
        loading.value = false;
      }
    }

    function spin() {
      if (reducedMotion) return;
      const { roll_min: min, roll_max: max } = activity.value;
      spinning.value = true;
      const started = performance.now();
      const tick = () => {
        display.value = String(Math.floor(min + Math.random() * (max - min + 1)));
        if (performance.now() - started < SPIN_MS) spinTimer = requestAnimationFrame(tick);
        else spinning.value = false;
      };
      spinTimer = requestAnimationFrame(tick);
    }

    async function rollTheDice() {
      const trimmed = name.value.trim();
      if (!trimmed) {
        notify("请先输入你的名字", "warn");
        return;
      }
      localStorage.setItem("team-roll-name", trimmed);
      busy.value = true;
      mine.value = null;
      const min = activity.value.roll_min;
      const max = activity.value.roll_max;
      spin();
      try {
        const data = await api.post(`/activities/${id.value}/rolls`, { name: trimmed });
        mine.value = data.roll;
        applyRoll(data.roll);
        activity.value = { ...activity.value, ...data.activity };
        display.value = String(data.roll.number);
      } catch (err) {
        display.value = "";
        notify(err.message, "error", 6000);
      } finally {
        cancelAnimationFrame(spinTimer);
        spinning.value = false;
        busy.value = false;
      }
    }

    function connect() {
      socket?.close();
      // The `hello` frame re-snapshots the board after every (re)connect.
      socket = openActivitySocket(id.value, {
        onMessage: onFrame,
        onStatus: (value) => {
          socketStatus.value = value;
        },
      });
    }

    onMounted(() => {
      load();
      connect();
    });

    onBeforeUnmount(() => {
      socket?.close();
      cancelAnimationFrame(spinTimer);
    });

    watch(id, () => {
      display.value = "";
      mine.value = null;
      load();
      connect();
    });

    return {
      activity, rolls, loading, missing, name, busy, spinning, display, mine, fresh,
      socketStatus, connections, range, canRoll, blockReason, load, rollTheDice,
      STATUS_LABEL, dateTime, number, percent,
    };
  },
  template: `
    <div class="page">
      <Busy v-if="loading" text="正在加载活动…"/>
      <section v-else-if="missing" class="card center stack-tight">
        <h1>活动不存在</h1>
        <p class="muted">该活动可能已被删除。回到列表看看正在开放的其他活动。</p>
        <a class="btn btn--primary" href="/" data-link>返回活动列表</a>
      </section>

      <div v-else-if="activity" class="stack">
        <header class="row row--between">
          <div class="stack-tight">
            <div class="row">
              <h1 style="margin:0">{{ activity.name }}</h1>
              <StatusPill :value="activity.status" :label="STATUS_LABEL[activity.status]"/>
            </div>
            <p class="muted" style="margin:0">
              区间 {{ number(activity.roll_min) }}-{{ number(activity.roll_max) }} · 每人最多 {{ activity.max_participations }} 次 ·
              创建于 {{ dateTime(activity.created_at) }}
            </p>
          </div>
          <a class="btn btn--ghost" href="/" data-link>返回列表</a>
        </header>

        <p v-if="activity.description" class="card muted" style="margin:0">{{ activity.description }}</p>

        <div v-if="blockReason" class="pill pill--paused" role="status">{{ blockReason }}</div>

        <div class="roll-hero">
          <section class="card rollbox" aria-label="Roll 点">
            <div class="rollbox__display" :data-state="spinning ? 'spinning' : (display ? 'revealed' : 'idle')"
                 aria-live="polite" aria-atomic="true">{{ display || (activity.roll_min + '-' + activity.roll_max) }}</div>
            <p class="rollbox__range" v-if="mine">{{ mine.name }} 的数值是 {{ number(mine.number) }}，当前排名第 {{ mine.rank }}</p>
            <label class="field" style="width:100%">
              <span class="field__label">你的名字</span>
              <input id="player-name" class="input" v-model="name" maxlength="32" autocomplete="nickname"
                     placeholder="队名/ID" @keyup.enter="canRoll && rollTheDice()">
            </label>
            <button class="btn btn--primary btn--roll" type="button" :disabled="!canRoll" @click="rollTheDice">
              <span v-if="busy" class="spinner" aria-hidden="true"></span>
              {{ busy ? 'Roll 中…' : (display ? '再 Roll 一次' : '开始 Roll 点') }}
            </button>
            <div class="row" style="justify-content:center;font-size:var(--text-xs)">
              <span class="presence">
                <span class="dot" :class="socketStatus === 'online' ? 'dot--on' : 'dot--off'" aria-hidden="true"></span>
                {{ socketStatus === 'online' ? '实时同步已连接' : '实时同步重连中' }} · 在线 {{ connections }} 人
              </span>
            </div>
          </section>

          <section class="card card--pad-none">
            <div class="card__head">
              <h2 style="margin:0;font-size:var(--text-lg)">实时排行</h2>
              <span class="muted" style="font-size:var(--text-xs)">
                已占用 {{ number(range.filled) }}/{{ number(range.size) }}（{{ percent(range.ratio) }}）
              </span>
            </div>
            <div class="board card__body">
              <ol class="board__list">
                <li v-for="roll in rolls" :key="roll.id" class="board__row" :data-new="fresh === roll.id">
                  <span class="board__rank">#{{ roll.rank }}</span>
                  <span class="truncate">{{ roll.name }}</span>
                  <span class="board__number">{{ number(roll.number) }}</span>
                </li>
              </ol>
              <p v-if="!rolls.length" class="muted center" style="padding:var(--space-5)">还没有人 Roll 点，等你开第一枪。</p>
            </div>
          </section>
        </div>
      </div>

      <section v-else class="card center">
        <p class="muted">加载失败。</p>
        <button class="btn" type="button" @click="load">重试</button>
      </section>
    </div>`,
});

export const LoginView = defineComponent({
  name: "LoginView",
  setup() {
    const username = ref("");
    const password = ref("");
    const error = ref("");
    const busy = ref(false);

    async function submit() {
      busy.value = true;
      error.value = "";
      try {
        const me = await login(username.value.trim(), password.value);
        password.value = "";
        notify(`欢迎回来，${me.display_name || me.username}`, "success");
        const next = new URLSearchParams(location.search).get("next") || "/admin";
        navigate(next.startsWith("/") ? next : "/admin", { replace: true });
      } catch (err) {
        error.value = err.message;
      } finally {
        busy.value = false;
      }
    }

    return { username, password, error, busy, submit };
  },
  template: `
    <div class="page page--narrow">
      <form class="card login-card stack" @submit.prevent="submit" aria-labelledby="login-title">
        <h1 id="login-title" style="margin:0">管理员登录</h1>
        <p class="muted" style="margin:0">登录后可查看仪表盘、管理活动与 Roll 记录。</p>
        <label class="field">
          <span class="field__label">用户名</span>
          <input id="username" class="input" v-model="username" autocomplete="username" required maxlength="64">
        </label>
        <label class="field">
          <span class="field__label">密码</span>
          <input id="password" class="input" type="password" v-model="password" autocomplete="current-password" required>
        </label>
        <p v-if="error" class="field__error" role="alert">{{ error }}</p>
        <button class="btn btn--primary btn-block" type="submit" :disabled="busy">
          <span v-if="busy" class="spinner" aria-hidden="true"></span>{{ busy ? '登录中…' : '登录' }}
        </button>
        <p class="faint" style="font-size:var(--text-xs);margin:0">多次密码错误会临时锁定账户，这是正常的防暴力破解策略。</p>
      </form>
    </div>`,
});

export const NotFoundView = defineComponent({
  name: "NotFoundView",
  template: `
    <div class="page center stack-tight">
      <h1>页面不存在</h1>
      <p class="muted">地址可能输错了，或者该页面已下线。</p>
      <a class="btn btn--primary" href="/" data-link>返回活动列表</a>
    </div>`,
});
