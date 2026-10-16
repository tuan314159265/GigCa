// Tests route presentation without React rendering, network, or a new runner.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const ts = require('typescript');
const code = ts.transpileModule(fs.readFileSync('src/app/(main)/dashboard/_components/gigca/routes.ts', 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;
const context = { exports: {}, require: () => ({}), URLSearchParams };
vm.runInNewContext(code, context);
const { groupRouteRoads, routeStreetSequence } = context.exports;
const { roadGroupGeometry } = context.exports;
const roads = [
  { id: '0:1', name: 'Hàm Nghi', status: 'unknown' },
  { id: '1:2', name: 'Hàm Nghi', status: 'moderate', speed: 10, delay: 20 },
  { id: '2:3', name: 'Trương Định', status: 'smooth', speed: 30 },
  { id: '3:4', name: 'Hàm Nghi', status: 'congested', speed: 5, delay: 20 },
  { id: '4:5', name: 'Đoạn đường chưa có tên', status: 'unknown' },
  { id: '5:6', name: 'Đoạn đường chưa có tên', status: 'unknown' },
];
const groups = groupRouteRoads(roads);
assert.equal(groups.length, 4); // Same named street once; unknown streets remain distinct.
assert.equal(groups[0].segments.length, 3);
assert.equal(groups[0].status, 'congested');
assert.equal(groups[0].speed, 5);
assert.equal(groups[0].partial, true); // Unknown section is never labeled smooth.
assert.equal(groups[0].delay, 20); // Never sum repeated provider delay across split rows.
assert.equal(roads[0].status, 'unknown'); // Original segments stay unchanged.
const route = {
  legs: [{ points: Array.from({ length: 6 }, (_, i) => ({ latitude: i, longitude: i })) }],
  sections: [
    { startPointIndex: 0, endPointIndex: 2, sectionType: 'IMPORTANT_ROAD_STRETCH', streetName: { text: 'A' } },
    { startPointIndex: 2, endPointIndex: 3, sectionType: 'IMPORTANT_ROAD_STRETCH', streetName: { text: 'B' } },
    { startPointIndex: 3, endPointIndex: 5, sectionType: 'IMPORTANT_ROAD_STRETCH', streetName: { text: 'A' } },
    { startPointIndex: 0, endPointIndex: 1, sectionType: 'TRAFFIC', magnitudeOfDelay: 1 },
  ],
};
assert.equal(JSON.stringify(routeStreetSequence(route)), JSON.stringify(['A', 'B', 'A']));
const geometry = roadGroupGeometry(route, { segments: [{ id: '0:2' }, { id: '3:5' }] });
assert.equal(geometry.length, 2); // Never join the first and later visit across road B.
assert.equal(JSON.stringify(geometry[0]), JSON.stringify([[0,0],[1,1],[2,2]]));
assert.equal(JSON.stringify(geometry[1]), JSON.stringify([[3,3],[4,4],[5,5]]));
console.log('Route presentation checks passed.');
