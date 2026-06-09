// src/types/protocol.ts
// ============================================================
// AlphaPilot 前后端通信协议定义 (Protocol Layer)
// 严格遵循 TaskModel v2,对标 Cursor/Claude Code
// ============================================================

/**
 * 消息方向
 */
export type MessageDirection = 'extension_to_backend' | 'backend_to_extension';

/**
 * 基础消息结构
 */
export interface BaseMessage {
  type: string;
  direction: MessageDirection;
  timestamp: number;
  id?: string; // 请求ID,用于关联请求-响应
}

/**
 * Extension → Backend 消息类型
 */
export type ExtensionMessage = 
  | SubmitTaskMessage
  | CancelTaskMessage
  | PauseStreamMessage
  | ResumeStreamMessage
  | GetTaskStatusMessage
  | ApplyPatchMessage;

/**
 * Backend → Extension 消息类型
 */
export type BackendMessage = 
  | TaskStartedMessage
  | TaskCompletedMessage
  | TaskFailedMessage
  | TaskCancelledMessage
  | StepStartedMessage
  | StepFinishedMessage
  | StreamStartMessage
  | StreamChunkMessage
  | StreamEndMessage
  | StreamErrorMessage
  | DiffPreviewMessage;

// ============================================================
// Extension → Backend 消息定义
// ============================================================

/**
 * 提交任务
 */
export interface SubmitTaskMessage extends BaseMessage {
  type: 'submit_task';
  direction: 'extension_to_backend';
  payload: {
    prompt: string;
    task_type: string; // 'qwen_generate' | 'deepseek_generate' | 'doubao_generate'
    context?: {
      file_path?: string;
      selected_code?: string;
      language?: string;
    };
  };
}

/**
 * 取消任务
 */
export interface CancelTaskMessage extends BaseMessage {
  type: 'cancel_task';
  direction: 'extension_to_backend';
  payload: {
    task_id: string;
  };
}

/**
 * 暂停流式输出
 */
export interface PauseStreamMessage extends BaseMessage {
  type: 'pause_stream';
  direction: 'extension_to_backend';
  payload: {
    task_id: string;
  };
}

/**
 * 恢复流式输出
 */
export interface ResumeStreamMessage extends BaseMessage {
  type: 'resume_stream';
  direction: 'extension_to_backend';
  payload: {
    task_id: string;
  };
}

/**
 * 获取任务状态
 */
export interface GetTaskStatusMessage extends BaseMessage {
  type: 'get_task_status';
  direction: 'extension_to_backend';
  payload: {
    task_id: string;
  };
}

/**
 * 应用补丁 (用户确认后)
 */
export interface ApplyPatchMessage extends BaseMessage {
  type: 'apply_patch';
  direction: 'extension_to_backend';
  payload: {
    task_id: string;
    file_path: string;
    patch: string;
    confirmed: boolean;
  };
}

// ============================================================
// Backend → Extension 消息定义
// ============================================================

/**
 * 任务已开始
 */
export interface TaskStartedMessage extends BaseMessage {
  type: 'task_started';
  direction: 'backend_to_extension';
  payload: {
    task_id: string;
    task_type: string;
    started_at: number;
  };
}

/**
 * 任务已完成
 */
export interface TaskCompletedMessage extends BaseMessage {
  type: 'task_completed';
  direction: 'backend_to_extension';
  payload: {
    task_id: string;
    result: any;
    completed_at: number;
    duration_ms: number;
  };
}

/**
 * 任务失败
 */
export interface TaskFailedMessage extends BaseMessage {
  type: 'task_failed';
  direction: 'backend_to_extension';
  payload: {
    task_id: string;
    error: {
      message: string;
      code: string;
      stack?: string;
    };
    failed_at: number;
  };
}

/**
 * 任务已取消
 */
export interface TaskCancelledMessage extends BaseMessage {
  type: 'task_cancelled';
  direction: 'backend_to_extension';
  payload: {
    task_id: string;
    reason: string;
    cancelled_at: number;
  };
}

/**
 * 步骤已开始
 */
export interface StepStartedMessage extends BaseMessage {
  type: 'step_started';
  direction: 'backend_to_extension';
  payload: {
    task_id: string;
    step_id: string;
    step_type: 'analyze' | 'plan' | 'write' | 'refine' | 'test' | 'fix' | 'profile' | 'doc';
    started_at: number;
  };
}

/**
 * 步骤已完成
 */
export interface StepFinishedMessage extends BaseMessage {
  type: 'step_finished';
  direction: 'backend_to_extension';
  payload: {
    task_id: string;
    step_id: string;
    step_type: string;
    output: any;
    finished_at: number;
    duration_ms: number;
  };
}

/**
 * 流式输出开始
 */
export interface StreamStartMessage extends BaseMessage {
  type: 'stream_start';
  direction: 'backend_to_extension';
  payload: {
    task_id: string;
    step_id?: string;
    started_at: number;
  };
}

/**
 * 流式数据块
 */
export interface StreamChunkMessage extends BaseMessage {
  type: 'stream_chunk';
  direction: 'backend_to_extension';
  payload: {
    task_id: string;
    chunk: string;
    token_index: number;
  };
}

/**
 * 流式输出结束
 */
export interface StreamEndMessage extends BaseMessage {
  type: 'stream_end';
  direction: 'backend_to_extension';
  payload: {
    task_id: string;
    total_tokens: number;
    ended_at: number;
  };
}

/**
 * 流式输出错误
 */
export interface StreamErrorMessage extends BaseMessage {
  type: 'stream_error';
  direction: 'backend_to_extension';
  payload: {
    task_id: string;
    error: string;
  };
}

/**
 * Diff 预览 (AI 生成的代码修改建议)
 */
export interface DiffPreviewMessage extends BaseMessage {
  type: 'diff_preview';
  direction: 'backend_to_extension';
  payload: {
    task_id: string;
    file_path: string;
    original_content: string;
    modified_content: string;
    diff: string; // unified diff 格式
    changes_count: number;
  };
}

// ============================================================
// 工具函数
// ============================================================

/**
 * 创建 Extension → Backend 消息
 */
export function createExtensionMessage<T extends ExtensionMessage>(
  type: T['type'],
  payload: T['payload']
): T {
  return {
    type,
    direction: 'extension_to_backend',
    timestamp: Date.now(),
    id: generateMessageId(),
    payload
  } as T;
}

/**
 * 创建 Backend → Extension 消息
 */
export function createBackendMessage<T extends BackendMessage>(
  type: T['type'],
  payload: T['payload']
): T {
  return {
    type,
    direction: 'backend_to_extension',
    timestamp: Date.now(),
    id: generateMessageId(),
    payload
  } as T;
}

/**
 * 生成唯一消息ID
 */
function generateMessageId(): string {
  return `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
}

/**
 * 验证消息格式
 */
export function validateMessage(message: any): boolean {
  return (
    message &&
    typeof message.type === 'string' &&
    typeof message.direction === 'string' &&
    typeof message.timestamp === 'number' &&
    ['extension_to_backend', 'backend_to_extension'].includes(message.direction)
  );
}
