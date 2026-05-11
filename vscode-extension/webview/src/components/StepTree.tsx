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
  refine: '优化和改进代码质量 (v3.0)',
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
                  <div className="flex items-center justify-between">
                    <span className="font-medium text-sm truncate">
                      {stepIcons[step.type]} {stepNames[step.type]}
                    </span>
                    {step.duration && (
                      <span className="text-xs text-gray-500">
                        {(step.duration / 1000).toFixed(1)}s
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-gray-400 mt-1 truncate">
                    {stepDescriptions[step.type]}
                  </p>
                </div>
              </div>

              {/* 展开详情 (v3.0 FileOps 预览) */}
              {isExpanded && hasOutput && (
                <div className="mt-2 ml-8 p-3 bg-black/30 rounded-lg text-xs font-mono space-y-2 border border-gray-700">
                  {step.output.file_ops && step.output.file_ops.length > 0 ? (
                    <>
                      <div className="text-gray-400">📂 v3.0 FileOps 协议执行:</div>
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
                      {typeof step.output.text === 'string' ? step.output.text.substring(0, 500) : JSON.stringify(step.output)}
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
