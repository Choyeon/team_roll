/* Public screens: activity list, the roll page, login. */

import { api } from "../lib/api.js";
import { login, notify } from "../lib/store.js";
import { navigate, params as routeParams } from "../lib/router.js";
import { STATUS_LABEL, dateTime, number, percent } from "../lib/format.js";
import { openActivitySocket } from "../lib/ws.js";
import { computed, defineComponent, onBeforeUnmount, onMounted, ref, watch } from "../lib/vue.js";
import { NumberReel } from "../components/reel.js";
import { RibbonBurst } from "../components/burst.js";
import { tierOf } from "../lib/tier.js";
import { Busy, EmptyState, Pager, StatusPill } from "../components/ui.js";

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
    const activeTotal = ref(null);
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

    // 独立于当前筛选的一次轻量计数，让首屏能回答“现在有没有活动在跑”。
    async function loadActiveTotal() {
      try {
        const data = await api.get("/activities", { status: "active", page_size: 1 });
        activeTotal.value = data.meta.total;
      } catch {
        activeTotal.value = null;
      }
    }

    function search() {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => load(1), 250);
    }

    function showActive() {
      status.value = "active";
      load(1);
    }

    function clearFilters() {
      status.value = "";
      q.value = "";
      load(1);
    }

    onMounted(() => {
      load();
      loadActiveTotal();
    });
    const ratio = (activity) => {
      const size = activity.roll_max - activity.roll_min + 1;
      return size ? Math.min(1, activity.roll_count / size) : 0;
    };
    const filtered = computed(() => Boolean(status.value) || Boolean(q.value.trim()));
    return {
      items,
      meta,
      status,
      q,
      loading,
      error,
      activeTotal,
      filtered,
      load,
      search,
      showActive,
      clearFilters,
      ratio,
      STATUS_LABEL,
      dateTime,
      number,
      percent,
    };
  },
  template: `
    <div class="page stack">
      <section class="hero stack-tight">
        <h1 class="hero__title">团队 Roll 点</h1>
        <p class="hero__lead">管理员建一个数值区间，队友在同一个页面各领一个不重复的随机数，结果按数值从高到低实时排行。
          每人能 Roll 几次、能进多少人，都在活动规则里设；作废的数值会重新开放。</p>
        <div class="row" v-if="activeTotal">
          <button class="btn btn--primary" type="button" @click="showActive">
            参与进行中的活动 · {{ number(activeTotal) }}
          </button>
        </div>
      </section>

      <div class="row row--between">
        <div class="tabs" role="tablist" aria-label="按状态筛选">
          <button class="tab" role="tab" v-for="tab in [['', '全部'], ['active', '进行中'], ['paused', '已暂停'], ['ended', '已结束']]"
                  :key="tab[0]" type="button" :aria-current="status === tab[0]" @click="status = tab[0]; load(1)">{{ tab[1] }}</button>
        </div>
        <div class="row">
          <span class="faint" aria-live="polite" style="font-size:var(--text-xs)">共 {{ number(meta.total) }} 个</span>
          <label class="field" style="min-width:12rem">
            <span class="sr-only">搜索活动</span>
            <input class="input" v-model="q" type="search" placeholder="搜索活动名称…" @input="search">
          </label>
        </div>
      </div>

      <Busy v-if="loading" text="正在加载活动…"/>
      <p v-else-if="error" class="pill pill--ended">{{ error }}</p>
      <EmptyState v-else-if="!items.length && filtered" text="没有符合筛选条件的活动。">
        <button class="btn btn--sm" type="button" @click="clearFilters">清除筛选</button>
      </EmptyState>
      <EmptyState v-else-if="!items.length" text="还没有公开活动，管理员创建后会显示在这里。"/>

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
            <li v-if="activity.max_participants">限 {{ number(activity.max_participants) }} 人</li>
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
  components: { Busy, NumberReel, RibbonBurst, StatusPill },
  setup() {
    const activity = ref(null);
    const rolls = ref([]);
    const loading = ref(true);
    const missing = ref(false);
    const name = ref(localStorage.getItem("team-roll-name") || "");
    const busy = ref(false);
    const rolling = ref(false);
    const reeling = ref(false);
    const rollSeq = ref(0);
    const burst = ref(0);
    const reelTarget = ref("");
    const display = ref("");
    const mine = ref(null);
    const fresh = ref("");
    const socketStatus = ref("connecting");
    const connections = ref(0);
    let socket = null;

    const id = computed(() => routeParams.value.activity_id);
    const range = computed(() => {
      if (!activity.value) return { size: 0, filled: 0 };
      const size = activity.value.roll_max - activity.value.roll_min + 1;
      return { size, filled: activity.value.roll_count, ratio: size ? activity.value.roll_count / size : 0 };
    });
    const reelDigits = computed(() => (activity.value ? String(activity.value.roll_max).length : 2));
    const displayState = computed(() => {
      if (rolling.value) return "spinning";
      return display.value || reelTarget.value ? "revealed" : "idle";
    });
    // 档位只在停稳后亮起来，转动途中泄色就没有开奖的悬念了。
    const revealTier = computed(() => {
      if (rolling.value || !display.value || !activity.value) return null;
      return tierOf(Number(display.value), activity.value.roll_min, activity.value.roll_max);
    });
    const rollTier = (value) => {
      if (!activity.value) return null;
      const tier = tierOf(value, activity.value.roll_min, activity.value.roll_max);
      return tier ? tier.key : null;
    };
    const canRoll = computed(() => activity.value && activity.value.status === "active" && !busy.value && !rolling.value);
    const slotsFull = computed(
      () => activity.value && activity.value.max_participants > 0
        && activity.value.participants >= activity.value.max_participants,
    );
    const blockReason = computed(() => {
      if (!activity.value) return "";
      if (activity.value.status === "ended") return "活动已结束，榜单保持最终状态。";
      if (activity.value.status === "paused") return "活动已暂停，稍后再来试试。";
      if (range.value.filled >= range.value.size) return "所有数值已被 Roll 完，等待管理员作废或调整区间。";
      // 名额满只挡住新名字，已上榜的人还能用完自己的次数，所以按钮保持可点。
      if (slotsFull.value) return `参与名额 ${activity.value.max_participants} 人已满，只有榜上的队友还能继续 Roll。`;
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

    // 自己这一枪先压住，等滚轮停稳再上榜，免得榜单提前剧透数字。
    let pending = null;

    function commitPending() {
      if (!pending) return;
      const result = pending;
      pending = null;
      applyRoll(result);
      resyncTotals();
    }

    function resyncTotals() {
      if (!activity.value) return;
      activity.value = {
        ...activity.value,
        roll_count: rolls.value.length,
        participants: new Set(rolls.value.map((roll) => roll.name)).size,
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
          if (!pending || frame.result.id !== pending.id) {
            applyRoll(frame.result);
            resyncTotals();
          }
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

    async function rollTheDice() {
      const trimmed = name.value.trim();
      if (!trimmed) {
        notify("请先输入你的名字", "warn");
        return;
      }
      localStorage.setItem("team-roll-name", trimmed);
      busy.value = true;
      mine.value = null;
      display.value = "";
      reelTarget.value = "";
      burst.value = 0;
      if (!reducedMotion) {
        // 每次开一轮新的滚轮：:key 变更会重挂载组件并从自由转动开始。
        rollSeq.value += 1;
        reeling.value = true;
        rolling.value = true;
      }
      try {
        const data = await api.post(`/activities/${id.value}/rolls`, { name: trimmed });
        mine.value = data.roll;
        activity.value = { ...activity.value, ...data.activity };
        display.value = String(data.roll.number);
        if (reeling.value) {
          pending = data.roll;
          reelTarget.value = display.value.padStart(reelDigits.value, "0");
        } else {
          applyRoll(data.roll);
        }
      } catch (err) {
        reeling.value = false;
        rolling.value = false;
        notify(err.message, "error", 6000);
      } finally {
        busy.value = false;
        if (!reeling.value) rolling.value = false;
      }
    }

    function fireBurst() {
      if (reducedMotion) return;
      burst.value += 1;
      const seq = burst.value;
      // 粒子动画自带 forwards，收尾只是把这上百个小元素从 DOM 里撤掉。
      setTimeout(() => {
        if (burst.value === seq) burst.value = 0;
      }, 3200);
    }

    function onLanded() {
      rolling.value = false;
      commitPending();
      fireBurst();
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
    });

    watch(id, () => {
      display.value = "";
      mine.value = null;
      reeling.value = false;
      rolling.value = false;
      reelTarget.value = "";
      burst.value = 0;
      pending = null;
      load();
      connect();
    });

    return {
      activity, rolls, loading, missing, name, busy, rolling, reeling, rollSeq, reelTarget, burst,
      display, mine, fresh, socketStatus, connections, range, reelDigits, displayState, revealTier,
      rollTier, canRoll, blockReason, load, rollTheDice, onLanded,
      STATUS_LABEL, dateTime, number,
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
        <RibbonBurst v-if="burst && revealTier" :key="burst" :tier="revealTier.key"/>

        <header class="row row--between">
          <div class="stack-tight">
            <div class="row">
              <h1 style="margin:0">{{ activity.name }}</h1>
              <StatusPill :value="activity.status" :label="STATUS_LABEL[activity.status]"/>
            </div>
            <p class="muted" style="margin:0">
              区间 {{ number(activity.roll_min) }}-{{ number(activity.roll_max) }} · 每人最多 {{ activity.max_participations }} 次 ·
              <template v-if="activity.max_participants">限 {{ number(activity.max_participants) }} 人 ·</template>
              创建于 {{ dateTime(activity.created_at) }}
            </p>
          </div>
          <a class="btn btn--ghost" href="/" data-link>返回列表</a>
        </header>

        <p v-if="activity.description" class="card muted" style="margin:0">{{ activity.description }}</p>

        <div v-if="blockReason" class="pill pill--paused" role="status">{{ blockReason }}</div>

        <div class="roll-hero">
          <section class="card rollbox" :data-quake="burst ? 'true' : null" aria-label="Roll 点">
            <div class="rollbox__display" :data-state="displayState"
                 :data-tier="revealTier ? revealTier.key : null" aria-live="polite" aria-atomic="true">
              <NumberReel v-if="reeling" :key="rollSeq" :digits="reelDigits" :target="reelTarget"
                          :label="display" @landed="onLanded"/>
              <span v-else class="reveal">{{ display || '等待 Roll 点' }}</span>
            </div>
            <p class="rollbox__range" v-if="mine && !rolling">
              {{ mine.name }}：{{ number(mine.number) }}，当前第 {{ mine.rank }} 名
            </p>
            <label class="field" style="width:100%">
              <span class="field__label">你的名字</span>
              <input id="player-name" class="input" v-model="name" maxlength="32" autocomplete="nickname"
                     placeholder="队名/ID" @keyup.enter="canRoll && rollTheDice()">
            </label>
            <button class="btn btn--primary btn--roll" type="button" :disabled="!canRoll" @click="rollTheDice">
              <span v-if="busy" class="spinner" aria-hidden="true"></span>
              {{ busy ? 'Roll 中…' : (rolling ? '开奖中…' : (display ? '再 Roll 一次' : '开始 Roll 点')) }}
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
                {{ number(range.filled) }}/{{ number(range.size) }} 个数值已 Roll · {{ number(activity.participants) }} 人
              </span>
            </div>
            <div class="card__body">
              <ol class="board__list">
                <li v-for="roll in rolls" :key="roll.id" class="board__row" :data-new="fresh === roll.id"
                    :data-tier="rollTier(roll.number)">
                  <span class="board__rank">#{{ roll.rank }}</span>
                  <span class="truncate">{{ roll.name }}</span>
                  <span class="board__number">{{ number(roll.number) }}</span>
                </li>
              </ol>
              <p v-if="!rolls.length" class="muted center" style="padding:var(--space-5)">还没有人 Roll 点。</p>
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
        <p class="faint" style="font-size:var(--text-xs);margin:0">连续输错密码会临时锁定账号。</p>
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
