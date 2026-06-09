// src/core/dispatcher.ts
// ============================================================
// 消息分发器 - 统一处理前后端通信
// 基于 Protocol Layer,实现类型安全的消息路由
// ============================================================

import { 
  ExtensionMessage, 
  BackendMessage,
  SubmitTaskMessage,
  CancelTaskMessage,
  TaskStartedMessage,
  TaskCompletedMessage,
  TaskFailedMessage,
  StepStartedMessage,
  StepFinishedMessage,
  StreamChunkMessage,
  DiffPreviewMessage,
  createExtensionMessage,
  validateMessage
} from '../types/protocol';
import { eventBus, EventType } from './eventBus';
import { diffService } from '../services/diffService';
import { websocketService } from '../services/websocketService';

/**
 * 消息处理器类型
 */
type MessageHandler<T extends BackendMessage> = (message: T) => void | Promise<void>;

/**
 * 消息分发器类
 */
class MessageDispatcher {
  private handlers: Map<string, MessageHandler<any>> = new Map();
  private isInitialized = false;

  constructor() {
    this.registerDefaultHandlers();
  }

  /**
   * 初始化分发器
   */
  initialize(): void {
    if (this.isInitialized) {
      console.warn('⚠️ MessageDispatcher 已初始化');
      return;
    }

    // 监听 WebSocket 消息
    this.setupWebSocketListener();
    
    this.isInitialized = true;
    console.log('✅ MessageDispatcher 已初始化');
  }

  /**
   * 注册消息处理器
   */
  registerHandler<T extends BackendMessage>(
    messageType: T['type'],
    handler: MessageHandler<T>
  ): void {
    this.handlers.set(messageType, handler);
    console.log(`📝 注册消息处理器: ${messageType}`);
  }

  /**
   * 发送 Extension → Backend 消息
   */
  async sendMessage(message: ExtensionMessage): Promise<void> {
    try {
      // 验证消息格式
      if (!validateMessage(message)) {
        throw new Error('无效的消息格式');
      }

      console.log(`📤 发送消息: ${message.type}`, message);

      // 通过 WebSocket 发送
      await websocketService.send(message);

      // 触发事件
      this.emitExtensionEvent(message);
    } catch (error) {
      console.error('❌ 发送消息失败:', error);
      eventBus.emit(EventType.ERROR_OCCURRED, {
        message: `发送消息失败: ${(error as Error).message}`
      });
    }
  }

  /**
   * 接收并处理 Backend → Extension 消息
   */
  async receiveMessage(rawMessage: any): Promise<void> {
    try {
      // 验证消息格式
      if (!validateMessage(rawMessage)) {
        console.warn('⚠️ 收到无效消息:', rawMessage);
        return;
      }

      const message = rawMessage as BackendMessage;
      console.log(`📥 接收消息: ${message.type}`);

      // 查找对应的处理器
      const handler = this.handlers.get(message.type);
      if (handler) {
        await handler(message);
      } else {
        console.warn(`⚠️ 未找到消息处理器: ${message.type}`);
      }

      // 触发事件
      this.emitBackendEvent(message);
    } catch (error) {
      console.error('❌ 处理消息失败:', error);
      eventBus.emit(EventType.ERROR_OCCURRED, {
        message: `处理消息失败: ${(error as Error).message}`
      });
    }
  }

  /**
   * 注册默认消息处理器
   */
  private registerDefaultHandlers(): void {
    // 任务已开始
    this.registerHandler('task_started', (msg: TaskStartedMessage) => {
      eventBus.emit(EventType.TASK_STARTED, {
        taskId: msg.payload.task_id,
        taskType: msg.payload.task_type
      });
    });

    // 任务已完成
    this.registerHandler('task_completed', (msg: TaskCompletedMessage) => {
      eventBus.emit(EventType.TASK_COMPLETED, {
        taskId: msg.payload.task_id,
        result: msg.payload.result
      });
    });

    // 任务失败
    this.registerHandler('task_failed', (msg: TaskFailedMessage) => {
      eventBus.emit(EventType.TASK_FAILED, {
        taskId: msg.payload.task_id,
        error: msg.payload.error
      });
    });

    // 步骤已开始
    this.registerHandler('step_started', (msg: StepStartedMessage) => {
      eventBus.emit(EventType.STEP_STARTED, {
        taskId: msg.payload.task_id,
        stepId: msg.payload.step_id,
        stepType: msg.payload.step_type
      });
    });

    // 步骤已完成
    this.registerHandler('step_finished', (msg: StepFinishedMessage) => {
      eventBus.emit(EventType.STEP_FINISHED, {
        taskId: msg.payload.task_id,
        stepId: msg.payload.step_id,
        output: msg.payload.output
      });
    });

    // 流式数据块
    this.registerHandler('stream_chunk', (msg: StreamChunkMessage) => {
      eventBus.emit(EventType.STREAM_CHUNK, {
        taskId: msg.payload.task_id,
        chunk: msg.payload.chunk
      });
    });

    // Diff 预览
    this.registerHandler('diff_preview', (msg: DiffPreviewMessage) => {
      // TODO: 转换为 MultiFilePatch 格式
      console.log('📋 收到 Diff 预览:', msg.payload.file_path);
      eventBus.emit(EventType.DIFF_PREVIEW, {
        taskId: msg.payload.task_id,
        fileCount: 1
      });
    });
  }

  /**
   * 设置 WebSocket 监听器
   */
  private setupWebSocketListener(): void {
    websocketService.on('message', (rawMessage: any) => {
      this.receiveMessage(rawMessage);
    });
  }

  /**
   * 触发 Extension 侧事件
   */
  private emitExtensionEvent(message: ExtensionMessage): void {
    switch (message.type) {
      case 'submit_task':
        const submitMsg = message as SubmitTaskMessage;
        eventBus.emit(EventType.TASK_SUBMITTED, {
          taskId: '', // TODO: 从响应中获取
          prompt: submitMsg.payload.prompt
        });
        break;
      
      case 'cancel_task':
        const cancelMsg = message as CancelTaskMessage;
        eventBus.emit(EventType.TASK_CANCELLED, {
          taskId: cancelMsg.payload.task_id,
          reason: '用户取消'
        });
        break;
    }
  }

  /**
   * 触发 Backend 侧事件
   */
  private emitBackendEvent(message: BackendMessage): void {
    // 已在各个 handler 中触发
  }

  /**
   * 便捷方法: 提交任务
   */
  async submitTask(prompt: string, taskType: string, context?: any): Promise<void> {
    const message = createExtensionMessage('submit_task', {
      prompt,
      task_type: taskType,
      context
    });
    await this.sendMessage(message);
  }

  /**
   * 便捷方法: 取消任务
   */
  async cancelTask(taskId: string): Promise<void> {
    const message = createExtensionMessage('cancel_task', {
      task_id: taskId
    });
    await this.sendMessage(message);
  }

  /**
   * 便捷方法: 暂停流式输出
   */
  async pauseStream(taskId: string): Promise<void> {
    const message = createExtensionMessage('pause_stream', {
      task_id: taskId
    });
    await this.sendMessage(message);
  }

  /**
   * 便捷方法: 恢复流式输出
   */
  async resumeStream(taskId: string): Promise<void> {
    const message = createExtensionMessage('resume_stream', {
      task_id: taskId
    });
    await this.sendMessage(message);
  }

  /**
   * 销毁分发器
   */
  dispose(): void {
    this.handlers.clear();
    this.isInitialized = false;
    console.log('🛑 MessageDispatcher 已销毁');
  }
}

// 单例模式
export const dispatcher = new MessageDispatcher();
