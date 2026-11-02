/* Slot-machine digit reels: free spin while the draw is in flight, then a
   staggered left-to-right settle with a short mechanical recoil. */

import { defineComponent, onBeforeUnmount, onMounted, ref, watch } from "../lib/vue.js";

const STRIP = 20; // two 0-9 cycles so wrap-around and recoil stay inside the strip
const SPIN_DIGITS_PER_S = 12; // base free-spin speed, nudged per reel so they desync
const DELAY_MS = 170; // extra spin each successive reel gets before it starts braking
const SETTLE_MS = 560;
const RECOIL_MS = 260;
const RECOIL_DIGITS = 0.14;
const MAX_BLUR_EM = 0.05;

const easeOutCubic = (t) => 1 - (1 - t) ** 3;

export const NumberReel = defineComponent({
  name: "NumberReel",
  props: {
    digits: { type: Number, required: true },
    target: { type: String, default: "" },
    label: { type: String, default: "" },
  },
  emits: ["landed"],
  setup(props, { emit }) {
    const reels = ref([]);
    const landed = ref(false);
    let frame = null;
    let timer = null;
    let plan = null;

    function clearTimer() {
      if (timer) clearTimeout(timer);
      timer = null;
    }

    // 后台标签页不跑 rAF，用户点完就切走时靠它收尾，避免永远停在“开奖中”。
    function finish() {
      clearTimer();
      if (frame) {
        cancelAnimationFrame(frame);
        frame = null;
      }
      for (const reel of reels.value) {
        reel.pos = reel.to;
        reel.blur = 0;
      }
      if (!landed.value) {
        landed.value = true;
        emit("landed");
      }
    }

    function spinStart() {
      plan = null;
      clearTimer();
      landed.value = false;
      const now = performance.now();
      reels.value = Array.from({ length: props.digits }, (_, i) => ({
        from: Math.random() * STRIP,
        speed: SPIN_DIGITS_PER_S + i * 1.1,
        at: now,
        delay: i * DELAY_MS,
        pos0: 0,
        to: 0,
        settleAt: 0,
        pos: 0,
        blur: MAX_BLUR_EM,
      }));
      run();
      if (props.target) brake(props.target);
    }

    // Freeze each reel's braking curve onto the drawn digit: land on an exact
    // index whose digit matches, far enough ahead that the reel is still turning.
    function brake(target) {
      if (!reels.value.length) return;
      const now = performance.now();
      plan = { at: now, last: 0 };
      reels.value.forEach((reel, i) => {
        const current = reel.from + (reel.speed * (reel.delay + now - reel.at)) / 1000;
        const digit = Number(target[i] ?? "0");
        const base = Math.ceil(current + 6 + i * 4);
        reel.settleAt = now + reel.delay;
        reel.pos0 = current;
        reel.to = base + ((((digit - base) % 10) + 10) % 10);
        plan.last = Math.max(plan.last, reel.delay + SETTLE_MS);
      });
      clearTimer();
      timer = setTimeout(finish, plan.last + 700);
    }

    function state(reel, now) {
      const elapsed = now - reel.at;
      if (!plan || now < reel.settleAt) {
        const drift = (reel.speed * elapsed) / 1000;
        const ramp = plan ? Math.min(1, Math.max(0, 1 - (now - (reel.settleAt - 220)) / 220)) : 1;
        return { pos: reel.from + drift, blur: MAX_BLUR_EM * ramp };
      }
      const t = (now - reel.settleAt) / SETTLE_MS;
      if (t < 1) {
        return { pos: reel.pos0 + (reel.to - reel.pos0) * easeOutCubic(t), blur: MAX_BLUR_EM * (1 - t) ** 2 };
      }
      const u = (now - reel.settleAt - SETTLE_MS) / RECOIL_MS;
      if (u < 1) {
        return { pos: reel.to + RECOIL_DIGITS * Math.exp(-4 * u) * Math.sin(u * 9), blur: 0 };
      }
      return { pos: reel.to, blur: 0 };
    }

    function run() {
      frame = requestAnimationFrame((now) => {
        for (const reel of reels.value) {
          const next = state(reel, now);
          reel.pos = next.pos;
          reel.blur = next.blur;
        }
        if (plan && !landed.value && now - plan.at >= plan.last) {
          landed.value = true;
          emit("landed");
        }
        if (plan && now - plan.at >= plan.last + RECOIL_MS) {
          finish();
          return;
        }
        run();
      });
    }

    watch(() => props.target, (target) => { if (target && !plan) brake(target); });
    onMounted(spinStart);
    onBeforeUnmount(() => {
      if (frame) cancelAnimationFrame(frame);
      clearTimer();
    });

    return { reels, landed, STRIP };
  },
  // 滚轮本身是装饰性的；真正的播报交给读屏友好的那句 sr-only 文本。
  template: `
    <span class="reels" aria-hidden="true">
      <span v-for="(reel, i) in reels" :key="i" class="reel">
        <span class="reel__strip"
              :style="{ transform: 'translateY(-' + ((reel.pos % 10) / STRIP) * 100 + '%)',
                        filter: reel.blur ? 'blur(' + reel.blur.toFixed(3) + 'em)' : 'none' }">
          <span v-for="n in STRIP" :key="n" class="reel__item">{{ (n - 1) % 10 }}</span>
        </span>
      </span>
    </span>
    <span v-if="landed" class="sr-only">开奖结果 {{ label }}</span>`,
});
