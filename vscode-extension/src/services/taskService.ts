// src/services/taskService.ts
// 任务管理服务

import * as vscode from 'vscode';
import { Task, TaskStatus } from '../types/task';

const NODE_API_BASE_URL = 'http://localhost:3000';

class TaskService {
  private tasks: Map<string, Task> = new Map();
  private context: vscode.ExtensionContext | null = null;

  /**
   * 初始化服务
   */
  initialize(context: vscode.ExtensionContext): void {
    this.context = context;
    this.loadTasksFromStorage();
  }

  /**
   * 提交新任务
   */
  async submitTask(prompt: string, type: string = 'qwen_generate'): Promise<string> {
    try {
      const body = {
        type,
        payload: { prompt },
        source: 'vscode-extension'
      };

      const response = await fetch(`${NODE_API_BASE_URL}/task/submit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });

      if (!response.ok) {
        const text = await response.text();
        throw new Error(`HTTP ${response.status}: ${text}`);
      }

      const data = await response.json();
      const taskId = data.task_id;

      // 创建任务记录
      const task: Task = {
        id: taskId,
        type,
        prompt,
        status: 'pending',
        steps: [],
        events: [],
        metadata: { source: 'vscode-extension' },
        createdAt: Date.now(),
        updatedAt: Date.now()
      };

      this.tasks.set(taskId, task);
      this.saveTasksToStorage();

      console.log(`✅ 任务已提交：${taskId}`);
      return taskId;

    } catch (error: any) {
      console.error('❌ 提交任务失败:', error);
      vscode.window.showErrorMessage(`提交任务失败：${error.message}`);
      throw error;
    }
  }

  /**
   * 取消任务
   */
  async cancelTask(taskId: string): Promise<void> {
    try {
      const response = await fetch(`${NODE_API_BASE_URL}/task/stop/${taskId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });

      if (!response.ok) {
        const text = await response.text();
        throw new Error(`HTTP ${response.status}: ${text}`);
      }

      // 更新本地状态
      const task = this.tasks.get(taskId);
      if (task) {
        task.status = 'cancelled';
        task.updatedAt = Date.now();
        task.completedAt = Date.now();
        this.saveTasksToStorage();
      }

      console.log(`✅ 任务已取消：${taskId}`);

    } catch (error: any) {
      console.error('❌ 取消任务失败:', error);
      vscode.window.showErrorMessage(`取消任务失败：${error.message}`);
      throw error;
    }
  }

  /**
   * 获取任务详情
   */
  getTask(taskId: string): Task | undefined {
    return this.tasks.get(taskId);
  }

  /**
   * 获取所有任务
   */
  getAllTasks(): Task[] {
    return Array.from(this.tasks.values());
  }

  /**
   * 更新任务状态
   */
  updateTaskStatus(taskId: string, status: TaskStatus): void {
    const task = this.tasks.get(taskId);
    if (task) {
      task.status = status;
      task.updatedAt = Date.now();
      
      if (status === 'running' && !task.startedAt) {
        task.startedAt = Date.now();
      } else if (['completed', 'failed', 'cancelled'].includes(status)) {
        task.completedAt = Date.now();
      }
      
      this.saveTasksToStorage();
    }
  }

  /**
   * 添加步骤到任务
   */
  addStep(taskId: string, step: any): void {
    const task = this.tasks.get(taskId);
    if (task) {
      task.steps.push(step);
      task.updatedAt = Date.now();
      this.saveTasksToStorage();
    }
  }

  /**
   * 更新步骤状态
   */
  updateStep(taskId: string, stepId: string, updates: Partial<any>): void {
    const task = this.tasks.get(taskId);
    if (task) {
      const step = task.steps.find(s => s.id === stepId);
      if (step) {
        Object.assign(step, updates);
        task.updatedAt = Date.now();
        this.saveTasksToStorage();
      }
    }
  }

  /**
   * 添加事件到任务
   */
  addEvent(taskId: string, event: any): void {
    const task = this.tasks.get(taskId);
    if (task) {
      task.events.push(event);
      task.updatedAt = Date.now();
      this.saveTasksToStorage();
    }
  }

  /**
   * 设置任务结果
   */
  setTaskResult(taskId: string, result: any): void {
    const task = this.tasks.get(taskId);
    if (task) {
      task.result = result;
      task.status = 'completed';
      task.completedAt = Date.now();
      task.updatedAt = Date.now();
      this.saveTasksToStorage();
    }
  }

  /**
   * 删除任务
   */
  deleteTask(taskId: string): void {
    this.tasks.delete(taskId);
    this.saveTasksToStorage();
    console.log(`🗑️ 任务已删除：${taskId}`);
  }

  /**
   * 清空所有任务
   */
  clearHistory(): void {
    this.tasks.clear();
    this.saveTasksToStorage();
    console.log('🧹 历史已清空');
  }

  /**
   * 保存任务到存储
   */
  private async saveTasksToStorage(): Promise<void> {
    if (!this.context) return;

    try {
      const tasksArray = Array.from(this.tasks.values());
      await this.context.globalState.update('alphapilot_tasks', tasksArray);
    } catch (error) {
      console.error('❌ 保存任务失败:', error);
    }
  }

  /**
   * 从存储加载任务
   */
  private loadTasksFromStorage(): void {
    if (!this.context) return;

    try {
      const stored = this.context.globalState.get<Task[]>('alphapilot_tasks') || [];
      
      // 只保留最近 50 个任务
      const recentTasks = stored.slice(-50);
      
      recentTasks.forEach(task => {
        this.tasks.set(task.id, task);
      });

      console.log(`📂 已加载 ${recentTasks.length} 个任务`);
    } catch (error) {
      console.error('❌ 加载任务失败:', error);
    }
  }

  /**
   * 获取任务统计信息
   */
  getStats(): { total: number; completed: number; failed: number; running: number } {
    const tasks = Array.from(this.tasks.values());
    return {
      total: tasks.length,
      completed: tasks.filter(t => t.status === 'completed').length,
      failed: tasks.filter(t => t.status === 'failed').length,
      running: tasks.filter(t => t.status === 'running').length
    };
  }
}

// 单例模式
export const taskService = new TaskService();
