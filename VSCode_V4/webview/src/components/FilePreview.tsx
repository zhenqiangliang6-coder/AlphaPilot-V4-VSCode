// src/components/FilePreview.tsx
import React, { useState } from 'react';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';

interface FilePreviewProps {
  filename: string;
  content: string;
  language?: string;
  action?: 'create' | 'modify' | 'delete';
  reason?: string;
}

// 文件类型图标映射
const fileIcons: Record<string, string> = {
  '.py': '',
  '.js': '⚡',
  '.ts': '',
  '.tsx': '⚛️',
  '.jsx': '⚛️',
  '.md': '',
  '.json': '📊',
  '.yaml': '📋',
  '.yml': '📋',
  '.html': '🌐',
  '.css': '',
  '.scss': '🎨',
  '.java': '☕',
  '.cpp': '⚙️',
  '.c': '⚙️',
  '.h': '⚙️',
  '.go': '🐹',
  '.rs': '🦀',
  '.rb': '💎',
  '.php': '🐘',
  '.swift': '',
  '.kt': '',
  '.sh': '🖥️',
  '.bash': '🖥️',
  '.zsh': '🖥️',
  '.dockerfile': ''
};

// 获取文件图标
const getFileIcon = (filename: string): string => {
  const ext = '.' + filename.split('.').pop();
  return fileIcons[ext] || '📄';
};

// 获取语言类型
const getLanguage = (filename: string, fallback?: string): string => {
  if (fallback) return fallback;
  const ext = filename.split('.').pop()?.toLowerCase();
  const langMap: Record<string, string> = {
    py: 'python',
    js: 'javascript',
    ts: 'typescript',
    tsx: 'typescript',
    jsx: 'javascript',
    md: '``',
    json: 'json',
    yaml: 'yaml',
    yml: 'yaml',
    html: 'html',
    css: 'css',
    scss: 'scss',
    java: 'java',
    cpp: 'cpp',
    c: 'c',
    h: 'cpp',
    go: 'go',
    rs: 'rust',
    rb: 'ruby',
    php: 'php',
    swift: 'swift',
    kt: 'kotlin',
    sh: 'bash',
    bash: 'bash',
    zsh: 'bash',
    dockerfile: 'dockerfile',
  };
  return langMap[ext || ''] || 'text';
};

export const FilePreview: React.FC<FilePreviewProps> = ({
  filename,
  content,
  language,
  action = 'create',
  reason
}) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const [copied, setCopied] = useState(false);

  const lang = getLanguage(filename, language);
  const icon = getFileIcon(filename);

  // 操作类型对应的颜色和图标
  const actionConfig = {
    create: { color: 'green', icon: '➕', label: '新建' },
    modify: { color: 'blue', icon: '️', label: '修改' },
    delete: { color: 'red', icon: '🗑️', label: '删除' }
  };

  const actionInfo = actionConfig[action];

  const handleCopy = () => {
    navigator.clipboard.writeText(content).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  const handleToggle = () => {
    setIsExpanded(!isExpanded);
  };

  return (
    <div className="file-preview border border-vscode-border rounded-lg overflow-hidden bg-vscode-list-hover/50 my-2">
      {/* 文件头部 */}
      <div
        className="flex items-center justify-between px-4 py-3 bg-vscode-list-hover/80 cursor-pointer hover:bg-vscode-list-hover transition-colors"
        onClick={handleToggle}
      >
        <div className="flex items-center gap-3 flex-1 min-w-0">
          {/* 文件图标 */}
          <span className="text-xl">{icon}</span>
          
          {/* 文件名（蓝色高亮） */}
          <span className="text-blue-400 font-mono font-medium truncate">
            {filename}
          </span>
          
          {/* 操作标签 */}
          <span className={`px-2 py-0.5 rounded text-xs font-medium bg-${actionInfo.color}-500/20 text-${actionInfo.color}-400`}>
            {actionInfo.icon} {actionInfo.label}
          </span>

          {/* 原因标签 */}
          {reason && (
            <span className="px-2 py-0.5 rounded text-xs bg-gray-500/20 text-gray-400">
              {reason}
            </span>
          )}
        </div>

        {/* 右侧按钮 */}
        <div className="flex items-center gap-2 ml-2">
          {/* 复制按钮 */}
          <button
            onClick={(e) => {
              e.stopPropagation();
              handleCopy();
            }}
            className="px-2 py-1 text-xs bg-vscode-button-bg/80 hover:bg-vscode-button-bg text-vscode-button-fg rounded transition-all opacity-0 group-hover:opacity-100"
            title="复制代码"
          >
            {copied ? '✓ 已复制' : '📋 复制'}
          </button>

          {/* 展开/折叠图标 */}
          <span className="text-gray-400 text-sm transition-transform duration-200">
            {isExpanded ? '▼' : '▶'}
          </span>
        </div>
      </div>

      {/* 文件内容 */}
      {isExpanded && (
        <div className="border-t border-vscode-border">
          <div className="relative group">
            {/* 复制按钮 (悬浮显示) */}
            <button
              onClick={handleCopy}
              className="absolute top-2 right-2 px-3 py-1 text-xs bg-vscode-button-bg/90 hover:bg-vscode-button-bg text-vscode-button-fg rounded shadow-lg opacity-0 group-hover:opacity-100 transition-opacity z-10"
              title="复制全部代码"
            >
              {copied ? '✓ 已复制' : ' 复制全部'}
            </button>

            {/* 代码高亮 */}
            <div className="max-h-96 overflow-auto scrollbar-thin">
              <SyntaxHighlighter
                style={vscDarkPlus}
                language={lang}
                PreTag="div"
                customStyle={{
                  margin: 0,
                  borderRadius: 0,
                  fontSize: '13px',
                  lineHeight: '1.5'
                }}
              >
                {content}
              </SyntaxHighlighter>
            </div>
          </div>

          {/* 文件统计信息 */}
          <div className="px-4 py-2 bg-vscode-bg/50 text-xs text-gray-500 flex items-center justify-between">
            <span>{content.split('\n').length} 行</span>
            <span>{content.length} 字符</span>
            <span>{lang}</span>
          </div>
        </div>
      )}
    </div>
  );
};
