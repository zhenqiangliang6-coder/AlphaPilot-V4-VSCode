// src/hooks/useTypewriter.ts
// ⚡ rAF 时间步进打字机引擎 — 替换逐字符 setTimeout 的 O(n) 定时器方案
// 特性：时间步进（帧率无关）、智能追赶（落后过多自动加速）、收尾快速补齐

import { useEffect, useLayoutEffect, useRef, useState } from 'react';

export interface UseTypewriterOptions {
  /** 打字速度（字符/秒），默认 90 */
  cps?: number;
  /** 是否启用打字机效果；false 时立即完整显示（历史消息直接呈现） */
  enabled?: boolean;
  /** 落后超过该字符数时进入追赶模式（速度 ×3），默认 240 */
  catchUpThreshold?: number;
  /** 非流式收尾时的补齐速度倍率，默认 12x（保证 stream_end 后快速补完） */
  finalBoost?: number;
}

/**
 * 返回逐字逼近 target 的显示字符串。
 * - 流式期间：按 cps 逐字推进；落后太多（>catchUpThreshold）自动 ×3 追赶
 * - 流式结束（active=false）：按 finalBoost 快速补齐，避免任务完成后还在慢慢打字
 * - target 收缩（消息被替换/清空）时同步收缩，不会显示脏数据
 */
export function useTypewriter(
  target: string,
  active: boolean,
  options: UseTypewriterOptions = {}
): string {
  const { cps = 90, enabled = true, catchUpThreshold = 240, finalBoost = 12 } = options;

  // 初始长度必须统一：非流式挂载（历史消息）直接完整显示，
  // lenRef 若停在 0 会导致 effect 空转推进几帧才追平（肉眼看不到但浪费 rAF）
  const initialLen = enabled && active ? 0 : target.length;
  const [displayedLen, setDisplayedLen] = useState(() => initialLen);

  const lenRef = useRef(initialLen);
  const rafRef = useRef(0);
  const lastTsRef = useRef(0);
  const accRef = useRef(0); // 小数累加器：dt * speed 不足 1 字符时累积到下一帧

  // target / active 通过 ref 读取：chunk 高频到达不重启 rAF 循环
  const targetRef = useRef(target);
  const activeRef = useRef(active);
  targetRef.current = target;
  activeRef.current = active;

  // target 收缩时同步收缩（防脏数据）
  // 注：收缩处理放在 layout effect 而非渲染期 —— 渲染期 setState 属于
  // "adjusting state during render" 模式（React 官方认可但有约束），
  // 挪进 effect 语义更干净，也为并发特性留足安全边际。
  const prevTargetLenRef = useRef(target.length);
  useLayoutEffect(() => {
    if (target.length < prevTargetLenRef.current) {
      // target 收缩 = 内容被替换/清空：直接完整显示新 target，清空小数累加器
      lenRef.current = target.length;
      accRef.current = 0;
      setDisplayedLen(target.length);
    }
    prevTargetLenRef.current = target.length;
  }, [target]);

  useEffect(() => {
    if (!enabled) {
      // 历史消息 / 未启用：直接完整显示
      lenRef.current = targetRef.current.length;
      setDisplayedLen(lenRef.current);
      return;
    }

    lastTsRef.current = 0;
    accRef.current = 0;

    const step = (ts: number) => {
      if (!lastTsRef.current) lastTsRef.current = ts;
      // 防后台节流导致的时间大跳（最长按 100ms 计）
      const dt = Math.min(ts - lastTsRef.current, 100) / 1000;
      lastTsRef.current = ts;

      const targetLen = targetRef.current.length;
      const behind = targetLen - lenRef.current;

      if (behind > 0) {
        const speed = activeRef.current
          ? behind > catchUpThreshold
            ? cps * 3 // 追赶模式
            : cps
          : cps * finalBoost; // 收尾补齐
        accRef.current += dt * speed;
        const add = Math.floor(accRef.current);
        if (add > 0) {
          accRef.current -= add;
          lenRef.current = Math.min(targetLen, lenRef.current + add);
          setDisplayedLen(lenRef.current);
        }
      }

      // 流式已结束且已追平 → 停止空转（active 变化时 effect 会重启）
      if (!(behind <= 0 && !activeRef.current)) {
        rafRef.current = requestAnimationFrame(step);
      }
    };

    rafRef.current = requestAnimationFrame(step);
    return () => cancelAnimationFrame(rafRef.current);
    // active 变化（true↔false）时重启循环以处理停止/收尾；chunk 到达不重启
  }, [enabled, active, cps, catchUpThreshold, finalBoost]);

  return target.slice(0, Math.min(displayedLen, target.length));
}
