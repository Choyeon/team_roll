/* The Vue global build loads as a classic script; expose it to ES modules. */

const {
  computed,
  createApp,
  defineComponent,
  h,
  nextTick,
  onBeforeUnmount,
  onMounted,
  reactive,
  ref,
  watch,
} = window.Vue;

export { computed, createApp, defineComponent, h, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch };
