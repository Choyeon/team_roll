/* 开奖档位：把数值在活动区间里的百分位切成七档，越靠上越花。
   只用来选配色，界面上不向参与者解释档位。 */

const BANDS = [
  { key: "white", from: 0, to: 40 },
  { key: "blue", from: 41, to: 50 },
  { key: "purple", from: 51, to: 60 },
  { key: "pink", from: 61, to: 70 },
  { key: "gold", from: 71, to: 80 },
  { key: "red", from: 81, to: 90 },
  { key: "rainbow", from: 91, to: 100 },
];

function positionInRange(value, rollMin, rollMax) {
  if (!Number.isFinite(value)) return null;
  const span = rollMax - rollMin;
  if (span <= 0) return 100;
  return Math.min(100, Math.max(0, Math.round(((value - rollMin) / span) * 100)));
}

export function tierOf(value, rollMin, rollMax) {
  const pct = positionInRange(value, rollMin, rollMax);
  if (pct === null) return null;
  const band = BANDS.find((item) => pct >= item.from && pct <= item.to) ?? BANDS[BANDS.length - 1];
  return { key: band.key, pct };
}
