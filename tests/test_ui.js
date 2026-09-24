const assert = require('node:assert/strict');
const { selectWindow, windowForHours, moveWindow, spreadPoints, chartStats, filterBranches, dashboardStats, circleMark } = require('../ui_helpers.js');

const rows = [
  { start_at: '2026-09-23T11:59:59Z' },
  { start_at: '2026-09-23T12:00:00Z' },
  { start_at: '2026-09-23T23:00:00Z' },
];
const selected = selectWindow(rows, +new Date('2026-09-23T12:00:00Z'), +new Date('2026-09-24T00:00:00Z'));
assert.deepEqual(selected, rows.slice(1), '12-hour range should include its lower boundary');

const domainStart = +new Date('2026-09-21T00:00:00Z');
const domainEnd = +new Date('2026-09-24T00:00:00Z');
assert.deepEqual(windowForHours(domainStart, domainEnd, 24), [domainEnd - 86400000, domainEnd]);
assert.deepEqual(moveWindow(domainStart, domainEnd, domainEnd - 86400000, domainEnd, -43200000), [domainEnd - 129600000, domainEnd - 43200000]);
assert.deepEqual(moveWindow(domainStart, domainEnd, domainStart, domainStart + 86400000, -43200000), [domainStart, domainStart + 86400000]);

const spread = spreadPoints([{x:10,y:10},{x:11,y:11},{x:40,y:40}], 4);
assert.deepEqual(spread[0], {x:10,y:10});
assert.notDeepEqual(spread[1], {x:11,y:11}, 'overlapping marks should receive a small visual offset');
assert.deepEqual(spread[2], {x:40,y:40});
const bounded = spreadPoints([{x:10,y:100},{x:10,y:100},{x:10,y:100}], 12, { minX: 0, maxX: 100, minY: 10, maxY: 100 });
assert.ok(bounded.every(point => point.y >= 10 && point.y <= 100), 'spread marks must stay inside the plot baseline');

const stats = chartStats([
  { duration_seconds: 600, status: 'success' },
  { duration_seconds: 900, status: 'failure' },
  { duration_seconds: 1200, status: 'cancelled' },
]);
assert.equal(stats.max, 1200, 'selected points should determine the y-axis maximum');
assert.equal(stats.p90, 870, 'selected completed points should determine the chart P90');
assert.equal(stats.average, 750, 'average should only use completed batches');
assert.equal(stats.p50, 750, 'P50 should only use completed batches');
assert.equal(stats.count, 2, 'sample count should only include completed batches');
assert.equal(chartStats([]).max, 300, 'empty ranges should keep a small readable scale');
assert.equal(chartStats([]).average, null, 'empty ranges should not invent an average');

const branchRows = [
  { pr: 1, base_branch: 'main', status: 'success', duration_seconds: 600, missing: [] },
  { pr: 2, base_branch: 'main-dev', status: 'failure', duration_seconds: 1200, missing: ['gap'] },
  { pr: 1, base_branch: 'release/3.2.2', status: 'running', duration_seconds: 300, missing: [] },
];
assert.deepEqual(filterBranches(branchRows, new Set(['main', 'release/3.2.2'])), [branchRows[0], branchRows[2]]);
assert.deepEqual(filterBranches(branchRows, new Set()), branchRows, 'empty selection means all branches');
const summary = dashboardStats(branchRows.slice(0, 2));
assert.equal(summary.prs, 2);
assert.equal(summary.batches, 2);
assert.equal(summary.valid, 2);
assert.equal(summary.median, 900);
assert.equal(summary.incomplete, 1);

const mark = circleMark({ status: 'running' }, 42, 21, 7, '#356ea8');
assert.match(mark, /^<g class="mark-hit"/, 'marks need a larger pointer hit area');
assert.match(mark, /<circle class="dot"/, 'running marks must use circles');
assert.match(mark, /fill="#356ea8"/, 'marks must be solid status colors');
assert.doesNotMatch(mark, /<path|fill="none"/, 'marks must not use triangles or hollow shapes');

console.log('UI helper tests OK');
