// src/components/FileOpsList.tsx
// ⭐ v3.2 FileOps Protocol - 文件操作列表面板（升级：使用FilePreview组件）

import React from 'react';
import { FilePreview } from './FilePreview';  // ⭐ v3.2 新增

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

export const FileOpsList: React.FC<FileOpsListProps> = ({
  show,
  setShow,
  fileOps,
  taskId
}) => {
  if (!show || fileOps.length === 0) {
    return null;
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 backdrop-blur-sm">
      <div className="bg-vscode-panel border border-vscode-border rounded-xl shadow-2xl max-w-3xl w-full mx-4 max-h-[85vh] flex flex-col">
        {/* 头部 */}
        <div className="flex items-center justify-between p-5 border-b border-vscode-border bg-gradient-to-r from-blue-500/10 to-purple-500/10">
          <div className="flex items-center gap-3">
            <span className="text-2xl">📁</span>
            <div>
              <h2 className="text-lg font-semibold text-vscode-fg">
                待应用的文件操作
              </h2>
              <p className="text-xs text-vscode-fg-muted mt-1">
                共 {fileOps.length} 个文件需要{fileOps.some(op => op.action === 'create') ? '创建' : '修改'}
              </p>
            </div>
          </div>
          <button
            onClick={() => setShow(false)}
            className="w-8 h-8 flex items-center justify-center rounded-full hover:bg-vscode-hover transition-colors text-vscode-fg-muted hover:text-vscode-fg"
          >
            ✕
          </button>
        </div>

        {/* 文件列表 */}
        <div className="flex-1 overflow-y-auto p-5 space-y-3 scrollbar-thin">
          {fileOps.map((op, index) => {
            if (op.type === 'folder') {
              // 文件夹操作单独显示
              return (
                <div
                  key={index}
                  className="flex items-center gap-3 p-3 bg-vscode-list-hover/50 border border-vscode-border rounded-lg"
                >
                  <span className="text-2xl">📂</span>
                  <div className="flex-1">
                    <code className="text-sm text-blue-400 font-mono">
                      {op.path}/
                    </code>
                    <p className="text-xs text-vscode-fg-muted mt-1">
                      创建目录
                    </p>
                  </div>
                </div>
              );
            }

            // 文件操作使用 FilePreview 组件
            return (
              <FilePreview
                key={index}
                filename={op.path}
                content={op.content || ''}
                language={op.language}
                action={op.action}
                reason={op.reason || op.meta?.from_step ? `来自 ${op.meta?.from_step || op.from_step} 步骤` : undefined}
              />
            );
          })}
        </div>

        {/* 底部按钮 */}
        <div className="flex items-center justify-between gap-3 p-5 border-t border-vscode-border bg-vscode-panel">
          <div className="text-xs text-vscode-fg-muted">
            ⚠️ 请仔细检查文件内容后再应用
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={() => setShow(false)}
              className="px-5 py-2.5 text-vscode-fg hover:bg-vscode-hover rounded-lg transition-colors font-medium"
            >
              取消
            </button>
            <button
              onClick={() => {
                console.log('✅ 应用文件操作:', fileOps.length);
                
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
              className="px-6 py-2.5 bg-gradient-to-r from-blue-600 to-blue-700 hover:from-blue-700 hover:to-blue-800 text-white rounded-lg font-medium transition-all shadow-lg hover:shadow-xl flex items-center gap-2"
            >
              <span>✅</span>
              <span>应用所有改动</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};