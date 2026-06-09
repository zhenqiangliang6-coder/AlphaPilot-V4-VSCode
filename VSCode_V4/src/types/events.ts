// src/types/events.ts
// WebSocket 事件类型定义

export interface WebSocketMessage {
  event: string;
  data?: any;
  task_id?: string;
  step_id?: string;
}

// 流式输出事件
export interface StreamStartEvent {
  event: 'stream_start';
  task_id: string;
  title?: string;
}

export interface StreamChunkEvent {
  event: 'stream_chunk';
  task_id: string;
  chunk: string;
}

export interface StreamEndEvent {
  event: 'stream_end';
  task_id: string;
}

export interface StreamErrorEvent {
  event: 'stream_error';
  task_id: string;
  message: string;
}

// 任务生命周期事件
export interface TaskStartedEvent {
  event: 'task_started';
  task_id: string;
}

export interface TaskCompletedEvent {
  event: 'task_completed';
  task_id: string;
  result: any;
}

export interface TaskFailedEvent {
  event: 'task_failed';
  task_id: string;
  error: string;
}

export interface TaskCancelledEvent {
  event: 'task_cancelled';
  task_id: string;
  reason?: string;
}

// 步骤事件
export interface StepStartedEvent {
  event: 'step_started';
  task_id: string;
  step_id: string;
  step_type: string;
}

export interface StepFinishedEvent {
  event: 'step_finished';
  task_id: string;
  step_id: string;
  step_type: string;
  output: any;
}

export interface StepFailedEvent {
  event: 'step_failed';
  task_id: string;
  step_id: string;
  error: string;
}

// 联合类型
export type AnyEvent = 
  | StreamStartEvent
  | StreamChunkEvent
  | StreamEndEvent
  | StreamErrorEvent
  | TaskStartedEvent
  | TaskCompletedEvent
  | TaskFailedEvent
  | TaskCancelledEvent
  | StepStartedEvent
  | StepFinishedEvent
  | StepFailedEvent;
