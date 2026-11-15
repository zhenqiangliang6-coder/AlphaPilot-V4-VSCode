// src/components/Toast.tsx
// v4.0 全局微交互基建 — 轻量 Toast 系统（零依赖：Context + createPortal）
// 特性：stagger 入场 / 倒计时进度条 / 左侧 accent 渐变条 / 最多堆叠 5 条
// 用法：
//   <ToastProvider>...</ToastProvider>
//   const { toast } = useToast();
//   toast('已应用 5 个文件变更', 'success');

import React, { createContext, useCallback, useContext, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

type ToastKind = 'success' | 'info' | 'error';

interface ToastItem {
  id: number;
  kind: ToastKind;
  message: string;
  duration: number;
}

interface ToastContextValue {
  toast: (message: string, kind?: ToastKind, duration?: number) => void;
}

const ToastCtx = createContext<ToastContextValue>({ toast: () => {} });

export const useToast = () => useContext(ToastCtx);

/** 内联 SVG 图标（比 emoji 更精致的科技感） */
const ToastIcon: React.FC<{ kind: ToastKind }> = ({ kind }) => {
  const common = {
    fill: 'none',
    strokeWidth: 2.4,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
  };
  if (kind === 'success') {
    return (
      <svg viewBox="0 0 24 24" className="w-4 h-4" stroke="url(#ap-toast-success)" {...common}>
        <defs>
          <linearGradient id="ap-toast-success" x1="0" y1="0" x2="24" y2="24">
            <stop offset="0%" stopColor="#34d399" />
            <stop offset="100%" stopColor="#22d3ee" />
          </linearGradient>
        </defs>
        <path d="M20 6L9 17l-5-5" />
      </svg>
    );
  }
  if (kind === 'error') {
    return (
      <svg viewBox="0 0 24 24" className="w-4 h-4" stroke="#fb7185" {...common}>
        <circle cx="12" cy="12" r="9" />
        <path d="M15 9l-6 6M9 9l6 6" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 24 24" className="w-4 h-4" stroke="#818cf8" {...common}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 8h.01M12 11v5" />
    </svg>
  );
};

const KIND_BAR: Record<ToastKind, string> = {
  success: 'from-emerald-400 to-cyan-400',
  info: 'from-indigo-400 to-cyan-400',
  error: 'from-rose-400 to-fuchsia-400',
};

const KIND_PROGRESS: Record<ToastKind, string> = {
  success: '#22d3ee',
  info: '#818cf8',
  error: '#fb7185',
};

const ToastProvider: React.FC<{ children?: React.ReactNode }> = ({ children }) => {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const idRef = useRef(0);

  const remove = useCallback((id: number) => {
    setToasts((t) => t.filter((x) => x.id !== id));
  }, []);

  const toast = useCallback(
    (message: string, kind: ToastKind = 'info', duration = 3200) => {
      const id = ++idRef.current;
      setToasts((t) => [...t.slice(-4), { id, kind, message, duration }]); // 最多堆叠 5 条
      window.setTimeout(() => remove(id), duration);
    },
    [remove]
  );

  return (
    <ToastCtx.Provider value={{ toast }}>
      {children}
      {createPortal(
        <div className="fixed bottom-5 left-1/2 -translate-x-1/2 z-[100] flex flex-col items-center gap-2 pointer-events-none">
          {toasts.map((t, i) => (
            <div
              key={t.id}
              className="ap-glass ap-rise pointer-events-auto relative overflow-hidden rounded-xl pl-4 pr-5 py-2.5 shadow-xl shadow-black/40 flex items-center gap-2.5 text-xs text-gray-200 min-w-[220px] max-w-[420px]"
              style={{ '--d': `${i * 60}ms` } as React.CSSProperties}
            >
              {/* 左侧 accent 渐变条 */}
              <span className={`absolute left-0 top-0 bottom-0 w-[3px] bg-gradient-to-b ${KIND_BAR[t.kind]}`} />
              <ToastIcon kind={t.kind} />
              <span className="flex-1">{t.message}</span>
              {/* 倒计时进度条 */}
              <span
                className="absolute bottom-0 left-0 right-0 h-[2px] origin-left"
                style={{
                  background: KIND_PROGRESS[t.kind],
                  animation: `ap-toast-bar ${t.duration}ms linear forwards`,
                  opacity: 0.7,
                }}
              />
            </div>
          ))}
        </div>,
        document.body
      )}
    </ToastCtx.Provider>
  );
};

export { ToastProvider };
