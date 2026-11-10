// src/components/StepPanel.tsx
import React, { useState } from 'react';
import { Step } from '../store/chatStore';

interface StepPanelProps {
  steps: Step[];
  currentPhase?: string | null;
  isStreaming?: boolean;
}

// 步骤配置 — 拟人化、美观的步骤名称
const stepConfig: Record<string, {
  icon: string;
  label: string;
  description: string;
  color: string;
  bgColor: string;
}> = {
  analyze: {
    icon: '🔍',
    label: '理解需求',
    description: '正在分析你的任务需求…',
    color: 'blue',
    bgColor: 'bg-blue-500'
  },
  plan: {
    icon: '📋',
    label: '规划方案',
    description: '设计最优的实现路线图',
    color: 'yellow',
    bgColor: 'bg-yellow-500'
  },
  write: {
    icon: '✍️',
    label: '编写代码',
    description: '将想法转化为优雅的代码',
    color: 'green',
    bgColor: 'bg-green-500'
  },
  refine: {
    icon: '✨',
    label: '打磨优化',
    description: '精雕细琢，让代码更出色',
    color: 'purple',
    bgColor: 'bg-purple-500'
  },
  test: {
    icon: '🧪',
    label: '运行测试',
    description: '验证每个功能都完美运行',
    color: 'cyan',
    bgColor: 'bg-cyan-500'
  },
  fix: {
    icon: '🔧',
    label: '修复问题',
    description: '快速定位并修复发现的问题',
    color: 'orange',
    bgColor: 'bg-orange-500'
  },
  doc: {
    icon: '📄',
    label: '编写文档',
    description: '为项目生成清晰的使用文档',
    color: 'pink',
    bgColor: 'bg-pink-500'
  },
  docstring: {
    icon: '📝',
    label: '补充注释',
    description: '为代码添加详细的文档字符串',
    color: 'indigo',
    bgColor: 'bg-indigo-500'
  },
  respond: {
    icon: '💬',
    label: '整理回复',
    description: '组织语言，给你最清晰的回答',
    color: 'teal',
    bgColor: 'bg-teal-500'
  },
  profile: {
    icon: '📊',
    label: '性能分析',
    description: '检测瓶颈，让代码跑得更快',
    color: 'rose',
    bgColor: 'bg-rose-500'
  },
  operate: {
    icon: '🛠️',
    label: '执行操作',
    description: '处理系统级任务和配置',
    color: 'slate',
    bgColor: 'bg-slate-500'
  },
  changelog: {
    icon: '📋',
    label: '生成日志',
    description: '记录本次更新的所有变更',
    color: 'amber',
    bgColor: 'bg-amber-500'
  },
  deploy: {
    icon: '🚀',
    label: '部署项目',
    description: '将项目推送到目标环境',
    color: 'emerald',
    bgColor: 'bg-emerald-500'
  }
};

