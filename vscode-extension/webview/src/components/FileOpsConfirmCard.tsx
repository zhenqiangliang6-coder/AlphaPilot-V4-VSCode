// src/components/FileOpsConfirmCard.tsx
// v4.0 Tech 动效包 — 玻璃拟态卡片 + 行 stagger 入场 + 按压微反馈 + 退场收起动画
// 交互细节：
//   - 文件行依次滑入（ap-rise + 递增 delay）
//   - 应用/放弃时先播放收起动画（ap-exit 280ms）再真正执行回调
//   - 按钮按压弹性反馈（ap-press / active:scale）
//   - 行 hover 微移 + 徽章高亮

import React, { useState } from 'react';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';

export interface FileOp {
  op?: string;
  action?: string;
  path: string;
  file_type?: string;
  type?: string;
  content?: string;
  language?: string;
  reason?: string;
}

interface FileOpsConfirmCardProps {
  fileOps: FileOp[];
  onApplyAll: () => void;
  onRejectAll: () => void;
}

const FILE_ICONS: Record<string, string> = {
  '.py': '🐍',
  '.js': '⚡',
  '.ts': '🛠️',
  '.tsx': '⚛️',
  '.jsx': '⚛️',
  '.json': '📊',
  '.yaml': '📋',
  '.yml': '📋',
  '.html': '🌐',
  '.css': '🎨',
  '.scss': '🎨',
  '.go': '🐹',
};

const LANG_MAP: Record<string, string> = {
  py: 'python', js: 'javascript', ts: 'typescript', tsx: 'tsx',
  jsx: 'jsx', json: 'json', yaml: 'yaml', yml: 'yaml',
  html: 'html', css: 'css', scss: 'scss', go: 'go',
};

function getLang(filename: string, fallback?: string): string {
  if (fallback) return fallback;
  const ext = filename.split('.').pop()?.toLowerCase() || '';
  return LANG_MAP[ext] || 'text';
}

function getIcon(filename: string): string {
  const ext = '.' + filename.split('.').pop();
  return FILE_ICONS[ext] || '📄';
}

const ACTION_STYLE: Record<string, string> = {
  create: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
  modify: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
  delete: 'bg-rose-500/15 text-rose-400 border-rose-500/30',
};

const ACTION_LABEL: Record<string, string> = {
  create: '➕ 新建',
  modify: '✏️ 修改',
  delete: '🗑️ 删除',
};

