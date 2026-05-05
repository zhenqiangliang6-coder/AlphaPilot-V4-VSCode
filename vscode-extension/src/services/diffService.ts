// src/services/diffService.ts
// ============================================================
// Diff/Patch 服务 - 对标 Cursor 的代码修改能力
// 严格遵循架构信条: Worker = 真相, Extension = 映射
// ============================================================

import * as vscode from 'vscode';
import { FileDiff, MultiFilePatch, PatchApplicationResult, UserConfirmation } from '../types/diff';
import { createExtensionMessage } from '../types/protocol';

class DiffService {
  private pendingPatches: Map<string, MultiFilePatch> = new Map();
  private appliedPatches: Map<string, PatchApplicationResult[]> = new Map();

  /**
   * 注册 Diff 预览 (从 Backend 接收)
   */
  registerDiffPreview(patch: MultiFilePatch): void {
    this.pendingPatches.set(patch.task_id, patch);
    console.log(`📋 收到 Diff 预览: ${patch.file_diffs.length} 个文件变更`);
    
    // 显示 Diff 面板
    this.showDiffPanel(patch);
  }

  /**
   * 显示 Diff 对比面板
   */
  async showDiffPanel(patch: MultiFilePatch): Promise<void> {
    for (const fileDiff of patch.file_diffs) {
      try {
        // 创建临时文件用于对比
        const originalUri = await this.createTempFile(
          fileDiff.original_content,
          `${fileDiff.file_path}.original`
        );
        
        const modifiedUri = await this.createTempFile(
          fileDiff.modified_content,
          `${fileDiff.file_path}.modified`
        );
        
        // 打开 VSCode 原生 Diff 视图
        await vscode.commands.executeCommand(
          'vscode.diff',
          originalUri,
          modifiedUri,
          `AlphaPilot: ${fileDiff.file_path} (AI 建议)`
        );
        
        console.log(`✅ 已打开 Diff 视图: ${fileDiff.file_path}`);
      } catch (error) {
        console.error(`❌ 打开 Diff 视图失败: ${fileDiff.file_path}`, error);
      }
    }
    
    // 询问用户是否应用
    this.promptUserAction(patch);
  }

  /**
   * 提示用户操作
   */
  async promptUserAction(patch: MultiFilePatch): Promise<void> {
    const action = await vscode.window.showInformationMessage(
      `AI 建议修改 ${patch.file_diffs.length} 个文件,是否应用?`,
      { modal: true },
      '✅ 全部应用',
      '❌ 全部拒绝',
      '📝 逐个确认'
    );
    
    if (action === '✅ 全部应用') {
      await this.applyAllPatches(patch);
    } else if (action === '❌ 全部拒绝') {
      await this.rejectAllPatches(patch);
    } else if (action === '📝 逐个确认') {
      await this.confirmEachPatch(patch);
    }
  }

  /**
   * 应用所有补丁
   */
  async applyAllPatches(patch: MultiFilePatch): Promise<void> {
    const results: PatchApplicationResult[] = [];
    
    for (const fileDiff of patch.file_diffs) {
      const result = await this.applySinglePatch(patch.task_id, fileDiff);
      results.push(result);
    }
    
    this.appliedPatches.set(patch.task_id, results);
    this.pendingPatches.delete(patch.task_id);
    
    const successCount = results.filter(r => r.status === 'applied').length;
    vscode.window.showInformationMessage(
      `✅ 已应用 ${successCount}/${results.length} 个文件修改`
    );
  }

  /**
   * 应用单个补丁
   */
  async applySinglePatch(
    taskId: string,
    fileDiff: FileDiff
  ): Promise<PatchApplicationResult> {
    try {
      const filePath = fileDiff.file_path;
      
      // 1. 备份原文件
      const backupPath = await this.backupFile(filePath);
      
      // 2. 写入新内容
      const uri = vscode.Uri.file(filePath);
      await vscode.workspace.fs.writeFile(uri, Buffer.from(fileDiff.modified_content, 'utf-8'));
      
      // 3. 记录结果
      const result: PatchApplicationResult = {
        task_id: taskId,
        file_path: filePath,
        status: 'applied',
        backup_path: backupPath,
        applied_at: Date.now()
      };
      
      console.log(`✅ 已应用补丁: ${filePath}`);
      return result;
    } catch (error: any) {
      console.error(`❌ 应用补丁失败: ${fileDiff.file_path}`, error);
      
      return {
        task_id: taskId,
        file_path: fileDiff.file_path,
        status: 'rejected',
        error: error.message
      };
    }
  }

