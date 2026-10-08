import * as fs from 'fs';
import * as path from 'path';
import * as vscode from 'vscode';

export interface WorkspaceDeleteOp {
  op: 'delete';
  path: string;
}

const SENSITIVE_SEGMENTS = new Set([
  '.git',
  'node_modules',
  'venv',
  '.venv',
  '__pycache__',
  'dist',
  'build',
]);

function isSensitivePath(relativePath: string): boolean {
  return relativePath.split(/[\\/]+/).some((segment) => {
    const normalized = segment.toLowerCase();
    return SENSITIVE_SEGMENTS.has(normalized)
      || normalized === '.env'
      || normalized.startsWith('.env.');
  });
}

function getSafeTarget(rootPath: string, relativePath: string): string {
  const normalized = relativePath.replace(/\\/g, '/');
  if (
    !normalized
    || path.posix.isAbsolute(normalized)
    || /^[a-z]:/i.test(normalized)
    || normalized.split('/').some((segment) => segment === '..' || segment === '')
  ) {
    throw new Error(`拒绝不安全或非工作区相对路径: ${relativePath}`);
  }

  const resolvedRoot = path.resolve(rootPath);
  const target = path.resolve(resolvedRoot, ...normalized.split('/'));
  const relative = path.relative(resolvedRoot, target);
  if (!relative || relative === '..' || relative.startsWith(`..${path.sep}`) || path.isAbsolute(relative)) {
    throw new Error(`拒绝超出工作区的路径: ${relativePath}`);
  }

  const realRoot = fs.realpathSync(resolvedRoot);
  let existingParent = target;
  while (!fs.existsSync(existingParent)) {
    const parent = path.dirname(existingParent);
    if (parent === existingParent) {
      throw new Error(`无法验证删除目标: ${relativePath}`);
    }
    existingParent = parent;
  }
  const realParent = fs.realpathSync(existingParent);
  const realRelative = path.relative(realRoot, realParent);
  if (realRelative === '..' || realRelative.startsWith(`..${path.sep}`) || path.isAbsolute(realRelative)) {
    throw new Error(`拒绝通过符号链接逃逸工作区的路径: ${relativePath}`);
  }
  if (fs.existsSync(target) && fs.lstatSync(target).isSymbolicLink()) {
    throw new Error(`拒绝删除符号链接: ${relativePath}`);
  }

  return target;
}

export async function applyWorkspaceDeleteOps(
  operations: WorkspaceDeleteOp[],
  workspaceRoot: vscode.Uri,
): Promise<{ deleted: string[]; rejected: string[]; cancelled: boolean }> {
  if (operations.length === 0) {
    return { deleted: [], rejected: [], cancelled: false };
  }

  const rejected: string[] = [];
  const targets: Array<{ path: string; fullPath: string; uri: vscode.Uri; isDirectory: boolean }> = [];

  for (const operation of operations) {
    try {
      if (isSensitivePath(operation.path)) {
        throw new Error(`拒绝删除敏感路径: ${operation.path}`);
      }
      const fullPath = getSafeTarget(workspaceRoot.fsPath, operation.path);
      const uri = vscode.Uri.file(fullPath);
      const stat = await vscode.workspace.fs.stat(uri);
      targets.push({
        path: operation.path,
        fullPath,
        uri,
        isDirectory: (stat.type & vscode.FileType.Directory) !== 0,
      });
    } catch (error) {
      rejected.push(`${operation.path}: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  if (rejected.length > 0) {
    return { deleted: [], rejected, cancelled: false };
  }

  for (let leftIndex = 0; leftIndex < targets.length; leftIndex += 1) {
    for (let rightIndex = leftIndex + 1; rightIndex < targets.length; rightIndex += 1) {
      const left = targets[leftIndex];
      const right = targets[rightIndex];
      const leftToRight = path.relative(left.fullPath, right.fullPath);
      const rightToLeft = path.relative(right.fullPath, left.fullPath);
      if (
        leftToRight === ''
        || rightToLeft === ''
        || (left.isDirectory && leftToRight !== '..' && !leftToRight.startsWith(`..${path.sep}`) && !path.isAbsolute(leftToRight))
        || (right.isDirectory && rightToLeft !== '..' && !rightToLeft.startsWith(`..${path.sep}`) && !path.isAbsolute(rightToLeft))
      ) {
        rejected.push(`删除清单包含重复或重叠目标：${left.path}、${right.path}`);
      }
    }
  }
  if (rejected.length > 0) {
    return { deleted: [], rejected, cancelled: false };
  }

  const requiresConfirmation = targets.length > 1 || targets.some((target) => target.isDirectory);
  if (requiresConfirmation) {
    const fullList = targets.map((target) => `• ${target.path}${target.isDirectory ? ' (目录)' : ''}`).join('\n');
    const choice = await vscode.window.showWarningMessage(
      `将把以下项目移入系统回收站：\n\n${fullList}\n\n目录删除会递归移入回收站。`,
      { modal: true },
      '移入回收站',
      '取消',
    );
    if (choice !== '移入回收站') {
      return { deleted: [], rejected: [], cancelled: true };
    }
  }

  const deleted: string[] = [];
  for (const target of targets) {
    await vscode.workspace.fs.delete(target.uri, {
      recursive: target.isDirectory,
      useTrash: true,
    });
    deleted.push(target.path);
  }
  return { deleted, rejected: [], cancelled: false };
}
