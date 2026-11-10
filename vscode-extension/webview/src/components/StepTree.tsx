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