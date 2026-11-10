// node-api/trafficMonitor.js
// Phase 2.4: 旧协议流量监控
// 统计 task_context 新协议 vs 兼容路径的流量比例
// 达标条件：旧协议流量 < 5% 且持续 7 天 → 可移除兼容路径
// ================================================================

class TrafficMonitor {
  constructor() {
    this.reset();
    this._inboundHook = null;
  }

  reset() {
    this.stats = {
      started_at: new Date().toISOString(),
      total_submissions: 0,
      new_protocol: 0,
      compat_protocol: 0,
      daily_buckets: {},
    };
  }

  _todayKey() {
    return new Date().toISOString().slice(0, 10);
  }

  _getOrCreateBucket(dateKey) {
    if (!this.stats.daily_buckets[dateKey]) {
      this.stats.daily_buckets[dateKey] = {
        total: 0,
        new_protocol: 0,
        compat_protocol: 0,
        started_at: new Date().toISOString(),
      };
    }
    return this.stats.daily_buckets[dateKey];
  }

  recordNewProtocol() {
    this.stats.total_submissions++;
    this.stats.new_protocol++;
    const bucket = this._getOrCreateBucket(this._todayKey());
    bucket.total++;
    bucket.new_protocol++;
  }

  recordCompatProtocol() {
    this.stats.total_submissions++;
    this.stats.compat_protocol++;
    const bucket = this._getOrCreateBucket(this._todayKey());
    bucket.total++;
    bucket.compat_protocol++;
  }

  getCompatRatio() {
    if (this.stats.total_submissions === 0) return 0;
    return this.stats.compat_protocol / this.stats.total_submissions;
  }

  isMigrationReady() {
    if (this.stats.total_submissions < 100) return false;
    const ratio = this.getCompatRatio();
    if (ratio >= 0.05) return false;

    const sortedDates = Object.keys(this.stats.daily_buckets).sort().reverse();
    let consecutiveDaysBelowThreshold = 0;

    for (const dateKey of sortedDates) {
      const bucket = this.stats.daily_buckets[dateKey];
      if (bucket.total === 0) continue;
      const dailyRatio = bucket.compat_protocol / bucket.total;
      if (dailyRatio < 0.05) {
        consecutiveDaysBelowThreshold++;
      } else {
        break;
      }
      if (consecutiveDaysBelowThreshold >= 7) return true;
    }

    return false;
  }

  getReport() {
    const ratio = this.getCompatRatio();
    const migrationReady = this.isMigrationReady();

    const daily = {};
    const sortedDates = Object.keys(this.stats.daily_buckets).sort();
    const last14 = sortedDates.slice(-14);
    for (const d of last14) {
      const b = this.stats.daily_buckets[d];
      daily[d] = {
        total: b.total,
        new_protocol: b.new_protocol,
        compat_protocol: b.compat_protocol,
        compat_ratio: b.total > 0
          ? (b.compat_protocol / b.total * 100).toFixed(1) + '%'
          : '0%',
      };
    }

    return {
      started_at: this.stats.started_at,
      now: new Date().toISOString(),
      total_submissions: this.stats.total_submissions,
      new_protocol: this.stats.new_protocol,
      compat_protocol: this.stats.compat_protocol,
      compat_ratio: (ratio * 100).toFixed(1) + '%',
      threshold: '5%',
      migration_ready: migrationReady,
      daily_breakdown: daily,
      note: migrationReady
        ? '达标：旧协议流量连续 7 天低于 5%，可以移除兼容路径'
        : '未达标：继续监控',
    };
  }

  getAllStats() {
    return JSON.parse(JSON.stringify(this.stats));
  }
}

module.exports = { TrafficMonitor };