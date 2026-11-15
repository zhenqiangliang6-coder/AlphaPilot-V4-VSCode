// src/components/StepTree.tsx
// v4.0 Tech 升级 — 玻璃拟态步骤卡 + 流光进度条 + 状态脉冲/呼吸光 + 实时耗时徽章
// + 高度自适应展开动画（grid-rows 零依赖技巧）+ 长任务折叠窗口（>30 步仅展示最近步骤）

import React, { useEffect, useState } from 'react';
import { Step } from '../store/chatStore';

interface StepTreeProps {
  steps: Step[];
}

/** 超过该阈值启用折叠窗口（虚拟滚动替代方案）：仅展示最近步骤 + 可展开全部 */
const COLLAPSE_THRESHOLD = 30;

const stepIcons: Record<Step['type'], string> = {
  analyze: '🔍',
  plan: '📋',
  write: '✍️',
  refine: '✨',
  test: '🧪',
  fix: '🔧',
  doc: '📄',
  docstring: '📝',
  respond: '💬',
  profile: '📊',
  operate: '🛠️',
  changelog: '📋',
  deploy: '🚀',
  workspace: '📂',
  setup: '📦',
  vision_analysis: '👁️'
};

const stepNames: Record<Step['type'], string> = {
  analyze: '理解需求',
  plan: '规划方案',
  write: '编写代码',
  refine: '打磨优化',
  test: '运行测试',
  fix: '修复问题',
  doc: '编写文档',
  docstring: '补充注释',
  respond: '整理回复',
  profile: '性能分析',
  operate: '执行操作',
  changelog: '生成日志',
  deploy: '部署项目',
  workspace: '扫描项目',
  setup: '依赖处理',
  vision_analysis: '图像分析'
};

const stepDescriptions: Record<Step['type'], string> = {
  analyze: '正在分析你的任务需求…',
  plan: '设计最优的实现路线图',
  write: '将想法转化为优雅的代码',
  refine: '精雕细琢，让代码更出色',
  test: '验证每个功能都完美运行',
  fix: '快速定位并修复发现的问题',
  doc: '为项目生成清晰的使用文档',
  docstring: '为代码添加详细的文档字符串',
  respond: '组织语言，给你最清晰的回答',
  profile: '检测瓶颈，让代码跑得更快',
  operate: '处理系统级任务和配置',
  changelog: '记录本次更新的所有变更',
  deploy: '将项目推送到目标环境',
  workspace: '扫描项目结构，检查依赖和环境',
  setup: '处理 DEPENDS 声明，补齐缺失文件',
  vision_analysis: '正在分析图像内容…'
};

/** 状态点配色 */
const STATUS_DOT: Record<Step['status'], string> = {
  pending: 'bg-gray-500/60',
  running: 'bg-gradient-to-r from-cyan-400 to-indigo-400',
  completed: 'bg-emerald-400',
  failed: 'bg-rose-400',
};

const STATUS_CARD: Record<Step['status'], string> = {
  pending: 'bg-white/[0.02] border-l-2 border-l-gray-600/50',
  running: 'bg-indigo-500/[0.08] border-l-2 border-l-cyan-400',
  completed: 'bg-emerald-500/[0.04] border-l-2 border-l-emerald-400/80',
  failed: 'bg-rose-500/[0.06] border-l-2 border-l-rose-400',
};

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  const m = Math.floor(ms / 60000);
  const s = Math.round((ms % 60000) / 1000);
  return `${m}m${s.toString().padStart(2, '0')}s`;
}

