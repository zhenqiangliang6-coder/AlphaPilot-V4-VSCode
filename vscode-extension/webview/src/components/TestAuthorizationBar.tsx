import React, { useState } from 'react';
import type { TestAuthorizationRequest } from './TestAuthorizationCard';

interface TestAuthorizationBarProps {
  requests: TestAuthorizationRequest[];
  onDecision: (taskId: string, action: 'run' | 'skip' | 'repair' | 'stop') => void;
}

function statusSummary(requests: TestAuthorizationRequest[]) {
  const pending = requests.filter((r) => r.status === 'pending').length;
  const running = requests.filter((r) => r.status === 'running').length;
  if (running > 0) return `运行中 (${running})`;
  if (pending > 0) return `${pending} 项待确认`;
  return '';
}

export const TestAuthorizationBar: React.FC<TestAuthorizationBarProps> = ({
  requests,
  onDecision,
}) => {
  const [expandedTaskId, setExpandedTaskId] = useState<string | null>(null);

  if (requests.length === 0) return null;

  const activeRequests = requests.filter((r) => r.status !== 'completed' && r.status !== 'skipped');
  if (activeRequests.length === 0) return null;

  const summary = statusSummary(activeRequests);

  return (
    <div
      className="fixed bottom-[72px] left-0 right-0 z-30 mx-auto max-w-screen-md animate-slide-up"
      role="region"
      aria-label="测试授权"
    >
      <div className="mx-4 rounded-xl border border-vscode-border bg-vscode-panel/95 shadow-2xl backdrop-blur-sm">
        <header className="flex items-center gap-3 border-b border-vscode-border/60 px-4 py-2.5">
          <span className="text-base" aria-hidden="true">🧪</span>
          <h3 className="flex-1 text-sm font-semibold text-vscode-fg">
            测试授权
            {summary && (
              <span className="ml-2 text-xs font-normal text-amber-400">
                {summary}
              </span>
            )}
          </h3>
          <span className="rounded-full bg-amber-500/15 px-2.5 py-0.5 text-[10px] font-medium text-amber-300">
            需确认
          </span>
        </header>

        <div className="max-h-64 overflow-y-auto">
          {activeRequests.map((request) => {
            const isExpanded = expandedTaskId === request.taskId;
            const isRunRequest = request.mode === 'run';
            const isPending = request.status === 'pending';

            return (
              <div
                key={request.taskId}
                className="border-b border-vscode-border/30 last:border-b-0"
              >
                <button
                  type="button"
                  onClick={() => setExpandedTaskId(isExpanded ? null : request.taskId)}
                  className="flex w-full items-center gap-3 px-4 py-2.5 text-left transition-colors hover:bg-vscode-list-hover/30"
                >
                  <span className="text-sm" aria-hidden="true">
                    {isRunRequest ? '▶️' : '🛠️'}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-xs font-medium text-vscode-fg">
                      {isRunRequest ? '运行测试' : '修复测试'}
                    </p>
                    <code className="block truncate font-mono text-[11px] text-gray-400">
                      {request.command || '(空命令)'}
                    </code>
                  </div>
                  <span className="text-[10px] text-gray-500">
                    {isExpanded ? '收起 ▲' : '展开 ▼'}
                  </span>
                </button>

                {isExpanded && (
                  <div className="space-y-2.5 border-t border-vscode-border/30 px-4 py-3">
                    {request.failureSummary && (
                      <div className="max-h-28 overflow-auto rounded-lg border border-red-500/20 bg-red-500/5 p-2.5">
                        <p className="mb-1 text-[11px] font-medium text-red-300">失败摘要</p>
                        <pre className="whitespace-pre-wrap break-words font-mono text-[11px] leading-relaxed text-vscode-fg">
                          {request.failureSummary}
                        </pre>
                      </div>
                    )}

                    <div className="grid grid-cols-1 gap-2 rounded-lg border border-vscode-border bg-vscode-bg/50 p-2.5">
                      <div>
                        <span className="text-[10px] uppercase tracking-wide text-gray-500">命令</span>
                        <code className="mt-0.5 block break-all font-mono text-xs text-blue-300">
                          {request.command}
                        </code>
                      </div>
                      <div>
                        <span className="text-[10px] uppercase tracking-wide text-gray-500">工作目录</span>
                        <code className="mt-0.5 block break-all font-mono text-xs text-gray-300">
                          {request.workspace}
                        </code>
                      </div>
                    </div>

                    {request.message && (
                      <p className="text-[11px] text-gray-400">{request.message}</p>
                    )}

                    {isPending && (
                      <div className="flex items-center justify-end gap-2 pt-1">
                        {isRunRequest ? (
                          <>
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                onDecision(request.taskId, 'skip');
                              }}
                              className="rounded-lg border border-vscode-border px-3 py-1.5 text-[11px] text-gray-400 transition-colors hover:bg-vscode-list-hover"
                            >
                              跳过
                            </button>
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                onDecision(request.taskId, 'run');
                              }}
                              className="rounded-lg bg-green-600 px-4 py-1.5 text-[11px] font-semibold text-white transition-colors hover:bg-green-700"
                            >
                              允许并运行测试
                            </button>
                          </>
                        ) : (
                          <>
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                onDecision(request.taskId, 'stop');
                              }}
                              className="rounded-lg border border-vscode-border px-3 py-1.5 text-[11px] text-gray-400 transition-colors hover:bg-vscode-list-hover"
                            >
                              停止
                            </button>
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                onDecision(request.taskId, 'repair');
                              }}
                              className="rounded-lg bg-amber-600 px-4 py-1.5 text-[11px] font-semibold text-white transition-colors hover:bg-amber-700"
                            >
                              提交修复
                            </button>
                          </>
                        )}
                      </div>
                    )}

                    {!isPending && (
                      <p className="text-[11px] text-gray-400">
                        {request.status === 'running' && '⏳ 测试正在运行…'}
                        {request.status === 'submitting' && '⏳ 正在提交修复任务…'}
                        {request.status === 'submitted' && '📤 修复任务已提交，等待应用文件变更。'}
                        {request.status === 'failed' && '⚠️ 操作未能完成。'}
                      </p>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};