export const StepPanel: React.FC<StepPanelProps> = ({ 
  steps, 
  currentPhase, 
  isStreaming = false 
}) => {
  const [expandedSteps, setExpandedSteps] = useState<Set<string>>(new Set());

  const toggleStep = (stepId: string) => {
    const newExpanded = new Set(expandedSteps);
    if (newExpanded.has(stepId)) {
      newExpanded.delete(stepId);
    } else {
      newExpanded.add(stepId);
    }
    setExpandedSteps(newExpanded);
  };

  // 计算进度
  const completedSteps = steps.filter(s => s.status === 'completed').length;
  const totalSteps = steps.length;
  const progressPercentage = totalSteps > 0 ? (completedSteps / totalSteps) * 100 : 0;

  // 获取当前步骤索引
  const currentStepIndex = steps.findIndex(s => s.status === 'running');

  if (steps.length === 0) {
    return null;
  }

  return (
    <div className="step-panel bg-vscode-list-hover rounded-xl border border-vscode-border overflow-hidden">
      {/* 头部：进度概览 */}
      <div className="px-4 py-3 border-b border-vscode-border bg-vscode-bg/50">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold">执行步骤</span>
            {isStreaming && (
              <span className="px-2 py-0.5 bg-blue-500/20 text-blue-400 rounded-full text-xs animate-pulse">
                执行中
              </span>
            )}
          </div>
          <span className="text-xs text-gray-400">
            {completedSteps}/{totalSteps} 完成
          </span>
        </div>
        
        {/* 进度条 */}
        <div className="w-full bg-vscode-bg h-2 rounded-full overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-blue-500 via-green-500 to-cyan-500 transition-all duration-500 ease-out"
            style={{ width: `${progressPercentage}%` }}
          />
        </div>
      </div>

      {/* 步骤列表 */}
      <div className="p-4 space-y-3">
        {steps.map((step, index) => {
          const config = stepConfig[step.type] || stepConfig.analyze;
          const isExpanded = expandedSteps.has(step.id);
          const isCurrent = currentStepIndex === index;
          const hasOutput = step.output && Object.keys(step.output).length > 0;
          const isCompleted = step.status === 'completed';
          const isRunning = step.status === 'running';
          const isPending = step.status === 'pending';

          return (
            <div key={step.id} className="relative">
              {/* 连接线 */}
              {index < steps.length - 1 && (
                <div className="absolute left-5 top-10 w-0.5 h-8 bg-vscode-border" />
              )}

              {/* 步骤卡片 */}
              <div
                className={`flex items-start gap-3 p-3 rounded-lg cursor-pointer transition-all duration-200 ${
                  isRunning 
                    ? 'bg-blue-500/10 border-2 border-blue-500 shadow-lg shadow-blue-500/20' 
                    : isCompleted 
                    ? 'bg-green-500/5 border border-green-500/30' 
                    : 'bg-vscode-bg/50 border border-vscode-border hover:border-vscode-border/80'
                }`}
                onClick={() => hasOutput && toggleStep(step.id)}
              >
                {/* 步骤图标 */}
                <div className="flex-shrink-0 relative">
                  <div className={`w-10 h-10 rounded-full flex items-center justify-center text-lg ${
                    isCompleted ? `${config.bgColor}/20` : 
                    isRunning ? `${config.bgColor}/30 animate-pulse` : 
                    'bg-gray-500/20'
                  }`}>
                    {isCompleted ? '✅' : 
                     isRunning ? <span className="animate-spin">⏳</span> : 
                     config.icon}
                  </div>
                  
                  {/* 步骤编号 */}
                  <div className="absolute -top-1 -right-1 w-5 h-5 bg-vscode-bg border-2 border-vscode-border rounded-full flex items-center justify-center text-xs font-bold">
                    {index + 1}
                  </div>
                </div>

                {/* 步骤信息 */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-medium text-sm">
                      {config.icon} {config.label}
                    </span>
                    {step.duration && (
                      <span className="text-xs text-gray-500">
                        {(step.duration / 1000).toFixed(1)}s
                      </span>
                    )}
                  </div>
                  
                  <p className="text-xs text-gray-400">
                    {config.description}
                  </p>

                  {/* 当前阶段标签 */}
                  {isRunning && currentPhase && (
                    <div className="mt-2 inline-flex items-center gap-1 px-2 py-1 bg-blue-500/20 rounded text-xs text-blue-400">
                      <span className="animate-pulse">●</span>
                      正在执行: {currentPhase}
                    </div>
                  )}
                </div>

                {/* 展开图标 */}
                {hasOutput && (
                  <span className="text-gray-400 text-sm transition-transform duration-200 mt-2">
                    {isExpanded ? '▼' : '▶'}
                  </span>
                )}
              </div>

              {/* 展开详情 */}
              {isExpanded && hasOutput && (
                <div className="mt-2 ml-12 p-3 bg-black/30 rounded-lg text-xs font-mono space-y-2 border border-gray-700 animate-fade-in">
                  {step.output.file_ops && step.output.file_ops.length > 0 ? (
                    <>
                      <div className="text-gray-400 mb-2">📂 FileOps 操作:</div>
                      {step.output.file_ops.map((op: any, idx: number) => (
                        <div key={idx} className="flex items-center gap-2 py-1">
                          <span className="text-blue-400">
                            {op.op === 'create' ? '➕' : op.op === 'modify' ? '✏️' : op.op === 'delete' ? '🗑️' : '💾'}
                          </span>
                          <span className="text-gray-300 font-mono">{op.path}</span>
                          {op.reason && (
                            <span className="text-gray-500 text-xs">({op.reason})</span>
                          )}
                        </div>
                      ))}
                    </>
                  ) : (
                    <pre className="whitespace-pre-wrap text-gray-300 max-h-40 overflow-y-auto">
                      {typeof step.output.text === 'string' 
                        ? step.output.text.substring(0, 500) 
                        : JSON.stringify(step.output, null, 2)}
                    </pre>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};