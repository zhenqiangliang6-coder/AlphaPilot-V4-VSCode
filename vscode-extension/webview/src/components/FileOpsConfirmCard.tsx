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
  taskId: string | null;
  onApplyAll: () => void;
  onRejectAll: () => void;
}

const FILE_ICONS: Record<string, string> = {
  '.py': '\uD83D\uDC0D',
  '.js': '\u26A1',
  '.ts': '\uD83D\uDEE0\uFE0F',
  '.tsx': '\u269B\uFE0F',
  '.jsx': '\u269B\uFE0F',
  '.json': '\uD83D\uDCCA',
  '.yaml': '\uD83D\uDCCB',
  '.yml': '\uD83D\uDCCB',
  '.html': '\uD83C\uDF10',
  '.css': '\uD83C\uDFA8',
  '.scss': '\uD83C\uDFA8',
  '.go': '\uD83D\uDC39',
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
  return FILE_ICONS[ext] || '\uD83D\uDCC4';
}

const ACTION_STYLE: Record<string, string> = {
  create: 'bg-green-500/15 text-green-400 border-green-500/30',
  modify: 'bg-yellow-500/15 text-yellow-400 border-yellow-500/30',
  delete: 'bg-red-500/15 text-red-400 border-red-500/30',
};

const ACTION_LABEL: Record<string, string> = {
  create: '\u2795 \u65B0\u5EFA',
  modify: '\u270F\uFE0F \u4FEE\u6539',
  delete: '\uD83D\uDDD1\uFE0F \u5220\u9664',
};

const FileOpRow: React.FC<{ op: FileOp; isExpanded: boolean; onToggle: () => void }> = ({
  op, isExpanded, onToggle,
}) => {
  const action = (op.op || op.action || 'create').toLowerCase();
  const type = op.file_type || op.type || 'file';
  const style = ACTION_STYLE[action] || ACTION_STYLE.create;
  const label = ACTION_LABEL[action] || action;

  if (type === 'folder') {
    return (
      <div className="flex items-center gap-2.5 px-3 py-2">
        <span className="text-base">\uD83D\uDCC2</span>
        <code className="text-sm text-blue-400 font-mono flex-1 truncate">{op.path}/</code>
        <span className="px-2 py-0.5 rounded text-[10px] font-medium bg-blue-500/15 text-blue-400 border border-blue-500/30">
          \uD83D\uDCC1 \u521B\u5EFA\u76EE\u5F55
        </span>
      </div>
    );
  }

  return (
    <div>
      <div
        onClick={onToggle}
        className="flex items-center gap-2.5 px-3 py-2 hover:bg-white/[0.03] cursor-pointer transition-colors group"
      >
        <span className="text-sm transition-transform duration-150"
          style={{ transform: isExpanded ? 'rotate(90deg)' : 'rotate(0deg)' }}>
          \u25B6
        </span>
        <span className="text-base">{getIcon(op.path)}</span>
        <code className="text-sm text-blue-400 font-mono flex-1 truncate">{op.path}</code>
        <span className={`px-2 py-0.5 rounded text-[10px] font-medium border ${style}`}>
          {label}
        </span>
        {op.reason && (
          <span className="hidden group-hover:inline text-[11px] text-gray-500 truncate max-w-[200px]">
            \uD83D\uDCA1 {op.reason}
          </span>
        )}
      </div>
      {isExpanded && op.content && (
        <div className="mx-3 mb-2 border border-white/[0.06] rounded-md overflow-hidden">
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
            {op.content.length > 3000 ? op.content.substring(0, 3000) + '\n... (\u5185\u5BB9\u8FC7\u957F\uFF0C\u5DF2\u622A\u65AD)' : op.content}
          </SyntaxHighlighter>
        </div>
      )}
    </div>
  );
};

