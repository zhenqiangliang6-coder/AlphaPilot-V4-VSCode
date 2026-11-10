// src/components/ConfirmationCard.tsx
// Phase 2.4 P0-4: 用户确认卡片 — 内联嵌入聊天流，拟人化展示
// ================================================================

import React, { useState, useEffect } from 'react';
import { vscodeAPI } from '../utils/vscode';

interface AllowedPaths {
  read: string[];
  write: string[];
  execute: string[];
}

interface ConfirmationData {
  confirmation_id: string;
  task_id: string;
  target_path: string;
  project_mode: string;
  allowed_paths: AllowedPaths;
  estimated_impact: string;
  context_summary?: string;
  expires_at: string;
  expires_in_seconds: number;
}

interface ConfirmationCardProps {
  confirmation: ConfirmationData;
  onResolved: () => void;
}

const MODE_LABELS: Record<string, { icon: string; label: string; color: string }> = {
  create_new_project: { icon: '🏗️', label: '创建新项目', color: 'text-emerald-400' },
  modify_existing_project: { icon: '✏️', label: '修改现有项目', color: 'text-blue-400' },
  modify_alphapilot: { icon: '⚙️', label: '修改 AlphaPilot 自身', color: 'text-amber-400' },
};

function formatCountdown(seconds: number): string {
  if (seconds <= 0) return '已过期';
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  if (m > 0) return `${m} 分 ${s} 秒`;
  return `${s} 秒`;
}

function formatPath(p: string): string {
  if (!p) return '';
  const parts = p.replace(/\\/g, '/').split('/');
  if (parts.length <= 3) return p;
  return '.../' + parts.slice(-2).join('/');
}

