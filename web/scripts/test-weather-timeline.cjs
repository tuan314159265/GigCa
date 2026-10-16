const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const ts = require('typescript');
const code = ts.transpileModule(fs.readFileSync('src/app/(main)/dashboard/_components/gigca/weather-timeline.ts', 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2023 },
}).outputText;
const context = { exports: {} };
vm.runInNewContext(code, context);
const { weatherTimeline, weatherTimeLabel } = context.exports;
const hours = [
  { valid_time: '2026-10-15T15:00:00+07:00', precipitation_mm: 6, precipitation_probability_pct: 90 },
  { valid_time: '2026-10-15T16:00:00+07:00', precipitation_mm: 2, precipitation_probability_pct: 50 },
];
const rows = weatherTimeline(hours, '2026-10-15T15:05:00+07:00', 30);
assert.equal(rows.length, 7);
assert.equal(weatherTimeLabel(rows[0].timestamp), '15:05');
assert.equal(weatherTimeLabel(rows.at(-1).timestamp), '15:35');
assert.ok(rows.every(r => r.precipitation_mm === 6 && r.precipitation_probability_pct === 90));
const boundary = weatherTimeline(hours, '2026-10-15T15:55:00+07:00', 10);
assert.equal(boundary[0].precipitation_mm, 6);
assert.equal(boundary[1].precipitation_mm, 2);
const missing = weatherTimeline([hours[0]], '2026-10-15T15:55:00+07:00', 10);
assert.equal(missing[1].precipitation_mm, null);
assert.equal(missing[2].precipitation_probability_pct, null);
const unaligned = weatherTimeline(hours, '2026-10-15T15:03:20+07:00', 30);
assert.equal(unaligned.at(-1).timestamp - unaligned[0].timestamp, 30 * 60000);
assert.equal(weatherTimeLabel(unaligned[1].timestamp), '15:05');
assert.equal(weatherTimeline(hours, 'bad', 30).length, 0);
console.log('Weather timeline checks passed.');
