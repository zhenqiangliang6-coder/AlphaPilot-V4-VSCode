// node-api/test-trafficMonitor.js
// Phase 2.4: TrafficMonitor 测试
// ================================================================

const { TrafficMonitor } = require('./trafficMonitor');

let pass = 0;
let fail = 0;

function assert(condition, label) {
  if (condition) {
    pass++;
  } else {
    fail++;
    console.error(`  FAIL: ${label}`);
  }
}

console.log('\n=== TrafficMonitor: 初始状态 ===');
{
  const tm = new TrafficMonitor();
  assert(tm.stats.total_submissions === 0, 'initial total is 0');
  assert(tm.stats.new_protocol === 0, 'initial new_protocol is 0');
  assert(tm.stats.compat_protocol === 0, 'initial compat_protocol is 0');
  assert(tm.getCompatRatio() === 0, 'compat ratio is 0 with no submissions');
  assert(tm.isMigrationReady() === false, 'not ready with < 100 submissions');
  assert(Object.keys(tm.stats.daily_buckets).length === 0, 'no daily buckets initially');
}

console.log('\n=== TrafficMonitor: 记录新协议 ===');
{
  const tm = new TrafficMonitor();
  tm.recordNewProtocol();
  assert(tm.stats.total_submissions === 1, 'total is 1');
  assert(tm.stats.new_protocol === 1, 'new_protocol is 1');
  assert(tm.stats.compat_protocol === 0, 'compat_protocol is 0');
  assert(tm.getCompatRatio() === 0, 'compat ratio is 0');
}

console.log('\n=== TrafficMonitor: 记录兼容协议 ===');
{
  const tm = new TrafficMonitor();
  tm.recordCompatProtocol();
  assert(tm.stats.total_submissions === 1, 'total is 1');
  assert(tm.stats.new_protocol === 0, 'new_protocol is 0');
  assert(tm.stats.compat_protocol === 1, 'compat_protocol is 1');
  assert(tm.getCompatRatio() === 1, 'compat ratio is 1');
}

console.log('\n=== TrafficMonitor: 混合记录 ===');
{
  const tm = new TrafficMonitor();
  for (let i = 0; i < 8; i++) tm.recordNewProtocol();
  for (let i = 0; i < 2; i++) tm.recordCompatProtocol();
  assert(tm.stats.total_submissions === 10, 'total is 10');
  assert(tm.stats.new_protocol === 8, 'new_protocol is 8');
  assert(tm.stats.compat_protocol === 2, 'compat_protocol is 2');
  assert(tm.getCompatRatio() === 0.2, 'compat ratio is 20%');
  assert(tm.isMigrationReady() === false, 'not ready (20% > 5%)');
}

console.log('\n=== TrafficMonitor: 达标条件 ===');
{
  const tm = new TrafficMonitor();
  for (let i = 0; i < 100; i++) {
    tm.recordNewProtocol();
  }
  assert(tm.stats.total_submissions === 100, 'total is 100');
  assert(tm.getCompatRatio() === 0, 'compat ratio is 0');
  assert(tm.isMigrationReady() === false, 'not ready with only 1 day of data');

  const today = new Date().toISOString().slice(0, 10);
  for (let d = 1; d <= 6; d++) {
    const dateKey = new Date(Date.now() - d * 86400000).toISOString().slice(0, 10);
    tm._getOrCreateBucket(dateKey);
    tm.stats.daily_buckets[dateKey].total = 20;
    tm.stats.daily_buckets[dateKey].new_protocol = 20;
    tm.stats.daily_buckets[dateKey].compat_protocol = 0;
  }
  assert(tm.isMigrationReady() === true, 'ready with 7 days all at 0% compat');
}

console.log('\n=== TrafficMonitor: 日报表 ===');
{
  const tm = new TrafficMonitor();
  tm.recordNewProtocol();
  tm.recordCompatProtocol();
  const report = tm.getReport();
  assert(report.total_submissions === 2, 'report total is 2');
  assert(typeof report.compat_ratio === 'string', 'compat_ratio is string');
  assert(report.daily_breakdown !== undefined, 'daily_breakdown exists');
  assert(Object.keys(report.daily_breakdown).length === 1, 'one day in breakdown');
}

console.log('\n=== TrafficMonitor: reset ===');
{
  const tm = new TrafficMonitor();
  tm.recordNewProtocol();
  tm.recordCompatProtocol();
  tm.reset();
  assert(tm.stats.total_submissions === 0, 'total is 0 after reset');
  assert(tm.stats.new_protocol === 0, 'new_protocol is 0 after reset');
  assert(tm.getCompatRatio() === 0, 'compat ratio is 0 after reset');
}

console.log('\n=== TrafficMonitor: 多天 ===');
{
  const tm = new TrafficMonitor();
  const today = new Date().toISOString().slice(0, 10);
  const todayBucket = tm._getOrCreateBucket(today);
  todayBucket.total = 50;
  todayBucket.new_protocol = 48;
  todayBucket.compat_protocol = 2;

  const yesterday = new Date(Date.now() - 86400000).toISOString().slice(0, 10);
  const yesterdayBucket = tm._getOrCreateBucket(yesterday);
  yesterdayBucket.total = 50;
  yesterdayBucket.new_protocol = 49;
  yesterdayBucket.compat_protocol = 1;

  assert(tm.isMigrationReady() === false, 'not ready (only 2 days, need 7)');
}

console.log(`\n==================================================`);
console.log(`Results: ${pass} pass  ${fail} fail  ${pass + fail} total`);
console.log(`==================================================`);

process.exit(fail > 0 ? 1 : 0);