export const ConfirmationCard: React.FC<ConfirmationCardProps> = ({ confirmation, onResolved }) => {
  const [state, setState] = useState<'pending' | 'confirming' | 'denying' | 'confirmed' | 'denied' | 'expired'>('pending');
  const [countdown, setCountdown] = useState(confirmation.expires_in_seconds);

  const mode = MODE_LABELS[confirmation.project_mode] || MODE_LABELS.modify_existing_project;

  useEffect(() => {
    if (countdown <= 0) {
      setState('expired');
      return;
    }
    const timer = setInterval(() => {
      setCountdown(prev => {
        if (prev <= 1) {
          clearInterval(timer);
          setState('expired');
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(timer);
  }, [countdown]);

  const handleConfirm = () => {
    if (state !== 'pending') return;
    setState('confirming');

    vscodeAPI.postMessage({
      type: 'confirm_task',
      payload: {
        confirmation_id: confirmation.confirmation_id,
        task_id: confirmation.task_id,
      },
    });
  };

  const handleDeny = () => {
    if (state !== 'pending') return;
    setState('denying');

    vscodeAPI.postMessage({
      type: 'deny_task',
      payload: {
        confirmation_id: confirmation.confirmation_id,
        task_id: confirmation.task_id,
      },
    });
  };

  const isDisabled = state !== 'pending';

  const readPaths = confirmation.allowed_paths?.read || [];
  const writePaths = confirmation.allowed_paths?.write || [];
  const execPaths = confirmation.allowed_paths?.execute || [];

  return (
    <div className="flex justify-start w-full animate-fade-in">
      <div className={`
        max-w-[480px] rounded-2xl overflow-hidden
        border transition-all duration-300
        ${state === 'expired' ? 'border-gray-600 opacity-60' : 'border-vscode-border'}
        bg-vscode-panel shadow-lg
      `}>
        {/* 头部 */}
        <div className="px-5 pt-4 pb-3">
          <div className="flex items-center gap-3 mb-2">
            <span className="text-2xl">{mode.icon}</span>
            <div>
              <h3 className={`text-sm font-semibold ${mode.color}`}>
                {mode.label}
              </h3>
              <p className="text-xs text-gray-400 mt-0.5">
                AlphaPilot 需要你的确认才能继续
              </p>
            </div>
          </div>

          {confirmation.estimated_impact && (
            <div className="mt-3 px-3 py-2 rounded-lg bg-vscode-list-hover/40 border border-vscode-border/50">
              <p className="text-xs text-gray-300 leading-relaxed">
                {confirmation.estimated_impact}
              </p>
            </div>
          )}
        </div>

        {/* 路径预览 */}
        <div className="px-5 py-2 space-y-1.5 border-t border-vscode-border/50">
          {readPaths.length > 0 && (
            <div className="flex items-start gap-2 text-xs">
              <span className="text-gray-500 w-10 shrink-0 pt-0.5">📖 读取</span>
              <div className="flex flex-wrap gap-1">
                {readPaths.map((p, i) => (
                  <code key={i} className="px-1.5 py-0.5 rounded bg-vscode-list-hover/60 text-gray-300 text-[11px] font-mono">
                    {formatPath(p)}
                  </code>
                ))}
              </div>
            </div>
          )}
          {writePaths.length > 0 && (
            <div className="flex items-start gap-2 text-xs">
              <span className="text-amber-400 w-10 shrink-0 pt-0.5">✍️ 写入</span>
              <div className="flex flex-wrap gap-1">
                {writePaths.map((p, i) => (
                  <code key={i} className="px-1.5 py-0.5 rounded bg-amber-400/10 text-amber-300 text-[11px] font-mono">
                    {formatPath(p)}
                  </code>
                ))}
              </div>
            </div>
          )}
          {execPaths.length > 0 && (
            <div className="flex items-start gap-2 text-xs">
              <span className="text-red-400 w-10 shrink-0 pt-0.5">▶️ 执行</span>
              <div className="flex flex-wrap gap-1">
                {execPaths.map((p, i) => (
                  <code key={i} className="px-1.5 py-0.5 rounded bg-red-400/10 text-red-300 text-[11px] font-mono">
                    {formatPath(p)}
                  </code>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* 倒计时 + 错误 */}
        <div className="px-5 py-2">
          {state === 'pending' && countdown > 0 && (
            <div className="flex items-center gap-2 text-xs">
              <span className="text-gray-500">⏱️</span>
              <span className="text-gray-400">
                请在 <span className="text-gray-300 font-medium">{formatCountdown(countdown)}</span> 内确认
              </span>
            </div>
          )}
          {state === 'expired' && (
            <p className="text-xs text-gray-500">⚠️ 确认已过期，请重新提交任务</p>
          )}
          {state === 'confirmed' && (
            <p className="text-xs text-emerald-400 flex items-center gap-1">
              <span>✅</span> 已确认，任务开始执行
            </p>
          )}
          {state === 'denied' && (
            <p className="text-xs text-gray-400 flex items-center gap-1">
              <span>❌</span> 已拒绝此次操作
            </p>
          )}
        </div>

        {/* 按钮 */}
        {state === 'pending' && (
          <div className="px-5 pb-4 pt-1 flex gap-3">
            <button
              onClick={handleDeny}
              disabled={isDisabled}
              className={`
                flex-1 py-2 px-4 rounded-xl text-sm font-medium
                border border-gray-600 text-gray-300
                hover:bg-gray-700/50 hover:border-gray-500
                transition-all duration-200
                disabled:opacity-40 disabled:cursor-not-allowed
              `}
            >
              拒绝
            </button>
            <button
              onClick={handleConfirm}
              disabled={isDisabled}
              className={`
                flex-[2] py-2 px-4 rounded-xl text-sm font-medium
                bg-blue-600 text-white
                hover:bg-blue-500
                active:bg-blue-700
                transition-all duration-200
                disabled:opacity-40 disabled:cursor-not-allowed
                shadow-md shadow-blue-600/20
              `}
            >
              允许执行
            </button>
          </div>
        )}

        {/* 确认中状态 */}
        {(state === 'confirming' || state === 'denying') && (
          <div className="px-5 pb-4 pt-1">
            <div className="flex items-center justify-center gap-2 py-2 text-sm text-gray-400">
              <span className="inline-block w-4 h-4 border-2 border-gray-500 border-t-blue-400 rounded-full animate-spin" />
              <span>{state === 'confirming' ? '正在确认...' : '正在处理...'}</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};