export const FileOpsConfirmCard: React.FC<FileOpsConfirmCardProps> = ({
  fileOps,
  taskId,
  onApplyAll,
  onRejectAll,
}) => {
  const [expanded, setExpanded] = useState(false);
  const [expandedFiles, setExpandedFiles] = useState<Set<number>>(new Set());

  if (!fileOps || fileOps.length === 0) return null;

  const createCount = fileOps.filter((o) => (o.op || o.action || '').toLowerCase() === 'create' && (o.file_type || o.type) !== 'folder').length;
  const modifyCount = fileOps.filter((o) => (o.op || o.action || '').toLowerCase() === 'modify').length;
  const deleteCount = fileOps.filter((o) => (o.op || o.action || '').toLowerCase() === 'delete').length;
  const folderCount = fileOps.filter((o) => (o.file_type || o.type) === 'folder').length;

  const parts: string[] = [];
  if (folderCount > 0) parts.push(`${folderCount} \u4E2A\u76EE\u5F55`);
  if (createCount > 0) parts.push(`${createCount} \u4E2A\u65B0\u5EFA`);
  if (modifyCount > 0) parts.push(`${modifyCount} \u4E2A\u4FEE\u6539`);
  if (deleteCount > 0) parts.push(`${deleteCount} \u4E2A\u5220\u9664`);

  const toggleFile = (idx: number) => {
    setExpandedFiles((prev) => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx);
      else next.add(idx);
      return next;
    });
  };

  return (
    <div className="mx-3 mb-3 animate-slide-up">
      <div className="border border-white/[0.08] rounded-xl bg-[#1e1e1e] overflow-hidden shadow-lg ring-1 ring-white/[0.03]">
        <div
          onClick={() => setExpanded(!expanded)}
          className="flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-white/[0.02] transition-colors"
        >
          <span className="text-lg">\uD83D\uDCC1</span>
          <div className="flex-1 min-w-0">
            <div className="text-sm font-medium text-gray-200">
              \u5F85\u5E94\u7528\u7684\u6587\u4EF6\u64CD\u4F5C
            </div>
            <div className="text-xs text-gray-500 mt-0.5">
              {parts.join('\uFF0C')}
            </div>
          </div>
          <span className="text-gray-500 text-xs transition-transform duration-150"
            style={{ transform: expanded ? 'rotate(180deg)' : 'rotate(0deg)' }}>
            \u25BC
          </span>
        </div>

        {expanded && (
          <>
            <div className="border-t border-white/[0.06] max-h-[400px] overflow-y-auto divide-y divide-white/[0.04]">
              {fileOps.map((op, idx) => (
                <FileOpRow
                  key={idx}
                  op={op}
                  isExpanded={expandedFiles.has(idx)}
                  onToggle={() => toggleFile(idx)}
                />
              ))}
            </div>

            <div className="border-t border-white/[0.08] flex items-center gap-3 px-4 py-3 bg-white/[0.01]">
              <div className="flex-1 text-xs text-gray-500">
                \u26A0\uFE0F \u8BF7\u786E\u8BA4\u6587\u4EF6\u5185\u5BB9\u540E\u518D\u5E94\u7528
              </div>
              <button
                onClick={(e) => { e.stopPropagation(); onRejectAll(); }}
                className="px-4 py-2 text-xs text-gray-400 hover:text-gray-200 hover:bg-white/[0.05] rounded-lg transition-colors border border-white/[0.08]"
              >
                \uD83D\uDEAB \u653E\u5F03
              </button>
              <button
                onClick={(e) => { e.stopPropagation(); onApplyAll(); }}
                className="px-4 py-2 text-xs bg-gradient-to-r from-green-600 to-emerald-600 hover:from-green-500 hover:to-emerald-500 text-white rounded-lg font-medium transition-all shadow-md flex items-center gap-1.5"
              >
                <span>\u2705</span>
                <span>\u5E94\u7528\u5168\u90E8 ({fileOps.length})</span>
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
};