/** 文件行 — stagger 入场 + hover 微移 + 展开预览 */
const FileOpRow: React.FC<{
  op: FileOp;
  index: number;
  isExpanded: boolean;
  onToggle: () => void;
}> = ({ op, index, isExpanded, onToggle }) => {
  const action = (op.op || op.action || 'create').toLowerCase();
  const type = op.file_type || op.type || 'file';
  const style = ACTION_STYLE[action] || ACTION_STYLE.create;
  const label = ACTION_LABEL[action] || action;

  if (type === 'folder') {
    return (
      <div
        className="flex items-center gap-2.5 px-3 py-2 ap-rise"
        style={{ '--d': `${Math.min(index * 40, 480)}ms` } as React.CSSProperties}
      >
        <span className="text-base">📂</span>
        <code className="text-sm text-blue-400 font-mono flex-1 truncate">{op.path}/</code>
        <span className="px-2 py-0.5 rounded text-[10px] font-medium bg-blue-500/15 text-blue-400 border border-blue-500/30">
          📁 创建目录
        </span>
      </div>
    );
  }

  return (
    <div
      className="ap-rise"
      style={{ '--d': `${Math.min(index * 40, 480)}ms` } as React.CSSProperties}
    >
      <div
        onClick={onToggle}
        className={`flex items-center gap-2.5 px-3 py-2 cursor-pointer transition-all duration-300 group ${
          isExpanded
            ? 'bg-indigo-500/10 ring-1 ring-inset ring-indigo-500/25'
            : 'hover:bg-white/[0.04] hover:translate-x-0.5'
        }`}
      >
        <span
          className="text-sm transition-transform duration-300"
          style={{ transform: isExpanded ? 'rotate(90deg)' : 'rotate(0deg)' }}
        >
          ▶
        </span>
        <span className="text-base">{getIcon(op.path)}</span>
        <code className="text-sm text-blue-400 font-mono flex-1 truncate">{op.path}</code>
        <span
          className={`px-2 py-0.5 rounded text-[10px] font-medium border transition-transform duration-300 group-hover:scale-105 ${style}`}
        >
          {label}
        </span>
        {op.reason && (
          <span className="hidden group-hover:inline text-[11px] text-gray-500 truncate max-w-[200px]">
            💡 {op.reason}
          </span>
        )}
      </div>

      {/* 展开预览（高度自适应动画） */}
      <div className={`ap-collapse-grid ${isExpanded && op.content ? 'open' : ''}`}>
        <div className="ap-collapse-inner">
          {op.content && (
            <div className="mx-3 mb-2 border border-indigo-500/20 rounded-md overflow-hidden">
              <SyntaxHighlighter
                style={vscDarkPlus}
                language={getLang(op.path, op.language)}
                PreTag="div"
                customStyle={{
                  margin: 0,
                  borderRadius: '0 0 6px 6px',
                  fontSize: '12px',
                  lineHeight: '1.5',
                  maxHeight: '240px',
                }}
              >
                {op.content.length > 3000 ? op.content.substring(0, 3000) + '\n... (内容过长，已截断)' : op.content}
              </SyntaxHighlighter>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export const FileOpsConfirmCard: React.FC<FileOpsConfirmCardProps> = ({
  fileOps,
  onApplyAll,
  onRejectAll,
}) => {
  const [expandedFiles, setExpandedFiles] = useState<Set<number>>(new Set());
  const [closing, setClosing] = useState(false);
  const [applied, setApplied] = useState(false);

  if (!fileOps || fileOps.length === 0) return null;

  const createCount = fileOps.filter((o) => (o.op || o.action || '').toLowerCase() === 'create' && (o.file_type || o.type) !== 'folder').length;
  const modifyCount = fileOps.filter((o) => (o.op || o.action || '').toLowerCase() === 'modify').length;
  const deleteCount = fileOps.filter((o) => (o.op || o.action || '').toLowerCase() === 'delete').length;
  const folderCount = fileOps.filter((o) => (o.file_type || o.type) === 'folder').length;
  const fileCount = fileOps.length - folderCount;

  const parts: string[] = [];
  if (folderCount > 0) parts.push(`${folderCount} 个目录`);
  if (createCount > 0) parts.push(`${createCount} 个新建`);
  if (modifyCount > 0) parts.push(`${modifyCount} 个修改`);
  if (deleteCount > 0) parts.push(`${deleteCount} 个删除`);

  const toggleFile = (idx: number) => {
    setExpandedFiles((prev) => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx);
      else next.add(idx);
      return next;
    });
  };

  /** 退场编排：先播收起动画（ap-exit 280ms），再执行真正的回调 */
  const closeWith = (isApply: boolean) => {
    if (closing) return;
    setClosing(true);
    setApplied(isApply);
    window.setTimeout(() => (isApply ? onApplyAll() : onRejectAll()), 280);
  };

  return (
    <div className={`mx-3 mb-3 ${closing ? 'ap-exit' : 'animate-slide-up'}`}>
      <div className="ap-glass ap-hairline rounded-xl overflow-hidden shadow-xl shadow-indigo-500/[0.06]">
        {/* 头部：玻璃拟态 + 渐变统计徽章 */}
        <div className="flex items-center gap-3 px-4 py-3 bg-gradient-to-r from-indigo-500/[0.08] to-cyan-500/[0.04]">
          <span className="text-lg">📁</span>
          <div className="flex-1 min-w-0">
            <div className="text-sm font-medium text-gray-200">
              已生成 <span className="ap-tabular ap-gradient-text font-semibold">{fileCount}</span> 个文件，待确认应用
            </div>
            <div className="text-xs text-gray-500 mt-0.5">
              {parts.length > 0 ? parts.join('，') : `${fileOps.length} 项变更`}
            </div>
          </div>
          <span className="ap-tabular px-2 py-0.5 rounded text-[11px] font-medium bg-indigo-500/15 text-indigo-300 border border-indigo-400/30 shrink-0">
            {fileOps.length} 项变更
          </span>
        </div>

        {/* 文件列表：stagger 入场，点击预览内容 */}
        <div className="border-t border-white/[0.06] max-h-[360px] overflow-y-auto divide-y divide-white/[0.04]">
          {fileOps.map((op, idx) => (
            <FileOpRow
              key={idx}
              op={op}
              index={idx}
              isExpanded={expandedFiles.has(idx)}
              onToggle={() => toggleFile(idx)}
            />
          ))}
        </div>

        {/* 底部按钮：按压微反馈 + 退场反馈 */}
        <div className="border-t border-white/[0.08] flex items-center gap-3 px-4 py-3 bg-white/[0.01]">
          <div className="flex-1 text-xs text-gray-500">
            {closing ? (
              <span className="ap-rise">
                {applied ? '✅ 正在应用文件变更…' : '已放弃本次变更'}
              </span>
            ) : (
              <>⚠️ 点击文件可预览内容，确认无误后应用</>
            )}
          </div>
          <button
            onClick={() => closeWith(false)}
            disabled={closing}
            className="ap-press px-4 py-2 text-xs text-gray-400 hover:text-gray-200 hover:bg-white/[0.05] rounded-lg transition-colors border border-white/[0.08] disabled:opacity-50"
          >
            🚫 放弃
          </button>
          <button
            onClick={() => closeWith(true)}
            disabled={closing}
            className="ap-press px-4 py-2 text-xs bg-gradient-to-r from-emerald-600 to-cyan-600 hover:from-emerald-500 hover:to-cyan-400 text-white rounded-lg font-medium shadow-md shadow-emerald-900/30 hover:shadow-emerald-500/25 flex items-center gap-1.5 disabled:opacity-60"
          >
            <span>✅</span>
            <span>应用全部 ({fileOps.length})</span>
          </button>
        </div>
      </div>
    </div>
  );
};
