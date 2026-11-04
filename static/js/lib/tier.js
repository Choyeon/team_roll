/* 开奖档位：把数值在活动区间里的百分位切成七档，越靠上越花。 */

// 区间百分位：roll_min 是 0% 位，roll_max 是 100% 位。
export const BANDS = [
  { key: "white", label: "白色彩带", from: 0, to: 40 },
  { key: "blue", label: "蓝色", from: 41, to: 50 },
  { key: "purple", label: "紫色", from: 51, to: 60 },
  { key: "pink", label: "粉色", from: 61, to: 70 },
  { key: "gold", label: "金色", from: 71, to: 80 },
  { key: "red", label: "红色", from: 81, to: 90 },
  { key: "rainbow", label: "七彩色", from: 91, to: 100 },
];

export function positionInRange(value, rollMin, rollMax) {
  if (!Number.isFinite(value)) return null;
  const span = rollMax - rollMin;
  if (span <= 0) return 100;
  return Math.min(100, Math.max(0, Math.round(((value - rollMin) / span) * 100)));
}

export function tierOf(value, rollMin, rollMax) {
  const pct = positionInRange(value, rollMin, rollMax);
  if (pct === null) return null;
  const band = BANDS.find((item) => pct >= item.from && pct <= item.to) ?? BANDS[BANDS.length - 1];
  return { key: band.key, label: band.label, pct, band: `${band.from}-${band.to}%` };
}