  /**
   * 拒绝所有补丁
   */
  async rejectAllPatches(patch: MultiFilePatch): Promise<void> {
    const results: PatchApplicationResult[] = patch.file_diffs.map(fileDiff => ({
      task_id: patch.task_id,
      file_path: fileDiff.file_path,
      status: 'rejected'
    }));
    
    this.appliedPatches.set(patch.task_id, results);
    this.pendingPatches.delete(patch.task_id);
    
    vscode.window.showInformationMessage('❌ 已拒绝所有修改');
  }

  /**
   * 逐个确认补丁
   */
  async confirmEachPatch(patch: MultiFilePatch): Promise<void> {
    const results: PatchApplicationResult[] = [];
    
    for (const fileDiff of patch.file_diffs) {
      const action = await vscode.window.showInformationMessage(
        `是否应用此修改?\n\n${fileDiff.file_path}\n+${fileDiff.stats.additions} -${fileDiff.stats.deletions}`,
        { modal: true },
        '✅ 应用',
        '❌ 跳过',
        '🛑 停止并拒绝剩余'
      );
      
      if (action === '✅ 应用') {
        const result = await this.applySinglePatch(patch.task_id, fileDiff);
        results.push(result);
      } else if (action === '🛑 停止并拒绝剩余') {
        // 拒绝剩余所有
        const remainingIndex = patch.file_diffs.indexOf(fileDiff);
        const remaining = patch.file_diffs.slice(remainingIndex + 1);
        remaining.forEach(fd => {
          results.push({
            task_id: patch.task_id,
            file_path: fd.file_path,
            status: 'rejected'
          });
        });
        break;
      } else {
        // 跳过
        results.push({
          task_id: patch.task_id,
          file_path: fileDiff.file_path,
          status: 'rejected'
        });
      }
    }
    
    this.appliedPatches.set(patch.task_id, results);
    this.pendingPatches.delete(patch.task_id);
  }

  /**
   * 备份文件
   */
  private async backupFile(filePath: string): Promise<string> {
    const originalUri = vscode.Uri.file(filePath);
    const backupPath = `${filePath}.backup.${Date.now()}`;
    const backupUri = vscode.Uri.file(backupPath);
    
    try {
      const content = await vscode.workspace.fs.readFile(originalUri);
      await vscode.workspace.fs.writeFile(backupUri, content);
      console.log(`💾 已备份: ${backupPath}`);
      return backupPath;
    } catch (error) {
      console.warn(`⚠️ 备份失败: ${filePath}`, error);
      return '';
    }
  }

  /**
   * 创建临时文件
   */
  private async createTempFile(content: string, fileName: string): Promise<vscode.Uri> {
    // 使用系统临时目录而不是 appRoot
    const tempDir = vscode.Uri.file(require('os').tmpdir());
    const tempUri = vscode.Uri.joinPath(tempDir, `alphapilot-${fileName}`);
    
    await vscode.workspace.fs.writeFile(tempUri, Buffer.from(content, 'utf-8'));
    return tempUri;
  }

  /**
   * 获取待处理的 Patch
   */
  getPendingPatch(taskId: string): MultiFilePatch | undefined {
    return this.pendingPatches.get(taskId);
  }

  /**
   * 获取已应用的 Patch 历史
   */
  getAppliedPatches(taskId: string): PatchApplicationResult[] | undefined {
    return this.appliedPatches.get(taskId);
  }

  /**
   * 撤销补丁 (恢复备份)
   */
  async revertPatch(taskId: string, filePath: string): Promise<boolean> {
    const results = this.appliedPatches.get(taskId);
    if (!results) return false;
    
    const result = results.find(r => r.file_path === filePath && r.backup_path);
    if (!result || !result.backup_path) return false;
    
    try {
      const backupUri = vscode.Uri.file(result.backup_path);
      const targetUri = vscode.Uri.file(filePath);
      
      const content = await vscode.workspace.fs.readFile(backupUri);
      await vscode.workspace.fs.writeFile(targetUri, content);
      
      // 删除备份文件
      await vscode.workspace.fs.delete(backupUri);
      
      result.status = 'rejected';
      console.log(`↩️ 已撤销补丁: ${filePath}`);
      return true;
    } catch (error) {
      console.error(`❌ 撤销补丁失败: ${filePath}`, error);
      return false;
    }
  }

  /**
   * 清理临时文件
   */
  async cleanupTempFiles(): Promise<void> {
    // TODO: 实现临时文件清理逻辑
    console.log('🧹 清理临时文件...');
  }
}

// 单例模式
export const diffService = new DiffService();
