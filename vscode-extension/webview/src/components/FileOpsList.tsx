// src/components/FileOpsList.tsx
// ⭐ v2.7 FileOps Protocol - 文件操作列表面板
// ⭐ v3.1.1 增强：根据 from_step 展示彩色标签

import React from 'react';

// ⭐ v2.7 新增：声明 window.vscode 类型（VSCode Webview API）
declare global {
  interface Window {
    vscode?: {
      postMessage(message: any): void;
    };
  }
}

export interface FileOp {
  action: 'create' | 'modify' | 'delete';
  path: string;
  type: 'file' | 'folder';
  content?: string;
  language?: string;
  reason?: string;
  meta?: {
    from_step?: string;
    intent?: string;
  };
  from_step?: string; // ⭐ v3.1.1 兼容旧格式
}

export interface FileOpsListProps {
  show: boolean;
  setShow: (show: boolean) => void;
  fileOps: FileOp[];
  taskId: string | null;
}

// ⭐ v3.1.1 步骤颜色映射
const STEP_COLORS: Record<string, { bg: string; text: string; label: string }> = {
  write: { bg: 'bg-blue-500/20', text: 'text-blue-400', label: '生成' },
  refine: { bg: 'bg-purple-500/20', text: 'text-purple-400', label: '优化' },
  test: { bg: 'bg-green-500/20', text: 'text-green-400', label: '测试' },
  fix: { bg: 'bg-orange-500/20', text: 'text-orange-400', label: '修复' },
  doc: { bg: 'bg-cyan-500/20', text: 'text-cyan-400', label: '文档' },
  docstring: { bg: 'bg-pink-500/20', text: 'text-pink-400', label: 'Docstring' },
  default: { bg: 'bg-gray-500/20', text: 'text-gray-400', label: '其他' }
};

// ⭐ v3.1.1 获取步骤样式
const getStepStyle = (fromStep?: string) => {
  if (!fromStep) return STEP_COLORS.default;
  
  const step = fromStep.toLowerCase();
  return STEP_COLORS[step] || STEP_COLORS.default;
};

export const FileOpsList: React.FC<FileOpsListProps> = ({
  show,
  setShow,
  fileOps,
  taskId
}) => {
  if (!show || fileOps.length === 0) {
    return null;
  }

  // 获取操作类型图标和颜色
  const getActionIcon = (action: string) => {
    switch (action) {
      case 'create':
        return { icon: '➕', color: 'text-green-500', bg: 'bg-green-500/10' };
      case 'modify':
        return { icon: '✏️', color: 'text-yellow-500', bg: 'bg-yellow-500/10' };
      case 'delete':
        return { icon: '🗑️', color: 'text-red-500', bg: 'bg-red-500/10' };
      default:
        return { icon: '📄', color: 'text-gray-500', bg: 'bg-gray-500/10' };
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-vscode-panel border border-vscode-border rounded-lg shadow-2xl max-w-2xl w-full mx-4 max-h-[80vh] flex flex-col">
        {/* 头部 */}
        <div className="flex items-center justify-between p-4 border-b border-vscode-border">
          <div className="flex items-center gap-2">
            <span className="text-xl">📁</span>
            <h2 className="text-lg font-semibold text-vscode-fg">
              待应用的文件操作 ({fileOps.length})
            </h2>
          </div>
          <button
            onClick={() => setShow(false)}
            className="text-vscode-fg-muted hover:text-vscode-fg transition-colors"
          >
            ✕
          </button>
        </div>

        {/* 文件列表 */}
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {fileOps.map((op, index) => {
            const { icon, color, bg } = getActionIcon(op.action);
            const stepStyle = getStepStyle(op.from_step || op.meta?.from_step);
            
            return (
              <div
                key={index}
                className={`border border-vscode-border rounded p-3 hover:bg-vscode-hover transition-colors ${bg}`}
              >
                <div className="flex items-start gap-3">
                  {/* 操作图标 */}
                  <span className={`text-xl ${color}`}>{icon}</span>
                  
                  {/* 文件信息 */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <code className="text-sm text-vscode-fg font-mono truncate">
                        {op.path}
                      </code>
                      
                      {/* 语言标签 */}
                      {op.language && (
                        <span className="px-2 py-0.5 bg-blue-500/20 text-blue-400 text-xs rounded-full">
                          {op.language}
                        </span>
                      )}
                      
                      {/* 类型标签 */}
                      <span className="px-2 py-0.5 bg-gray-500/20 text-gray-400 text-xs rounded-full">
                        {op.type}
                      </span>
                      
                      {/* ⭐ v3.1.1 步骤来源标签（彩色） */}
                      {(op.from_step || op.meta?.from_step) && (
                        <span className={`px-2 py-0.5 ${stepStyle.bg} ${stepStyle.text} text-xs rounded-full`}>
                          {stepStyle.label}
                        </span>
                      )}
                    </div>
                    
                    {/* 操作原因 */}
                    {op.reason && (
                      <p className="text-xs text-vscode-fg-muted mt-1">
                        {op.reason}
                      </p>
                    )}
                    
                    {/* 来源步骤（详细信息） */}
                    {op.meta?.from_step && !op.from_step && (
                      <p className="text-xs text-vscode-fg-muted mt-1">
                        来源: {op.meta.from_step} 步骤
                      </p>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        {/* 底部按钮 */}
        <div className="flex items-center justify-end gap-3 p-4 border-t border-vscode-border bg-vscode-panel">
          <button
            onClick={() => setShow(false)}
            className="px-4 py-2 text-vscode-fg hover:bg-vscode-hover rounded transition-colors"
          >
            取消
          </button>
          <button
            onClick={() => {
              // ⭐ v2.7 应用文件操作
              console.log('✅ 应用文件操作:', fileOps.length);
              
              // 发送消息给 Extension
              if (window.vscode) {
                window.vscode.postMessage({
                  type: 'apply_file_ops',
                  taskId,
                  fileOps
                });
              } else {
                console.error('❌ window.vscode 未定义');
              }
              
              setShow(false);
            }}
            className="px-6 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded font-medium transition-colors flex items-center gap-2"
          >
            <span>✅</span>
            <span>应用所有改动</span>
          </button>
        </div>
      </div>
    </div>
  );
};