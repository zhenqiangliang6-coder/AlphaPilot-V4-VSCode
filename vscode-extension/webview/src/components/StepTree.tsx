// src/components/StepTree.tsx
import React from 'react';
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

export const StepTree: React.FC<StepTreeProps> = ({ steps }) => {
  return (
    <div className="space-y-2">
      <div className="text-xs font-semibold text-gray-400 mb-2">执行步骤:</div>
      {steps.map((step, index) => (
        <div
          key={step.id}
          className={`flex items-center gap-2 text-sm p-2 rounded transition-all ${
            step.status === 'running' ? 'bg-blue-500/20 border-l-2 border-blue-500' :
            step.status === 'completed' ? 'bg-green-500/10' :
            step.status === 'failed' ? 'bg-red-500/10' :
            'bg-vscode-list-hover/50'
          }`}
        >
          {/* 状态图标 */}
          <span className="text-lg">
            {step.status === 'running' ? '⏳' :
             step.status === 'completed' ? '✅' :
             step.status === 'failed' ? '❌' :
             '⏸️'}
          </span>

          {/* 步骤名称 */}
          <span className="flex-1">
            {stepIcons[step.type]} {stepNames[step.type]}
          </span>

          {/* 耗时 */}
          {step.startedAt && step.completedAt && (
            <span className="text-xs text-gray-500">
              {((step.completedAt - step.startedAt) / 1000).toFixed(1)}s
            </span>
          )}
        </div>
      ))}
    </div>
  );
};
