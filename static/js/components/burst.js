/* 开奖撒花：一整层固定覆盖视口，挂载时撒一次，父组件换 :key 就重撒。
   只在非 reduced-motion 下渲染，动画本身由 CSS 推进。 */

import { defineComponent, ref } from "../lib/vue.js";

const PALETTES = {
  white: ["#ffffff", "#e8ecff", "#c6d0ea", "#f6f8ff", "#aab6d6"],
  blue: ["#2f9bff", "#7fc4f2", "#bcdcff", "#0f6ba8", "#5fd0ff"],
  purple: ["#7b5cff", "#b9a6ff", "#ded1ff", "#4f46e5", "#c084fc"],
  pink: ["#ff3ba1", "#f286c8", "#ffc7e6", "#db2777", "#ff8fc4"],
  gold: ["#f7e37b", "#f5c56a", "#c8952a", "#fff3c4", "#eab308"],
  red: ["#ff3b3b", "#f78f8f", "#ffb1b1", "#b91c1c", "#ff6b4a"],
  rainbow: ["#ff3b3b", "#ffae00", "#35d07f", "#2f9bff", "#7b5cff", "#ff3ba1"],
};

// 从顶部落下的彩片数；档位越高铺得越满。
const DROP_COUNTS = { white: 26, blue: 34, purple: 46, pink: 58, gold: 78, red: 96, rainbow: 128 };
// 从卡片底部两侧斜射上来的那一拨，只有金档以上才有。
const SHOT_COUNTS = { white: 0, blue: 0, purple: 0, pink: 8, gold: 16, red: 24, rainbow: 34 };
const SHOT_TIERS = new Set(["pink", "gold", "red", "rainbow"]);

const rand = (min, span) => min + Math.random() * span;

function drop(palette, index) {
  return {
    "--x0": `${rand(0, 100).toFixed(2)}vw`,
    "--dx": `${rand(-9, 18).toFixed(1)}vw`,
    "--rot": `${rand(-540, 1080).toFixed(0)}deg`,
    "--delay": `${rand(0, 420).toFixed(0)}ms`,
    "--life": `${rand(1500, 1100).toFixed(0)}ms`,
    "--c": palette[index % palette.length],
    "--w": `${rand(5, 6).toFixed(1)}px`,
    "--h": `${rand(8, 8).toFixed(1)}px`,
    "--r": Math.random() < 0.3 ? "50%" : "1px",
  };
}

function shot(palette, index) {
  const left = index % 2 === 0;
  return {
    "--x0": `${(left ? rand(4, 14) : rand(80, 14)).toFixed(1)}vw`,
    "--dx": `${(left ? rand(6, 26) : -rand(6, 26)).toFixed(1)}vw`,
    "--peak": `${(-rand(34, 34)).toFixed(0)}vh`,
    "--rot": `${rand(-720, 720).toFixed(0)}deg`,
    "--delay": `${rand(0, 260).toFixed(0)}ms`,
    "--life": `${rand(1300, 700).toFixed(0)}ms`,
    "--c": palette[index % palette.length],
    "--w": `${rand(4, 5).toFixed(1)}px`,
    "--h": `${rand(10, 10).toFixed(1)}px`,
    "--r": Math.random() < 0.35 ? "50%" : "1px",
  };
}

export const RibbonBurst = defineComponent({
  name: "RibbonBurst",
  props: {
    tier: { type: String, default: "white" },
  },
  setup(props) {
    const palette = PALETTES[props.tier] || PALETTES.white;
    const drops = Array.from({ length: DROP_COUNTS[props.tier] ?? 26 }, (_, index) => drop(palette, index));
    const shots = SHOT_TIERS.has(props.tier)
      ? Array.from({ length: SHOT_COUNTS[props.tier] ?? 0 }, (_, index) => shot(palette, index))
      : [];
    return { drops: ref(drops), shots: ref(shots) };
  },
  template: `
    <span class="burst" :data-tier="tier" aria-hidden="true">
      <span class="burst__flash"></span>
      <i v-for="(bit, index) in drops" :key="'d' + index" class="burst__bit burst__drop" :style="bit"></i>
      <i v-for="(bit, index) in shots" :key="'s' + index" class="burst__bit burst__shot" :style="bit"></i>
    </span>`,
});
