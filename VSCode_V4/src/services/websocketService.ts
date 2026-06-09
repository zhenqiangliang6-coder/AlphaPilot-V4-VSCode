// src/services/websocketService.ts
// WebSocket 通信服务 - 使用 Socket.io 客户端

import * as vscode from 'vscode';
import { io, Socket } from 'socket.io-client';

export type EventHandler = (data: any) => void;

class WebSocketService {
  private socket: Socket | null = null;
  private eventHandlers: Map<string, Set<EventHandler>> = new Map();
  private messageQueue: any[] = [];
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 1000;
  private isConnecting = false;

  /**
   * 连接到 Socket.io 服务器
   */
  connect(url: string): Promise<void> {
    return new Promise((resolve, reject) => {
      if (this.isConnecting) {
        reject(new Error('已经在连接中'));
        return;
      }

      this.isConnecting = true;
      console.log(`🔌 正在连接 Socket.io: ${url}`);

      try {
        // 使用 socket.io-client 连接
        this.socket = io(url, {
          transports: ['websocket', 'polling'],
          reconnection: true,
          reconnectionDelay: 1000,
          reconnectionDelayMax: 5000,
          reconnectionAttempts: 10,
        });

        this.socket.on('connect', () => {
          console.log('✅ Socket.io 已连接');
          this.isConnecting = false;
          this.reconnectAttempts = 0;
          
          // 发送缓存的消息
          while (this.messageQueue.length > 0) {
            const message = this.messageQueue.shift();
            if (this.socket) {
              this.socket.emit('message', message);
            }
          }
          
          resolve();
        });

        this.socket.on('disconnect', (reason) => {
          console.log('❌ Socket.io 已断开连接:', reason);
          this.isConnecting = false;
          
          if (reason === 'io server disconnect') {
            // 服务器主动断开，需要重新连接
            this.socket?.connect();
          }
        });

        this.socket.on('connect_error', (error) => {
          console.error('❌ Socket.io 连接错误:', error.message);
          this.isConnecting = false;
          reject(error);
        });

        // 监听所有事件
        this.socket.onAny((eventName, ...args) => {
          console.log(`📥 收到事件: ${eventName}`, args[0]);
          this.handleMessage({ [eventName]: args[0] });
        });

      } catch (error) {
        this.isConnecting = false;
        reject(error);
      }
    });
  }

  /**
   * 处理接收到的消息
   */
  private handleMessage(data: any) {
    // 兼容 socket.io 的 emit 格式：{ eventName: payload }
    const eventKeys = Object.keys(data);
    
    for (const key of eventKeys) {
      const payload = data[key];
      const handlers = this.eventHandlers.get(key);
      
      if (handlers) {
        handlers.forEach(handler => {
          try {
            handler(payload);
          } catch (error) {
            console.error('❌ 事件处理器错误:', error);
          }
        });
      }
    }

    // 同时支持标准事件格式
    if (data.event) {
      const handlers = this.eventHandlers.get(data.event);
      if (handlers) {
        handlers.forEach(handler => handler(data));
      }
    }
  }

  /**
   * 订阅事件
   */
  on(event: string, handler: EventHandler): () => void {
    if (!this.eventHandlers.has(event)) {
      this.eventHandlers.set(event, new Set());
    }
    
    this.eventHandlers.get(event)!.add(handler);
    
    // 返回取消订阅函数
    return () => {
      this.off(event, handler);
    };
  }

  /**
   * 取消订阅事件
   */
  off(event: string, handler: EventHandler) {
    const handlers = this.eventHandlers.get(event);
    if (handlers) {
      handlers.delete(handler);
    }
  }

  /**
   * 发送消息（使用 Socket.io emit）
   */
  send(data: any): void {
    if (this.socket && this.socket.connected) {
      // Socket.io 使用 emit 发送事件
      if (data.event) {
        const { event, ...payload } = data;
        console.log(`📤 发送事件: ${event}`, payload);
        this.socket.emit(event, payload);
      } else {
        console.log(`📤 发送消息:`, data);
        this.socket.emit('message', data);
      }
    } else {
      console.warn('⚠️ Socket.io 未连接，消息已加入队列:', data);
      this.messageQueue.push(data);
    }
  }

  /**
   * 订阅任务
   */
  subscribeTask(taskId: string): void {
    console.log(`📡 订阅任务：${taskId}`);
    if (this.socket) {
      this.socket.emit('subscribe_task', taskId);
    } else {
      console.warn('⚠️ Socket.io 未连接，订阅请求已加入队列');
      this.messageQueue.push({
        event: 'subscribe_task',
        task_id: taskId
      });
    }
  }

  /**
   * 取消订阅任务
   */
  unsubscribeTask(taskId: string): void {
    console.log(` 取消订阅任务：${taskId}`);
    if (this.socket) {
      this.socket.emit('unsubscribe_task', taskId);
    }
  }

  /**
   * 断开连接
   */
  disconnect(): void {
    if (this.socket) {
      console.log('🔌 断开 Socket.io 连接');
      this.socket.disconnect();
      this.socket = null;
    }
    this.eventHandlers.clear();
    this.messageQueue = [];
  }

  /**
   * 检查是否已连接
   */
  isConnected(): boolean {
    return this.socket !== null && this.socket.connected;
  }
}

// 单例模式
export const websocketService = new WebSocketService();