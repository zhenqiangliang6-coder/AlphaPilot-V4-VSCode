// src/hooks/useTypewriter.test.ts
// 契约测试：打字机时间状态机（rAF 时间步进 / 追赶 / 收尾补齐 / 收缩防脏数据 / 停帧）
// 思路与后端 contract-test-vectors.json 同构：回归是静默的（build 照过），必须用测试锁死。
// rAF 采用确定性 mock：手动驱动帧 + 手动控制时间戳，断言可精确到字符。

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useTypewriter } from './useTypewriter';

// ---- 确定性 rAF mock ----
type RafCb = (ts: number) => void;
type RafHandle = number;
let rafCallbacks: Map<RafHandle, RafCb>;
let nextRafId: number;
let clockMs: number;

beforeEach(() => {
  rafCallbacks = new Map();
  nextRafId = 1;
  clockMs = 0;
  vi.stubGlobal('requestAnimationFrame', (cb: RafCb) => {
    const id = nextRafId++;
    rafCallbacks.set(id, cb);
    return id;
  });
  // cancel 必须真正删除：否则 rerender（effect 重启）后旧回调仍在队列里递归调度
  vi.stubGlobal('cancelAnimationFrame', (id: RafHandle) => {
    rafCallbacks.delete(id);
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

/**
 * 推进 n 个 rAF 帧，每帧 dtMs 毫秒（默认 16.7ms ≈ 60fps）。
 * 注意：首帧是"时间基准帧"——引擎在首帧只记录 lastTs（dt=0），
 * 真实字符推进从第 2 帧开始。故有效推进帧数 = n - 1。
 */
function flushFrames(n: number, dtMs = 16.7): void {
  for (let i = 0; i < n; i++) {
    clockMs += dtMs;
    const batch = Array.from(rafCallbacks.values());
    rafCallbacks.clear(); // 引擎会在回调里重新注册下一帧
    act(() => {
      batch.forEach((cb) => cb(clockMs));
    });
  }
}

const hookArgs = { initialProps: { text: '', active: true } };

describe('useTypewriter 契约', () => {
  it('非流式挂载（active=false）：直接完整显示，用于历史消息', () => {
    const { result } = renderHook(() => useTypewriter('历史消息内容', false));
    expect(result.current).toBe('历史消息内容');
  });

  it('enabled=false：立即完整显示（打字机关闭）', () => {
    const { result } = renderHook(() =>
      useTypewriter('立即显示', true, { enabled: false })
    );
    expect(result.current).toBe('立即显示');
  });

  it('流式时间步进：cps=100 时按 dt 累积推进（帧率无关）', () => {
    const { result } = renderHook(
      ({ text, active }) =>
        useTypewriter(text, active, { cps: 100, catchUpThreshold: 1000, finalBoost: 12 }),
      { ...hookArgs, initialProps: { text: 'x'.repeat(10), active: true } }
    );
    expect(result.current).toBe('');

    // 首帧基准 dt=0；后续每帧 16.7ms × 100cps ≈ 1.67 字
    // 4 帧 = 3 个有效推进帧：acc 累积 [1.67, 3.34, 5.01] → 取整 1, 3, 5 字
    flushFrames(4);
    expect(result.current).toBe('xxxxx');
  });

  it('智能追赶：落后 > catchUpThreshold 时速度 ×3', () => {
    const { result } = renderHook(
      ({ text, active }) =>
        useTypewriter(text, active, { cps: 100, catchUpThreshold: 10, finalBoost: 12 }),
      { ...hookArgs, initialProps: { text: 'y'.repeat(100), active: true } }
    );

    // behind=100 > 10 → 300cps：5 帧 = 4 有效帧 × 5.01 ≈ 20 字
    // （正常速率要 12 个有效帧才能打 20 字）
    flushFrames(5);
    expect(result.current.length).toBe(20);
  });

  it('收尾补齐：active=false 后按 finalBoost 快速补完', () => {
    const { result, rerender } = renderHook(
      ({ text, active }) =>
        useTypewriter(text, active, { cps: 100, catchUpThreshold: 1000, finalBoost: 12 }),
      { ...hookArgs, initialProps: { text: 'z'.repeat(10), active: true } }
    );
    flushFrames(2); // 1 个有效帧，正常速率打了 1 字

    // 模拟 stream_end：active=false，effect 重启后首帧重新作基准
    rerender({ text: 'z'.repeat(60), active: false });
    // 1200cps：4 帧 = 3 有效帧 × 20.04 ≈ 60 字，追平
    flushFrames(4);
    expect(result.current.length).toBe(60);
    expect(result.current).toBe('z'.repeat(60));
  });

  it('停帧契约：追平且非流式后不再调度 rAF（不空转耗电）', () => {
    const { result } = renderHook(
      ({ text, active }) =>
        useTypewriter(text, active, { cps: 100, catchUpThreshold: 1000, finalBoost: 12 }),
      { ...hookArgs, initialProps: { text: '追平即停', active: false } }
    );
    flushFrames(2); // active=false 初始即完整显示（useState 初值=target.length）
    expect(result.current).toBe('追平即停');
    expect(rafCallbacks.size).toBe(0); // 首帧判定 behind<=0 && !active → 不再调度
  });

  it('收缩防脏数据：target 变短时显示立即收缩为新 target 的前缀', () => {
    const { result, rerender } = renderHook(
      ({ text, active }) =>
        useTypewriter(text, active, { cps: 100, catchUpThreshold: 1000, finalBoost: 12 }),
      { ...hookArgs, initialProps: { text: 'abcdefghij', active: true } }
    );
    flushFrames(2); // 1 个有效帧 → 已显示 1 字
    expect(result.current.length).toBe(1);

    // 模拟消息被替换：target 从 10 字收缩为 3 字
    rerender({ text: 'abc', active: true });
    expect(result.current.length).toBeLessThanOrEqual(3);
    expect('abc'.startsWith(result.current)).toBe(true); // 前缀契约，绝无脏数据
  });
});
