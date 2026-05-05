// src/core/eventBus.ts
// ============================================================
// 全局事件总线 - 解耦组件间通信
// 对标 Redux/Zustand 的状态管理模式
// ============================================================

import { EventEmitter } from 'vscode';

/**
 * 事件类型定义
 */
export enum EventType {
  // 任务相关
  TASK_SUBMITTED = 'task:submitted',
  TASK_STARTED = 'task:started',
  TASK_COMPLETED = 'task:completed',
  TASK_FAILED = 'task:failed',
  TASK_CANCELLED = 'task:cancelled',
  
  // 步骤相关
  STEP_STARTED = 'step:started',
  STEP_FINISHED = 'step:finished',
  
  // 流式输出
  STREAM_START = 'stream:start',
  STREAM_CHUNK = 'stream:chunk',
  STREAM_END = 'stream:end',
  STREAM_ERROR = 'stream:error',
  
  // Diff/Patch
  DIFF_PREVIEW = 'diff:preview',
  PATCH_APPLIED = 'patch:applied',
  PATCH_REJECTED = 'patch:rejected',
  
  // UI 相关
  PANEL_OPENED = 'ui:panel_opened',
  MODEL_CHANGED = 'ui:model_changed',
  
  // 错误
  ERROR_OCCURRED = 'error:occurred'
}

/**
 * 事件负载类型映射
 */
export interface EventPayloadMap {
  [EventType.TASK_SUBMITTED]: { taskId: string; prompt: string };
  [EventType.TASK_STARTED]: { taskId: string; taskType: string };
  [EventType.TASK_COMPLETED]: { taskId: string; result: any };
  [EventType.TASK_FAILED]: { taskId: string; error: any };
  [EventType.TASK_CANCELLED]: { taskId: string; reason: string };
  
  [EventType.STEP_STARTED]: { taskId: string; stepId: string; stepType: string };
  [EventType.STEP_FINISHED]: { taskId: string; stepId: string; output: any };
  
  [EventType.STREAM_START]: { taskId: string };
  [EventType.STREAM_CHUNK]: { taskId: string; chunk: string };
  [EventType.STREAM_END]: { taskId: string };
  [EventType.STREAM_ERROR]: { taskId: string; error: string };
  
  [EventType.DIFF_PREVIEW]: { taskId: string; fileCount: number };
  [EventType.PATCH_APPLIED]: { taskId: string; filePath: string };
  [EventType.PATCH_REJECTED]: { taskId: string; filePath: string };
  
  [EventType.PANEL_OPENED]: void;
  [EventType.MODEL_CHANGED]: { model: string };
  
  [EventType.ERROR_OCCURRED]: { message: string; stack?: string };
}

/**
 * 事件监听器类型
 */
export type EventListener<T extends EventType> = (payload: EventPayloadMap[T]) => void;

/**
 * 全局事件总线类
 */
class EventBus {
  private emitters: Map<EventType, EventEmitter<any>> = new Map();
  private listeners: Map<EventType, Set<Function>> = new Map();

  constructor() {
    // 初始化所有事件类型的 EventEmitter
    Object.values(EventType).forEach(eventType => {
      this.emitters.set(eventType, new EventEmitter());
      this.listeners.set(eventType, new Set());
    });
  }

  /**
   * 订阅事件
   * @param eventType 事件类型
   * @param listener 监听器函数
   * @returns 取消订阅函数
   */
  on<T extends EventType>(eventType: T, listener: EventListener<T>): () => void {
    const listenerSet = this.listeners.get(eventType);
    if (listenerSet) {
      listenerSet.add(listener);
      
      // 注册到 EventEmitter
      const emitter = this.emitters.get(eventType);
      if (emitter) {
        emitter.event(listener as any);
      }
    }
    
    // 返回取消订阅函数
    return () => {
      this.off(eventType, listener);
    };
  }

  /**
   * 取消订阅
   */
  off<T extends EventType>(eventType: T, listener: EventListener<T>): void {
    const listenerSet = this.listeners.get(eventType);
    if (listenerSet) {
      listenerSet.delete(listener);
    }
  }

  /**
   * 触发事件
   */
  emit<T extends EventType>(eventType: T, payload: EventPayloadMap[T]): void {
    console.log(`📡 Event: ${eventType}`, payload);
    
    const emitter = this.emitters.get(eventType);
    if (emitter) {
      emitter.fire(payload);
    }
    
    // 通知所有监听器
    const listenerSet = this.listeners.get(eventType);
    if (listenerSet) {
      listenerSet.forEach(listener => {
        try {
          (listener as EventListener<T>)(payload);
        } catch (error) {
          console.error(`❌ 事件监听器执行失败 [${eventType}]:`, error);
        }
      });
    }
  }

  /**
   * 一次性监听 (触发后自动取消)
   */
  once<T extends EventType>(eventType: T, listener: EventListener<T>): () => void {
    const unsubscribe = this.on(eventType, (payload) => {
      listener(payload);
      unsubscribe();
    });
    return unsubscribe;
  }

  /**
   * 清除所有监听器
   */
  clearAll(): void {
    this.listeners.forEach(set => set.clear());
    this.emitters.forEach(emitter => emitter.dispose());
  }

  /**
   * 获取某个事件的监听器数量
   */
  getListenerCount(eventType: EventType): number {
    const listenerSet = this.listeners.get(eventType);
    return listenerSet ? listenerSet.size : 0;
  }

  /**
   * 销毁事件总线
   */
  dispose(): void {
    this.clearAll();
    this.emitters.clear();
    this.listeners.clear();
  }
}

// 单例模式
export const eventBus = new EventBus();

/**
 * 便捷函数: 创建带上下文的事件监听器
 */
export function createEventListener<T extends EventType>(
  eventType: T,
  handler: (payload: EventPayloadMap[T]) => void,
  context?: any
): () => void {
  const boundHandler = context ? handler.bind(context) : handler;
  return eventBus.on(eventType, boundHandler);
}
