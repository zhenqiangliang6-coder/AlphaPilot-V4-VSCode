import React from 'react';

interface WorkspaceProgressToastProps {
  message: string;
  completed: boolean;
}

export const WorkspaceProgressToast: React.FC<WorkspaceProgressToastProps> = ({
  message,
  completed
}) => (
  <div
    className="fixed bottom-24 left-1/2 z-50 flex w-[min(360px,calc(100vw-2rem))] -translate-x-1/2 items-center gap-3 rounded-xl border border-vscode-border bg-vscode-panel/95 px-4 py-3 shadow-xl backdrop-blur-sm animate-fade-in"
    role="status"
    aria-live="polite"
  >
    {completed ? (
      <span className="text-green-400" aria-hidden="true">✓</span>
    ) : (
      <span
        className="h-4 w-4 shrink-0 animate-spin rounded-full border-2 border-blue-400/30 border-t-blue-400"
        aria-hidden="true"
      />
    )}
    <span className="min-w-0 truncate text-sm text-vscode-fg">
      {completed ? '项目检查完成' : message}
    </span>
  </div>
);
