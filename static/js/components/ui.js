/* Shared UI primitives. */

import { defineComponent, ref } from "../lib/vue.js";
import { number } from "../lib/format.js";
import { store, dismissToast } from "../lib/store.js";

export const Toasts = defineComponent({
  name: "Toasts",
  setup: () => ({ store, dismissToast }),
  template: `
    <div class="toasts" role="region" aria-label="通知">
      <div v-for="toast in store.toasts" :key="toast.id" class="toast" :class="'toast--' + toast.type"
           :role="toast.type === 'danger' ? 'alert' : 'status'">
        <span>{{ toast.text }}</span>
        <button class="toast__close" type="button" aria-label="关闭通知" @click="dismissToast(toast.id)">×</button>
      </div>
    </div>`,
});

export const StatusPill = defineComponent({
  name: "StatusPill",
  props: { value: { type: String, default: "" }, label: { type: String, default: "" } },
  computed: {
    text() {
      return this.label || this.value;
    },
  },
  template: `<span class="pill" :class="'pill--' + value">{{ text }}</span>`,
});

export const EmptyState = defineComponent({
  name: "EmptyState",
  props: { text: { type: String, default: "暂无数据" } },
  template: `<div class="state"><div class="state__icon" aria-hidden="true">◇</div><p>{{ text }}</p><slot/></div>`,
});

export const Busy = defineComponent({
  name: "Busy",
  props: { text: { type: String, default: "加载中…" } },
  template: `<div class="state"><span class="spinner" aria-hidden="true"></span> <span>{{ text }}</span></div>`,
});

export const Pager = defineComponent({
  name: "Pager",
  props: { meta: { type: Object, required: true } },
  emits: ["go"],
  setup: () => ({ number }),
  computed: {
    pages() {
      return this.meta.pages || 1;
    },
  },
  template: `
    <nav class="pager" aria-label="分页">
      <span class="muted">共 {{ number(meta.total) }} 条 · 第 {{ meta.page }}/{{ pages }} 页</span>
      <span class="row">
        <button class="btn btn--sm" type="button" :disabled="meta.page <= 1" @click="$emit('go', meta.page - 1)">上一页</button>
        <button class="btn btn--sm" type="button" :disabled="meta.page >= pages" @click="$emit('go', meta.page + 1)">下一页</button>
      </span>
    </nav>`,
});

/** 页面内常驻提示：色调词和 toast 共用一套（info / success / warning / danger）。 */
export const Alert = defineComponent({
  name: "Alert",
  props: {
    tone: { type: String, default: "info" },
    text: { type: String, default: "" },
  },
  template: `
    <div class="alert" :class="'alert--' + tone" :role="tone === 'danger' ? 'alert' : 'status'">
      <span class="alert__body"><slot>{{ text }}</slot></span>
      <span class="alert__actions" v-if="$slots.actions"><slot name="actions"></slot></span>
    </div>`,
});

/** 页面标题区：标题 + 状态徽章 + 说明，操作永远在右侧一行。 */
export const PageHead = defineComponent({
  name: "PageHead",
  props: {
    title: { type: String, default: "" },
    subtitle: { type: String, default: "" },
  },
  template: `
    <div class="page-head">
      <div class="stack-tight">
        <div class="row">
          <h1><slot name="title">{{ title }}</slot></h1>
          <slot name="badge"></slot>
        </div>
        <p class="muted" v-if="subtitle || $slots.subtitle"><slot name="subtitle">{{ subtitle }}</slot></p>
      </div>
      <div class="row" v-if="$slots.default"><slot></slot></div>
    </div>`,
});

/** 一组关键数字，前台详情页和后台仪表盘共用同一个结构与字号。 */
export const Metric = defineComponent({
  name: "Metric",
  props: {
    label: { type: String, default: "" },
    value: { type: [String, Number], default: "" },
    hint: { type: String, default: "" },
  },
  template: `
    <div class="card metric">
      <span class="metric__hint">{{ label }}</span>
      <span class="metric__value">{{ value }}</span>
      <span class="metric__hint" v-if="hint">{{ hint }}</span>
      <slot></slot>
    </div>`,
});

/**
 * 列表卡片：加载中出提示，加载失败出可重试的错误条，空了只出空状态（不再留一行空表头），
 * 有内容才把表格放进横向滚动容器。
 * count 由调用方给，因为 v-for 渲染出的空插槽没法从 $slots 判断。
 */
export const ListCard = defineComponent({
  name: "ListCard",
  components: { Alert, Busy, EmptyState },
  props: {
    title: { type: String, default: "" },
    count: { type: Number, default: 0 },
    loading: { type: Boolean, default: false },
    loadingText: { type: String, default: "加载中…" },
    error: { type: String, default: "" },
    emptyText: { type: String, default: "暂无数据" },
  },
  emits: ["retry"],
  template: `
    <div class="card card--pad-none">
      <div class="card__head" v-if="title || $slots.head">
        <h2 v-if="title">{{ title }}</h2>
        <slot name="head"></slot>
      </div>
      <Busy v-if="loading" :text="loadingText"/>
      <Alert v-else-if="error" tone="danger" :text="error">
        <template #actions>
          <button class="btn btn--sm" type="button" @click="$emit('retry')">重试</button>
        </template>
      </Alert>
      <EmptyState v-else-if="!count" :text="emptyText"><slot name="action"></slot></EmptyState>
      <div v-else class="table-wrap"><slot></slot></div>
    </div>`,
});

/** Native <dialog> wrapper: focus trapping and Escape come for free. */
export const AppModal = defineComponent({
  name: "AppModal",
  props: { title: { type: String, default: "" } },
  setup() {
    const dialog = ref(null);
    return { dialog };
  },
  mounted() {
    if (this.dialog && !this.dialog.open) this.dialog.showModal();
  },
  methods: {
    close() {
      this.$emit("close");
    },
  },
  emits: ["close"],
  template: `
    <dialog class="modal" ref="dialog" :aria-label="title || '对话框'" @close="close" @click.self="close">
      <div class="modal__panel">
        <div class="card__head">
          <h2>{{ title }}</h2>
          <button class="btn btn--ghost btn--sm" type="button" aria-label="关闭" @click="close">×</button>
        </div>
        <div class="card__body"><slot></slot></div>
        <div class="card__foot"><slot name="footer"></slot></div>
      </div>
    </dialog>`,
});

export const ConfirmDialog = defineComponent({
  name: "ConfirmDialog",
  props: {
    title: { type: String, default: "确认操作" },
    message: { type: String, default: "该操作不可撤销。" },
    danger: { type: Boolean, default: true },
    confirmLabel: { type: String, default: "确认" },
    busy: { type: Boolean, default: false },
  },
  emits: ["result"],
  components: { AppModal },
  template: `
    <AppModal :title="title" @close="$emit('result', false)">
      <div class="stack">
        <slot>
          <p class="muted">{{ message }}</p>
        </slot>
      </div>
      <template #footer>
        <button class="btn" type="button" :disabled="busy" @click="$emit('result', false)">取消</button>
        <button class="btn" :class="danger ? 'btn--danger' : 'btn--primary'" type="button" :disabled="busy"
                @click="$emit('result', true)">{{ busy ? '处理中…' : confirmLabel }}</button>
      </template>
    </AppModal>`,
});
