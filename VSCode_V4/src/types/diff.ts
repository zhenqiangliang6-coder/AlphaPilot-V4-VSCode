// src/types/diff.ts
// ============================================================
// Diff/Patch 系统类型定义
// 对标 Cursor/Windsurf 的代码修改能力
// ============================================================

/**
 * 代码变更类型
 */
export type ChangeType = 'add' | 'delete' | 'modify';

/**
 * 单个代码块变更
 */
export interface CodeChange {
  /**
   * 变更类型
   */
  type: ChangeType;
  
  /**
   * 文件路径
   */
  file_path: string;
  
  /**
   * 原始内容 (删除/修改时有值)
   */
  original_content?: string;
  
  /**
   * 修改后内容 (添加/修改时有值)
   */
  modified_content?: string;
  
  /**
   * 起始行号 (从1开始)
   */
  start_line: number;
  
  /**
   * 结束行号
   */
  end_line: number;
  
  /**
   * Unified Diff 格式
   */
  diff: string;
  
  /**
   * 变更描述 (AI 生成)
   */
  description?: string;
}

/**
 * 文件级别的 Diff
 */
export interface FileDiff {
  /**
   * 文件路径
   */
  file_path: string;
  
  /**
   * 原始内容
   */
  original_content: string;
  
  /**
   * 修改后内容
   */
  modified_content: string;
  
  /**
   * Unified Diff
   */
  unified_diff: string;
  
  /**
   * 变更统计
   */
  stats: {
    additions: number;
    deletions: number;
    changes_count: number;
  };
  
  /**
   * 语言类型
   */
  language: string;
}

/**
 * 多文件 Patch
 */
export interface MultiFilePatch {
  /**
   * 任务ID
   */
  task_id: string;
  
  /**
   * 所有文件变更
   */
  file_diffs: FileDiff[];
  
  /**
   * 总体统计
   */
  total_stats: {
    files_changed: number;
    total_additions: number;
    total_deletions: number;
  };
  
  /**
   * 生成时间
   */
  created_at: number;
  
  /**
   * AI 生成的提交信息
   */
  commit_message?: string;
}

/**
 * Patch 应用状态
 */
export type PatchStatus = 'pending' | 'applied' | 'rejected' | 'partial';

/**
 * Patch 应用结果
 */
export interface PatchApplicationResult {
  /**
   * 任务ID
   */
  task_id: string;
  
  /**
   * 文件路径
   */
  file_path: string;
  
  /**
   * 应用状态
   */
  status: PatchStatus;
  
  /**
   * 错误信息 (失败时)
   */
  error?: string;
  
  /**
   * 备份文件路径 (应用前自动备份)
   */
  backup_path?: string;
  
  /**
   * 应用时间
   */
  applied_at?: number;
}

/**
 * Diff 查看器配置
 */
export interface DiffViewerConfig {
  /**
   * 是否显示行号
   */
  show_line_numbers: boolean;
  
  /**
   * 是否启用语法高亮
   */
  enable_syntax_highlighting: boolean;
  
  /**
   * 视图模式: 'split' | 'inline'
   */
  view_mode: 'split' | 'inline';
  
  /**
   * 是否忽略空白变化
   */
  ignore_whitespace: boolean;
}

/**
 * 用户确认操作
 */
export interface UserConfirmation {
  /**
   * 任务ID
   */
  task_id: string;
  
  /**
   * 文件路径
   */
  file_path: string;
  
  /**
   * 用户选择: 'accept' | 'reject' | 'modify'
   */
  action: 'accept' | 'reject' | 'modify';
  
  /**
   * 用户修改的内容 (如果 action === 'modify')
   */
  user_modified_content?: string;
  
  /**
   * 确认时间
   */
  confirmed_at: number;
}

/**
 * 工具函数: 生成 Unified Diff
 */
export function generateUnifiedDiff(
  original: string,
  modified: string,
  originalPath: string = 'a/file',
  modifiedPath: string = 'b/file'
): string {
  const originalLines = original.split('\n');
  const modifiedLines = modified.split('\n');
  
  // 简化的 diff 生成 (生产环境应使用 jsdiff 库)
  let diff = `--- ${originalPath}\n+++ ${modifiedPath}\n`;
  
  let i = 0, j = 0;
  let hunk: string[] = [];
  let originalLineNum = 1;
  let modifiedLineNum = 1;
  
  while (i < originalLines.length || j < modifiedLines.length) {
    if (i < originalLines.length && j < modifiedLines.length && 
        originalLines[i] === modifiedLines[j]) {
      // 相同行
      if (hunk.length > 0) {
        diff += formatHunk(hunk, originalLineNum, modifiedLineNum);
        hunk = [];
      }
      diff += ` ${originalLines[i]}\n`;
      i++;
      j++;
      originalLineNum++;
      modifiedLineNum++;
    } else {
      // 不同行
      if (i < originalLines.length) {
        hunk.push(`-${originalLines[i]}`);
        i++;
        originalLineNum++;
      }
      if (j < modifiedLines.length) {
        hunk.push(`+${modifiedLines[j]}`);
        j++;
        modifiedLineNum++;
      }
    }
  }
  
  if (hunk.length > 0) {
    diff += formatHunk(hunk, originalLineNum - hunk.filter(l => l.startsWith('+')).length, 
                              modifiedLineNum - hunk.filter(l => l.startsWith('-')).length);
  }
  
  return diff;
}

function formatHunk(hunk: string[], origStart: number, modStart: number): string {
  const additions = hunk.filter(l => l.startsWith('+')).length;
  const deletions = hunk.filter(l => l.startsWith('-')).length;
  return `@@ -${origStart},${deletions} +${modStart},${additions} @@\n${hunk.join('\n')}\n`;
}

/**
 * 工具函数: 应用 Patch
 */
export function applyPatch(originalContent: string, patch: string): string {
  // 简化的 patch 应用 (生产环境应使用 jsdiff 库的 applyPatch)
  // 这里仅作示例,实际需要完整的 diff 解析逻辑
  console.warn('⚠️ 简化版 applyPatch,生产环境应使用 jsdiff 库');
  return originalContent; // TODO: 实现完整的 patch 应用逻辑
}
