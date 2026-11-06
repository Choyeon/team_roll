/* Shared UI primitives. */

import { defineComponent, ref } from "../lib/vue.js";
import { store, dismissToast } from "../lib/store.js";

export const Toasts = defineComponent({
  name: "Toasts",
  setup: () => ({ store, dismissToast }),
  template: `
    <div class="toasts" role="region" aria-label="通知">
      <div v-for="toast in store.toasts" :key="toast.id" class="toast" :class="'toast--' + toast.type"
           :role="toast.type === 'error' ? 'alert' : 'status'">
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
  computed: {
    pages() {
      return this.meta.pages || 1;
    },
  },
  template: `
    <nav class="pager" aria-label="分页">
      <span class="muted">共 {{ meta.total }} 条 · 第 {{ meta.page }}/{{ pages }} 页</span>
      <span class="row">
        <button class="btn btn--sm" type="button" :disabled="meta.page <= 1" @click="$emit('go', meta.page - 1)">上一页</button>
        <button class="btn btn--sm" type="button" :disabled="meta.page >= pages" @click="$emit('go', meta.page + 1)">下一页</button>
      </span>
    </nav>`,
});

/** Native <dialog> wrapper: focus trapping and Escape come for free. */
export const AppModal = defineComponent({
  name: "AppModal",
  props: { title: { type: String, default: "" }, width: { type: String, default: "" } },
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
      <div class="modal__panel" :style="width ? { maxWidth: width } : null">
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
