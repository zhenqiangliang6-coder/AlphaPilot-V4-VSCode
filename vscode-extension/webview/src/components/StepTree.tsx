// src/components/StepTree.tsx
import React, { useState } from 'react';
import { Step } from '../store/chatStore';

interface StepTreeProps {
  steps: Step[];
}

const stepIcons: Record<Step['type'], string> = {
  analyze: '🔍',
  plan: '📋',
  write: '✍️',
  refine: '⚡',
  test: '✅'
};

const stepNames: Record<Step['type'], string> = {
  analyze: '分析需求',
  plan: '制定计划',
  write: '编写代码',
  refine: '优化改进',
  test: '测试验证'
};

const stepDescriptions: Record<Step['type'], string> = {
  analyze: '理解任务需求和上下文',
  plan: '设计实现方案和步骤',
  write: '生成具体代码实现',
  refine: '优化和改进代码质量',
  test: '验证功能正确性'
};

export const StepTree: React.FC<StepTreeProps> = ({ steps }) => {
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

  return (
    <div className="space-y-3">
      {/* 进度条 */}
      {totalSteps > 0 && (
        <div className="bg-vscode-list-hover rounded-lg p-3">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-semibold text-gray-400">
              📊 任务进度: {completedSteps}/{totalSteps} 步骤完成
            </span>
            <span className="text-xs text-blue-400">
              {Math.round(progressPercentage)}%
            </span>
          </div>
          <div className="w-full bg-vscode-bg h-2 rounded-full overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-blue-500 to-green-500 transition-all duration-500 ease-out"
              style={{ width: `${progressPercentage}%` }}
            />
          </div>
        </div>
      )}

      {/* 步骤列表 */}
      <div className="space-y-2">
        {steps.map((step, index) => {
          const isExpanded = expandedSteps.has(step.id);
          const hasOutput = step.output && Object.keys(step.output).length > 0;

          return (
            <div key={step.id}>
              {/* 步骤卡片 */}
              <div
                className={`flex items-center gap-3 p-3 rounded-lg cursor-pointer transition-all ${
                  step.status === 'running' 
                    ? 'bg-blue-500/20 border-l-4 border-blue-500 shadow-lg shadow-blue-500/20' 
                    : step.status === 'completed' 
                    ? 'bg-green-500/10 border-l-4 border-green-500' 
                    : step.status === 'failed' 
                    ? 'bg-red-500/10 border-l-4 border-red-500' 
                    : 'bg-vscode-list-hover/50 border-l-4 border-gray-600'
                }`}
                onClick={() => hasOutput && toggleStep(step.id)}
              >
                {/* 状态图标 */}
                <span className="text-xl flex-shrink-0">
                  {step.status === 'running' ? (
                    <span className="animate-spin">⏳</span>
                  ) : step.status === 'completed' ? (
                    '✅'
                  ) : step.status === 'failed' ? (
                    '❌'
                  ) : (
                    '⏸️'
                  )}
                </span>

                {/* 步骤信息 */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium">
                      {stepIcons[step.type]} {stepNames[step.type]}
                    </span>
                    {hasOutput && (
                      <span className="text-xs text-gray-500">
                        {isExpanded ? '▼' : '▶'}
                      </span>
                    )}
                  </div>
                  <div className="text-xs text-gray-500 mt-0.5">
                    {stepDescriptions[step.type]}
                  </div>
                </div>

                {/* 耗时 */}
                {step.startedAt && step.completedAt && (
                  <span className="text-xs text-gray-500 flex-shrink-0">
                    {((step.completedAt - step.startedAt) / 1000).toFixed(1)}s
                  </span>
                )}
              </div>

              {/* 展开的输出内容 */}
              {isExpanded && hasOutput && (
                <div className="ml-8 mt-2 p-3 bg-vscode-bg rounded border border-vscode-border text-xs">
                  <pre className="whitespace-pre-wrap overflow-x-auto">
                    {typeof step.output === 'string' 
                      ? step.output 
                      : JSON.stringify(step.output, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