const StepTree: React.FC<StepTreeProps> = ({ steps }) => {
  const [expandedSteps, setExpandedSteps] = useState<Set<string>>(new Set());
  const [showAll, setShowAll] = useState(false);
  const [now, setNow] = useState(Date.now());

  // running 步骤实时耗时（1s 心跳）
  const hasRunning = steps.some((s) => s.status === 'running');
  useEffect(() => {
    if (!hasRunning) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [hasRunning]);

  // 折叠窗口：长任务只渲染最近 N 步（含 running），避免数百步骤卡死 webview
  const needsWindow = steps.length > COLLAPSE_THRESHOLD && !showAll;
  const visibleSteps = needsWindow ? steps.slice(-COLLAPSE_THRESHOLD) : steps;
  const hiddenCount = steps.length - visibleSteps.length;

  const toggleStep = (stepId: string) => {
    setExpandedSteps((prev) => {
      const next = new Set(prev);
      if (next.has(stepId)) next.delete(stepId);
      else next.add(stepId);
      return next;
    });
  };

  // 进度统计
  const completedSteps = steps.filter((s) => s.status === 'completed').length;
  const totalSteps = steps.length;
  const progressPercentage = totalSteps > 0 ? (completedSteps / totalSteps) * 100 : 0;
  const failedSteps = steps.filter((s) => s.status === 'failed').length;
  const totalDuration = steps.reduce(
    (acc, s) => acc + (s.duration ?? (s.startedAt && s.completedAt ? s.completedAt - s.startedAt : 0)),
    0
  );

  const getStepDuration = (step: Step): number | null => {
    if (step.duration) return step.duration;
    if (step.status === 'running' && step.startedAt) return now - step.startedAt;
    if (step.completedAt && step.startedAt) return step.completedAt - step.startedAt;
    return null;
  };

  return (
    <div className="space-y-3">
      {/* 进度面板：流光进度条 + 总耗时 */}
      {totalSteps > 0 && (
        <div className="ap-glass ap-hairline rounded-lg p-3">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-semibold text-gray-400">
              📊 任务进度
              <span className="ap-tabular ml-1.5 text-gray-500">
                {completedSteps}/{totalSteps}
                {failedSteps > 0 && <span className="text-rose-400"> · {failedSteps} 失败</span>}
              </span>
            </span>
            <span className="flex items-center gap-2">
              {totalDuration > 0 && (
                <span className="ap-tabular text-[10px] text-gray-500">
                  ⏱ {formatDuration(totalDuration)}
                </span>
              )}
              <span className="ap-tabular text-xs ap-gradient-text font-semibold">
                {Math.round(progressPercentage)}%
              </span>
            </span>
          </div>
          <div className="w-full bg-white/[0.06] h-1.5 rounded-full overflow-hidden">
            <div
              className="h-full rounded-full ap-progress-fill"
              style={{ width: `${progressPercentage}%` }}
            />
          </div>
        </div>
      )}

      {/* 步骤列表 */}
      <div className="space-y-1.5">
        {/* 折叠窗口提示条 */}
        {needsWindow && (
          <button
            onClick={() => setShowAll(true)}
            className="w-full text-center text-[11px] text-gray-500 hover:text-indigo-400 transition-colors py-1.5 rounded-lg border border-dashed border-white/10 hover:border-indigo-400/40"
          >
            ⌃ 已折叠较早的 {hiddenCount} 步 · 点击展开全部
          </button>
        )}

        {visibleSteps.map((step, index) => {
          const isExpanded = expandedSteps.has(step.id);
          const hasOutput = step.output && Object.keys(step.output).length > 0;
          const isRunning = step.status === 'running';
          const dur = getStepDuration(step);

          return (
            <div
              key={step.id}
              className="ap-rise"
              style={{ '--d': `${Math.min(index * 35, 350)}ms` } as React.CSSProperties}
            >
              {/* 步骤卡片 */}
              <div
                className={`flex items-center gap-3 p-3 rounded-lg cursor-pointer transition-all duration-500 ap-glass ${STATUS_CARD[step.status]} ${
                  isRunning ? 'ap-breathe' : ''
                } ${hasOutput ? 'hover:bg-white/[0.05]' : 'cursor-default'}`}
                onClick={() => hasOutput && toggleStep(step.id)}
              >
                {/* 状态指示点（running 脉冲扩散） */}
                <span className="relative flex-shrink-0 w-2 h-2 rounded-full">
                  <span className={`absolute inset-0 rounded-full ${STATUS_DOT[step.status]}`} />
                  {isRunning && (
                    <span className={`absolute inset-0 rounded-full ap-dot ${STATUS_DOT.running}`} />
                  )}
                </span>

                {/* 步骤信息 */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-2">
                    <span
                      className={`font-medium text-sm truncate transition-colors duration-500 ${
                        step.status === 'completed'
                          ? 'text-gray-400'
                          : isRunning
                          ? 'text-indigo-300'
                          : 'text-gray-300'
                      }`}
                    >
                      {stepIcons[step.type]} {stepNames[step.type]}
                    </span>
                    <span className="flex items-center gap-2 flex-shrink-0">
                      {isRunning && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-indigo-500/15 text-indigo-300 border border-indigo-400/25">
                          执行中
                        </span>
                      )}
                      {dur !== null && (
                        <span className="ap-tabular text-[10px] px-1.5 py-0.5 rounded bg-white/[0.04] text-gray-500 border border-white/[0.07]">
                          {formatDuration(dur)}
                        </span>
                      )}
                      {hasOutput && (
                        <span
                          className={`text-gray-500 transition-transform duration-300 ${
                            isExpanded ? 'rotate-90' : ''
                          }`}
                        >
                          ▸
                        </span>
                      )}
                    </span>
                  </div>
                  <p className="text-xs text-gray-500 mt-0.5 truncate">
                    {stepDescriptions[step.type]}
                  </p>
                </div>
              </div>

              {/* 展开详情（高度自适应动画） */}
              <div className={`ap-collapse-grid ${isExpanded && hasOutput ? 'open' : ''}`}>
                <div className="ap-collapse-inner">
                  {hasOutput && (
                    <div className="mt-1.5 mb-1 ml-8 mr-2 p-3 bg-black/30 rounded-lg text-xs font-mono space-y-2 border border-white/[0.07]">
                      {step.output.file_ops && step.output.file_ops.length > 0 ? (
                        <>
                          <div className="text-gray-400">📂 FileOps 协议执行:</div>
                          {step.output.file_ops.map((op: any, idx: number) => (
                            <div key={idx} className="flex items-center gap-2">
                              <span className="text-blue-400">
                                {op.op === 'create' ? '➕' : op.op === 'test' ? '🧪' : op.op === 'doc' ? '📄' : '💾'}
                              </span>
                              <span className="text-gray-300">{op.path || JSON.stringify(op.data)}</span>
                            </div>
                          ))}
                        </>
                      ) : (
                        <pre className="whitespace-pre-wrap text-gray-300 max-h-40 overflow-y-auto">
                          {typeof step.output.text === 'string'
                            ? step.output.text.substring(0, 500)
                            : JSON.stringify(step.output)}
                        </pre>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export { StepTree };
