// src/services/streamingService.ts
// 流式输出管理服务

interface StreamState {
  taskId: string;
  isPaused: boolean;
  buffer: string[];
  charCount: number;
  startTime: number;
  lastUpdateTime: number;
}

class StreamingService {
  private streams: Map<string, StreamState> = new Map();
  private callbacks: Map<string, (chunk: string) => void> = new Map();

  /**
   * 开始流式输出
   */
  startStream(taskId: string): void {
    console.log(`🌊 开始流式输出：${taskId}`);
    
    this.streams.set(taskId, {
      taskId,
      isPaused: false,
      buffer: [],
      charCount: 0,
      startTime: Date.now(),
      lastUpdateTime: Date.now()
    });
  }

  /**
   * 追加流式内容块
   */
  appendChunk(taskId: string, content: string): void {
    const stream = this.streams.get(taskId);
    if (!stream) {
      console.warn(`⚠️ 流不存在：${taskId}, 创建新流`);
      this.startStream(taskId);
      return this.appendChunk(taskId, content);
    }

    // 更新状态
    stream.lastUpdateTime = Date.now();
    stream.charCount += content.length;

    // 如果暂停，加入缓冲区
    if (stream.isPaused) {
      stream.buffer.push(content);
      console.log(`⏸️ 流已暂停，内容已缓冲 (${stream.buffer.length} 块)`);
      return;
    }

    // 立即处理
    this.processChunk(taskId, content);
  }

  /**
   * 处理内容块
   */
  private processChunk(taskId: string, content: string): void {
    const callback = this.callbacks.get(taskId);
    if (callback) {
      callback(content);
    } else {
      console.warn(`⚠️ 没有注册回调函数：${taskId}`);
    }
  }

  /**
   * 暂停流式输出
   */
  pauseStream(taskId: string): void {
    const stream = this.streams.get(taskId);
    if (stream) {
      stream.isPaused = true;
      console.log(`⏸️ 流已暂停：${taskId} (已输出 ${stream.charCount} 字)`);
    }
  }

  /**
   * 恢复流式输出
   */
  resumeStream(taskId: string): void {
    const stream = this.streams.get(taskId);
    if (stream) {
      stream.isPaused = false;
      console.log(`▶️ 流已恢复，处理 ${stream.buffer.length} 块缓冲内容`);

      // 处理缓冲区
      while (stream.buffer.length > 0) {
        const content = stream.buffer.shift()!;
        this.processChunk(taskId, content);
      }
    }
  }

  /**
   * 结束流式输出
   */
  endStream(taskId: string): void {
    const stream = this.streams.get(taskId);
    if (stream) {
      const duration = Date.now() - stream.startTime;
      console.log(`✅ 流式输出完成：${taskId} (${stream.charCount} 字，${duration}ms)`);
      
      // 清理
      this.streams.delete(taskId);
      this.callbacks.delete(taskId);
    }
  }

  /**
   * 获取流状态
   */
  getStreamState(taskId: string): StreamState | undefined {
    return this.streams.get(taskId);
  }

  /**
   * 检查是否暂停
   */
  isPaused(taskId: string): boolean {
    return this.streams.get(taskId)?.isPaused || false;
  }

  /**
   * 获取字符计数
   */
  getCharCount(taskId: string): number {
    return this.streams.get(taskId)?.charCount || 0;
  }

  /**
   * 注册内容回调
   */
  onChunk(taskId: string, callback: (chunk: string) => void): () => void {
    this.callbacks.set(taskId, callback);
    
    return () => {
      this.callbacks.delete(taskId);
    };
  }

  /**
   * 清空流
   */
  clearStream(taskId: string): void {
    const stream = this.streams.get(taskId);
    if (stream) {
      stream.buffer = [];
      stream.charCount = 0;
    }
  }
}

// 单例模式
export const streamingService = new StreamingService();
