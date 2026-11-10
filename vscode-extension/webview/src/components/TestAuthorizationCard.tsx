import React from 'react';

export type TestAuthorizationMode = 'run' | 'repair';
export type TestAuthorizationStatus =
  | 'pending'
  | 'running'
  | 'submitting'
  | 'submitted'
  | 'completed'
  | 'skipped'
  | 'failed';

export interface TestAuthorizationRequest {
  taskId: string;
  mode: TestAuthorizationMode;
  command: string;
  workspace: string;
  repairRounds: number;
  status: TestAuthorizationStatus;
  failureSummary?: string;
  message?: string;
}

interface TestAuthorizationCardProps {
  request: TestAuthorizationRequest;
  onDecision: (action: 'run' | 'skip' | 'repair' | 'stop') => void;
}

export const TestAuthorizationCard: React.FC<TestAuthorizationCardProps> = ({
  request,
  onDecision,
}) => {
  const isPending = request.status === 'pending';
  const isRunRequest = request.mode === 'run';
  const statusLabel = isPending
    ? '等待确认'
    : request.status === 'running'
      ? '运行中'
      : request.status === 'submitting'
        ? '提交中'
        : request.status === 'submitted'
          ? '已提交'
          : request.status === 'completed'
            ? '已通过'
            : request.status === 'skipped'
              ? '已停止'
              : '未完成';

  return (
    <section
      className="mx-4 mb-3 overflow-hidden rounded-xl border border-vscode-border bg-vscode-panel shadow-lg"
      aria-live="polite"
      aria-label={isRunRequest ? '测试运行授权' : '测试失败修复确认'}
    >
      <header className="flex items-start gap-3 border-b border-vscode-border bg-vscode-list-hover/50 px-4 py-3">
        <span className="text-xl" aria-hidden="true">{isRunRequest ? '🧪' : '🛠️'}</span>
        <div className="min-w-0 flex-1">
          <h3 className="text-sm font-semibold text-vscode-fg">
            {isRunRequest ? '需要你的授权才能运行测试' : '测试未通过，需要你决定下一步'}
          </h3>
          <p className="mt-1 text-xs leading-relaxed text-gray-400">
            {isRunRequest
              ? 'AlphaPilot 不会在你确认前执行测试命令。'
              : '你可以让 AlphaPilot 提交修复任务，也可以停止在这里。'}
          </p>
        </div>
        <span className={`shrink-0 rounded-full border px-2 py-1 text-[10px] font-medium ${
          isPending
            ? 'border-amber-500/30 bg-amber-500/10 text-amber-300'
            : request.status === 'failed'
              ? 'border-red-500/30 bg-red-500/10 text-red-300'
              : 'border-vscode-border bg-vscode-bg/60 text-gray-300'
        }`}>
          {statusLabel}
        </span>
      </header>

      <div className="space-y-3 px-4 py-3">
        {request.failureSummary && (
          <div className="max-h-36 overflow-auto rounded-lg border border-red-500/20 bg-red-500/5 p-3">
            <p className="mb-1 text-xs font-medium text-red-300">测试失败摘要</p>
            <pre className="whitespace-pre-wrap break-words font-mono text-[11px] leading-relaxed text-vscode-fg">
              {request.failureSummary}
            </pre>
          </div>
        )}

        <div className="rounded-lg border border-vscode-border bg-vscode-bg/60 p-3">
          <p className="mb-1 text-[11px] font-medium uppercase tracking-wide text-gray-500">测试命令</p>
          <code className="block break-all font-mono text-xs text-blue-300">{request.command}</code>
          <p className="mb-1 mt-3 text-[11px] font-medium uppercase tracking-wide text-gray-500">工作目录</p>
          <code className="block break-all font-mono text-xs text-gray-300">{request.workspace}</code>
        </div>

        {request.message && (
          <p className={`text-xs ${request.status === 'failed' ? 'text-red-300' : 'text-gray-300'}`}>
            {request.message}
          </p>
        )}
      </div>

      <footer className="flex flex-wrap items-center justify-end gap-2 border-t border-vscode-border px-4 py-3">
        {!isPending ? (
          <p className="mr-auto text-xs text-gray-400">
            {request.status === 'running' && '测试正在运行…'}
            {request.status === 'submitting' && '正在提交修复任务…'}
            {request.status === 'submitted' && '修复任务已提交，等待你应用文件变更。'}
            {request.status === 'completed' && '测试验证通过。'}
            {request.status === 'skipped' && '已停止，未执行后续操作。'}
            {request.status === 'failed' && '操作未能完成，请查看执行输出。'}
          </p>
        ) : isRunRequest ? (
          <>
            <button
              type="button"
              onClick={() => onDecision('skip')}
              className="rounded-lg border border-vscode-border px-3 py-2 text-xs text-gray-300 transition-colors hover:bg-vscode-list-hover focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-400"
            >
              跳过
            </button>
            <button
              type="button"
              onClick={() => onDecision('run')}
              className="rounded-lg bg-vscode-button-bg px-4 py-2 text-xs font-semibold text-vscode-button-fg transition-colors hover:brightness-110 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-300"
            >
              允许并运行测试
            </button>
          </>
        ) : (
          <>
            <button
              type="button"
              onClick={() => onDecision('stop')}
              className="rounded-lg border border-vscode-border px-3 py-2 text-xs text-gray-300 transition-colors hover:bg-vscode-list-hover focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-400"
            >
              停止
            </button>
            <button
              type="button"
              onClick={() => onDecision('repair')}
              className="rounded-lg bg-vscode-button-bg px-4 py-2 text-xs font-semibold text-vscode-button-fg transition-colors hover:brightness-110 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-300"
            >
              提交修复任务
            </button>
          </>
        )}
      </footer>
    </section>
  );
};
