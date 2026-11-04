/* 开奖彩带：粒子在挂载时撒一次，父组件换 :key 就重撒一轮。
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

// 档位越高撒得越猛，七彩档几乎铺满整个开奖框。
const COUNTS = { white: 18, blue: 18, purple: 20, pink: 20, gold: 26, red: 30, rainbow: 40 };

function ribbon(palette, index) {
  const angle = ((-160 + Math.random() * 140) * Math.PI) / 180;
  const reach = 70 + Math.random() * 90;
  const peakX = Math.cos(angle) * reach;
  const peakY = Math.sin(angle) * reach;
  return {
    "--mx": `${peakX.toFixed(0)}px`,
    "--my": `${peakY.toFixed(0)}px`,
    "--dx": `${(peakX * 1.35).toFixed(0)}px`,
    "--dy": `${(peakY + 130 + Math.random() * 70).toFixed(0)}px`,
    "--rot": `${(Math.random() * 720 - 360).toFixed(0)}deg`,
    "--delay": `${(Math.random() * 140).toFixed(0)}ms`,
    "--life": `${(950 + Math.random() * 750).toFixed(0)}ms`,
    "--c": palette[index % palette.length],
    "--w": `${(5 + Math.random() * 7).toFixed(1)}px`,
  };
}

export const RibbonBurst = defineComponent({
  name: "RibbonBurst",
  props: {
    tier: { type: String, default: "white" },
  },
  setup(props) {
    const palette = PALETTES[props.tier] || PALETTES.white;
    const count = COUNTS[props.tier] || 18;
    const bits = ref(Array.from({ length: count }, (_, index) => ribbon(palette, index)));
    return { bits };
  },
  template: `
    <span class="burst" aria-hidden="true">
      <i v-for="(bit, index) in bits" :key="index" class="burst__bit" :style="bit"></i>
    </span>`,
});
