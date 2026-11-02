/* Hand-written SVG charts — no chart library, no extra dependency. */

import { computed, defineComponent } from "../lib/vue.js";

const PALETTE = ["var(--chart-1)", "var(--chart-2)", "var(--chart-3)", "var(--chart-4)"];

/** Line + area for the daily roll trend. */
export const TrendChart = defineComponent({
  name: "TrendChart",
  props: {
    data: { type: Array, default: () => [] },
    height: { type: Number, default: 170 },
    valueLabel: { type: String, default: "Roll 点" },
  },
  setup(props) {
    const box = { w: 620, h: props.height, pad: 26 };
    const max = computed(() => Math.max(1, ...props.data.map((item) => item.rolls)));
    const step = computed(() => (props.data.length > 1 ? (box.w - box.pad * 2) / (props.data.length - 1) : 0));
    const points = computed(() =>
      props.data.map((item, index) => {
        const x = box.pad + index * step.value;
        const y = box.h - box.pad - (item.rolls / max.value) * (box.h - box.pad * 2);
        return { ...item, x, y };
      }),
    );
    const line = computed(() => points.value.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" "));
    const area = computed(() => {
      if (!points.value.length) return "";
      const first = points.value[0];
      const last = points.value[points.value.length - 1];
      const base = box.h - box.pad;
      return `${first.x.toFixed(1)},${base} ${line.value} ${last.x.toFixed(1)},${base}`;
    });
    const grid = computed(() => [0, 0.5, 1].map((ratio) => box.pad + ratio * (box.h - box.pad * 2)));
    return { box, max, points, line, area, grid, label: (p) => `${p.day}：${p.rolls} ${props.valueLabel}` };
  },
  template: `
    <svg class="chart" :viewBox="'0 0 ' + box.w + ' ' + box.h" role="img"
         :aria-label="valueLabel + '趋势，最高 ' + max">
      <line v-for="(y, i) in grid" :key="'g' + i" class="chart__grid" :x1="box.pad" :x2="box.w - box.pad" :y1="y" :y2="y"/>
      <text class="chart__axis" :x="box.pad - 6" :y="box.pad + 4" text-anchor="end">{{ max }}</text>
      <text class="chart__axis" :x="box.pad - 6" :y="box.h - box.pad + 4" text-anchor="end">0</text>
      <polygon v-if="area" class="chart__area" :points="area"/>
      <polyline v-if="line" class="chart__line" :points="line"/>
      <circle v-for="p in points" :key="p.day" :cx="p.x" :cy="p.y" r="2.6">
        <title>{{ label(p) }}</title>
      </circle>
      <text v-if="points.length" class="chart__axis" :x="box.pad" :y="box.h - 6" text-anchor="start">{{ points[0].day }}</text>
      <text v-if="points.length" class="chart__axis" :x="box.w - box.pad" :y="box.h - 6" text-anchor="end">{{ points[points.length - 1].day }}</text>
    </svg>`,
});

/** Horizontal bars for distributions and top lists. */
export const BarChart = defineComponent({
  name: "BarChart",
  props: {
    data: { type: Array, default: () => [] },
    color: { type: String, default: "var(--chart-1)" },
  },
  setup(props) {
    const max = computed(() => Math.max(1, ...props.data.map((item) => Number(item.value) || 0)));
    return { max, pct: (item) => `${((Number(item.value) || 0) / max.value) * 100}%` };
  },
  template: `
    <ul class="stack-tight" style="list-style:none;margin:0;padding:0">
      <li v-for="item in data" :key="item.label" class="stack-tight">
        <div class="row row--between" style="font-size:var(--text-xs)">
          <span class="muted">{{ item.label }}</span>
          <span class="mono">{{ item.display ?? item.value }}</span>
        </div>
        <div class="bar" role="img" :aria-label="item.label + '：' + (item.display ?? item.value)">
          <div class="bar__fill" :style="{ width: pct(item), background: color }"></div>
        </div>
      </li>
    </ul>`,
});

/** Donut for the activity status split. */
export const DonutChart = defineComponent({
  name: "DonutChart",
  props: { segments: { type: Array, default: () => [] } },
  setup(props) {
    const radius = 42;
    const circumference = 2 * Math.PI * radius;
    const total = computed(() => props.segments.reduce((sum, item) => sum + item.value, 0));
    const arcs = computed(() => {
      let offset = 0;
      return props.segments
        .map((item, index) => {
          const fraction = total.value ? item.value / total.value : 0;
          const arc = {
            label: item.label,
            value: item.value,
            color: item.color || PALETTE[index % PALETTE.length],
            dash: `${(fraction * circumference).toFixed(2)} ${(circumference * (1 - fraction)).toFixed(2)}`,
            offset: (-offset * circumference).toFixed(2),
            fraction,
          };
          offset += fraction;
          return arc;
        })
        .filter((arc) => arc.value > 0);
    });
    return { radius, circumference, arcs, total, palette: PALETTE };
  },
  template: `
    <div class="row" style="gap:var(--space-4)">
      <svg class="chart" viewBox="0 0 120 120" style="max-width:9rem" role="img" aria-label="状态分布">
        <circle :cx="60" :cy="60" :r="radius" fill="none" class="chart__grid" stroke-width="14"/>
        <circle v-for="arc in arcs" :key="arc.label" class="donut__segment" :cx="60" :cy="60" :r="radius"
                :stroke="arc.color" :stroke-dasharray="arc.dash" :stroke-dashoffset="arc.offset"
                transform="rotate(-90 60 60)">
          <title>{{ arc.label }}：{{ arc.value }}</title>
        </circle>
        <text class="chart__value" x="60" y="64" text-anchor="middle" style="font-size:16px">{{ total }}</text>
      </svg>
      <ul class="legend" style="flex-direction:column;align-items:flex-start">
        <li v-for="arc in arcs" :key="arc.label">
          <span class="legend__swatch" :style="{ background: arc.color }"></span>{{ arc.label }} · {{ arc.value }}
        </li>
      </ul>
    </div>`,
});
