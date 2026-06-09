// src/providers/inlineCompletionProvider.ts
// ============================================================
// 智能代码补全提供者 - 对标 GitHub Copilot
// 严格遵循架构信条: Worker = 真相, Extension = 映射
// ============================================================

import * as vscode from 'vscode';
import { taskService } from '../services/taskService';

export class AlphaPilotCompletionProvider implements vscode.InlineCompletionItemProvider {
    private isProcessing: boolean = false;
    private lastPrompt: string = '';
    private debounceTimer: NodeJS.Timeout | null = null;

    /**
     * 提供内联代码补全建议
     * 这是 Copilot 的核心功能
     */
    async provideInlineCompletionItems(
        document: vscode.TextDocument,
        position: vscode.Position,
        context: vscode.InlineCompletionContext,
        token: vscode.CancellationToken
    ): Promise<vscode.InlineCompletionList | vscode.InlineCompletionItem[] | null> {
        
        // 如果正在处理或已取消,返回 null
        if (this.isProcessing || token.isCancellationRequested) {
            return null;
        }

        // 获取当前行的前缀文本
        const linePrefix = document.lineAt(position).text.substr(0, position.character);
        
        // 如果前缀太短,不触发补全(避免频繁请求)
        if (linePrefix.trim().length < 3) {
            return null;
        }

        // 防抖:等待用户停止输入 500ms 后再请求
        return new Promise((resolve) => {
            if (this.debounceTimer) {
                clearTimeout(this.debounceTimer);
            }

            this.debounceTimer = setTimeout(async () => {
                try {
                    this.isProcessing = true;
                    
                    // 构建上下文:获取前后各 10 行代码
                    const contextLines = this.getCodeContext(document, position);
                    
                    // 调用后端生成补全建议
                    const suggestion = await this.generateCompletion(contextLines, linePrefix);
                    
                    if (suggestion && suggestion.trim().length > 0) {
                        resolve([
                            new vscode.InlineCompletionItem(
                                suggestion,
                                new vscode.Range(position, position)
                            )
                        ]);
                    } else {
                        resolve([]);
                    }
                } catch (error) {
                    console.error('❌ 代码补全失败:', error);
                    resolve([]);
                } finally {
                    this.isProcessing = false;
                }
            }, 500); // 500ms 防抖
        });
    }

    /**
     * 获取代码上下文(前后各 10 行)
     */
    private getCodeContext(document: vscode.TextDocument, position: vscode.Position): string {
        const startLine = Math.max(0, position.line - 10);
        const endLine = Math.min(document.lineCount - 1, position.line + 10);
        
        const lines: string[] = [];
        for (let i = startLine; i <= endLine; i++) {
            const lineText = document.lineAt(i).text;
            if (i === position.line) {
                // 标记当前行
                lines.push(`>>> ${lineText} <<<`);
            } else {
                lines.push(lineText);
            }
        }
        
        return lines.join('\n');
    }

    /**
     * 调用后端生成补全建议
     */
    private async generateCompletion(context: string, prefix: string): Promise<string> {
        try {
            // 构建 prompt
            const prompt = `基于以下代码上下文,补全当前行的代码:\n\n${context}\n\n只需要输出补全的代码片段,不要包含解释。`;
            
            // 调用 Qwen Worker 生成补全 (不显示面板)
            const taskId = await taskService.submitTask(prompt, 'qwen_generate');
            
            // 等待任务完成(最多 5 秒)
            const result = await this.waitForTaskResult(taskId, 5000);
            
            if (result && result.status === 'done') {
                // 提取代码部分
                const text = result.result?.text || result.steps?.[result.steps.length - 1]?.output?.text || '';
                return this.extractCodeSnippet(text, prefix);
            }
            
            return '';
        } catch (error) {
            console.error('生成补全建议失败:', error);
            return '';
        }
    }

    /**
     * 等待任务结果
     */
    private async waitForTaskResult(taskId: string, timeout: number): Promise<any> {
        const startTime = Date.now();
        
        while (Date.now() - startTime < timeout) {
            const task = taskService.getTask(taskId);
            if (task && task.status !== 'pending' && task.status !== 'running') {
                return task;
            }
            await new Promise(resolve => setTimeout(resolve, 200));
        }
        
        return null;
    }

    /**
     * 从 LLM 响应中提取代码片段
     */
    private extractCodeSnippet(text: string, prefix: string): string {
        // 移除 markdown 代码块标记
        let code = text.replace(/```[\w]*\n?/g, '').replace(/```/g, '');
        
        // 去除首尾空白
        code = code.trim();
        
        // 如果已经包含前缀,只返回剩余部分
        if (code.startsWith(prefix)) {
            code = code.substring(prefix.length);
        }
        
        // 只返回第一行(内联补全通常只需要一行)
        const firstLine = code.split('\n')[0].trim();
        
        return firstLine;
    }

    /**
     * 释放资源
     */
    dispose() {
        if (this.debounceTimer) {
            clearTimeout(this.debounceTimer);
        }
    }
}
