// src/taskHistory.ts
// ----------------------------
// 中文注释：任务历史管理器（TaskHistoryManager）
// ----------------------------
// 职责：
// - 在本地（VSCode globalState）保存用户提交的任务摘要和结果
// - 提供读取、删除、清空和获取摘要接口，供面板展示使用
// - 此文件只负责本地存储，不与后端通信
//
// 说明（对菜鸟前端）：
// - globalState 是 VSCode 提供的一个永久化存储（针对当前扩展和用户）
// - 添加任务时会去重（相同 taskId 会更新）并只保留最新 N 条
// - 注释不会影响运行，安全可改进可扩展
//
import * as vscode from 'vscode';
import { TaskResult } from './taskModel';

export interface HistoryTask {
    taskId: string;
    type: string;
    prompt?: string;
    payload?: any;
    result?: TaskResult;
    timestamp: number;
    duration?: number;
    status: 'pending' | 'done' | 'error';
}

export class TaskHistoryManager {
    private static readonly HISTORY_KEY = 'alphaPilot.taskHistory';
    private static readonly MAX_HISTORY = 50;
    private context: vscode.ExtensionContext;

    constructor(context: vscode.ExtensionContext) {
        this.context = context;
    }

    /**
     * 添加任务到历史记录
     */
    public addTask(task: HistoryTask): void {
        try {
            const history = this.getHistory();
            
            // 检查是否已存在该任务 ID
            const existingIndex = history.findIndex(h => h.taskId === task.taskId);
            if (existingIndex >= 0) {
                history[existingIndex] = task;
            } else {
                history.unshift(task);
            }
            
            // 只保留最新的 MAX_HISTORY 条
            if (history.length > TaskHistoryManager.MAX_HISTORY) {
                history.splice(TaskHistoryManager.MAX_HISTORY);
            }

            this.context.globalState.update(TaskHistoryManager.HISTORY_KEY, history);
        } catch (err) {
            console.error('Failed to add task to history:', err);
        }
    }

    /**
     * 获取完整的历史记录
     */
    public getHistory(): HistoryTask[] {
        try {
            const data = this.context.globalState.get<HistoryTask[]>(TaskHistoryManager.HISTORY_KEY);
            return data ?? [];
        } catch (err) {
            console.error('Failed to get history:', err);
            return [];
        }
    }

    /**
     * 获取单个任务
     */
    public getTask(taskId: string): HistoryTask | undefined {
        const history = this.getHistory();
        return history.find(h => h.taskId === taskId);
    }

    /**
     * 清除所有历史
     */
    public clearHistory(): void {
        try {
            this.context.globalState.update(TaskHistoryManager.HISTORY_KEY, []);
        } catch (err) {
            console.error('Failed to clear history:', err);
        }
    }

    /**
     * 删除单个历史项
     */
    public deleteTask(taskId: string): void {
        try {
            const history = this.getHistory();
            const filtered = history.filter(h => h.taskId !== taskId);
            this.context.globalState.update(TaskHistoryManager.HISTORY_KEY, filtered);
        } catch (err) {
            console.error('Failed to delete task from history:', err);
        }
    }

    /**
     * 获取摘要列表（用于 UI 展示）
     */
    public getHistorySummary(): Array<{
        taskId: string;
        type: string;
        title: string;
        timestamp: number;
        status: string;
        timeAgo: string;
    }> {
        const history = this.getHistory();
        const now = Date.now();

        return history.map(task => ({
            taskId: task.taskId,
            type: task.type,
            title: this.generateTitle(task),
            timestamp: task.timestamp,
            status: task.status,
            timeAgo: this.formatTimeAgo(now - task.timestamp)
        }));
    }

    /**
     * 为任务生成短标题
     */
    private generateTitle(task: HistoryTask): string {
        if (task.type === 'qwen_generate' && task.prompt) {
            return task.prompt.substring(0, 50) + (task.prompt.length > 50 ? '...' : '');
        } else if (task.type === 'add_numbers' && task.payload) {
            return `计算 ${task.payload.a} + ${task.payload.b}`;
        }
        return `${task.type} (${task.taskId.substring(0, 8)})`;
    }

    /**
     * 格式化相对时间
     */
    private formatTimeAgo(ms: number): string {
        const seconds = Math.floor(ms / 1000);
        const minutes = Math.floor(seconds / 60);
        const hours = Math.floor(minutes / 60);
        const days = Math.floor(hours / 24);

        if (days > 0) return `${days} 天前`;
        if (hours > 0) return `${hours} 小时前`;
        if (minutes > 0) return `${minutes} 分钟前`;
        if (seconds > 0) return `${seconds} 秒前`;
        return '刚才';
    }
}
