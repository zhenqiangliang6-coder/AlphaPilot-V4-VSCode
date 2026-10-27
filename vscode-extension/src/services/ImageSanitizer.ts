// src/services/ImageSanitizer.ts
// 图片压缩中间件 — Worker Thread 异步隔离 + 模型感知 + 真相透传
import { Worker } from 'worker_threads';
import * as path from 'path';

// ═══════════════════════════════════════════════
// 模型感知配置表
// ═══════════════════════════════════════════════
export interface ModelVisionLimits {
  maxWidth: number;
  maxHeight: number;
  quality: number;
  maxImages: number;
  maxInputBytes: number;
  supportedFormats: string[];
}

const MODEL_VISION_LIMITS: Record<string, ModelVisionLimits> = {
  'qwen3.8-omni-flash': {
    maxWidth: 1280,
    maxHeight: 1280,
    quality: 85,
    maxImages: 10,
    maxInputBytes: 10 * 1024 * 1024,
    supportedFormats: ['jpeg', 'png', 'webp'],
  },
  'qwen3-vl-plus': {
    maxWidth: 2048,
    maxHeight: 2048,
    quality: 85,
    maxImages: 5,
    maxInputBytes: 10 * 1024 * 1024,
    supportedFormats: ['jpeg', 'png', 'webp'],
  },
  'gpt-4o': {
    maxWidth: 2048,
    maxHeight: 2048,
    quality: 85,
    maxImages: 10,
    maxInputBytes: 20 * 1024 * 1024,
    supportedFormats: ['jpeg', 'png', 'webp', 'gif'],
  },
  'gemini-2.0-flash': {
    maxWidth: 4096,
    maxHeight: 4096,
    quality: 90,
    maxImages: 16,
    maxInputBytes: 20 * 1024 * 1024,
    supportedFormats: ['jpeg', 'png', 'webp', 'gif'],
  },
  'default': {
    maxWidth: 1024,
    maxHeight: 1024,
    quality: 80,
    maxImages: 3,
    maxInputBytes: 5 * 1024 * 1024,
    supportedFormats: ['jpeg', 'png'],
  },
};

// ═══════════════════════════════════════════════
// 浏览器安全阀 — 不是业务规则，是浏览器生命线
// ═══════════════════════════════════════════════
export const BROWSER_SAFETY_MAX_RAW_BYTES = 25 * 1024 * 1024;

// ═══════════════════════════════════════════════
// Worker 通信配置
// ═══════════════════════════════════════════════
const WORKER_TIMEOUT_MS = 10_000;
const WARMUP_DELAY_MS = 2_000;

export interface SanitizationMeta {
  resized: boolean;
  original_size_kb: number;
  compressed_size_kb: number;
  saved_kb: number;
  compression_duration_ms: number;
  target_model: string;
  applied_limits: ModelVisionLimits;
}

export interface SanitizedImage {
  buffer: Buffer;
  sanitizationMeta: SanitizationMeta;
}

export class ImageSanitizer {
  private worker: Worker | null = null;
  private warmupComplete = false;
  private warmupPromise: Promise<void> | null = null;

  /**
   * 获取指定模型的能力边界
   */
  getLimits(modelId: string): ModelVisionLimits {
    return MODEL_VISION_LIMITS[modelId] || MODEL_VISION_LIMITS['default'];
  }

  /**
   * 获取所有已知模型的边界映射表
   * 供 Webview 批量预取 + 本地缓存，避免 IPC 频率过高
   */
  getAllLimits(): Record<string, ModelVisionLimits> {
    return MODEL_VISION_LIMITS;
  }

  /**
   * 匹配模型名到配置 key
   * 处理 webview 传来的 qwen_generate 等缩写
   */
  resolveModelKey(modelId: string): string {
    const normalized = modelId.replace('_generate', '').toLowerCase();
    if (normalized.includes('qwen') && normalized.includes('omni')) return 'qwen3.8-omni-flash';
    if (normalized.includes('qwen') && normalized.includes('vl')) return 'qwen3-vl-plus';
    if (normalized.includes('gpt')) return 'gpt-4o';
    if (normalized.includes('gemini')) return 'gemini-2.0-flash';
    return 'default';
  }

  /**
   * 启动 Worker Thread（懒加载）
   */
  private ensureWorker(): Worker {
    if (!this.worker) {
      const workerPath = path.join(__dirname, '..', 'workers', 'image-compress.worker.js');
      this.worker = new Worker(workerPath);
    }
    return this.worker;
  }

  /**
   * 预热 Worker — Extension 激活后延迟执行
   * 避免用户粘贴第一张图时遭遇 200-500ms 冷启动
   */
  warmup(): void {
    if (this.warmupPromise) return;
    this.warmupPromise = new Promise<void>((resolve) => {
      setTimeout(async () => {
        try {
          const warmupPixel = Buffer.from(
            '/9j/2wBDAAMCAgMCAgMDAwMEAwMEBQgFBQQEBQoHBwYIDAoMCwsKCwsM',
            'base64'
          );
          await this.sanitize(warmupPixel, 'default');
          this.warmupComplete = true;
          console.log('🔥 ImageSanitizer: Worker 预热完成');
        } catch (e) {
          console.warn('🔥 ImageSanitizer: 预热跳过 (sharp 可能未安装)', e);
        }
        resolve();
      }, WARMUP_DELAY_MS);
    });
  }

  /**
   * 核心压缩方法 — 超时熔断 + 优雅降级
   * 如果 Worker 超时或崩溃，直接透传原图（保留现场让后端报错）
   */
  async sanitize(imageBuffer: Buffer, modelId: string): Promise<SanitizedImage> {
    const modelKey = this.resolveModelKey(modelId);
    const limits = this.getLimits(modelKey);
    const startTime = Date.now();

    const worker = this.ensureWorker();

    const workerPromise = new Promise<{ buffer: Buffer; originalSize: number; compressedSize: number; resized: boolean; originalDimensions: { w: number | undefined; h: number | undefined } }>(
      (resolve, reject) => {
        const onMessage = (msg: any) => {
          worker.removeListener('message', onMessage);
          worker.removeListener('error', onError);
          if (msg.type === 'success') {
            resolve(msg.data);
          } else {
            reject(new Error(msg.error || 'Worker 压缩失败'));
          }
        };

        const onError = (err: Error) => {
          worker.removeListener('message', onMessage);
          worker.removeListener('error', onError);
          reject(err);
        };

        worker.on('message', onMessage);
        worker.on('error', onError);

        worker.postMessage({
          buffer: imageBuffer.buffer.slice(
            imageBuffer.byteOffset,
            imageBuffer.byteOffset + imageBuffer.byteLength
          ),
          maxWidth: limits.maxWidth,
          maxHeight: limits.maxHeight,
          quality: limits.quality,
        });
      }
    );

    try {
      const result = await Promise.race([
        workerPromise,
        new Promise<never>((_, reject) =>
          setTimeout(() => reject(new Error('WORKER_TIMEOUT')), WORKER_TIMEOUT_MS)
        ),
      ]);

      const durationMs = Date.now() - startTime;

      return {
        buffer: result.buffer,
        sanitizationMeta: {
          resized: result.resized,
          original_size_kb: Math.round(result.originalSize / 1024),
          compressed_size_kb: Math.round(result.compressedSize / 1024),
          saved_kb: Math.round((result.originalSize - result.compressedSize) / 1024),
          compression_duration_ms: durationMs,
          target_model: modelKey,
          applied_limits: limits,
        },
      };
    } catch (err) {
      const durationMs = Date.now() - startTime;
      console.warn('🔥 ImageSanitizer: 压缩失败，透传原图 —', err);

      return {
        buffer: imageBuffer,
        sanitizationMeta: {
          resized: false,
          original_size_kb: Math.round(imageBuffer.length / 1024),
          compressed_size_kb: Math.round(imageBuffer.length / 1024),
          saved_kb: 0,
          compression_duration_ms: durationMs,
          target_model: modelKey,
          applied_limits: limits,
        },
      };
    }
  }

  /**
   * 释放 Worker 资源
   */
  dispose(): void {
    this.worker?.terminate();
    this.worker = null;
    this.warmupComplete = false;
    this.warmupPromise = null;
  }
}

export const imageSanitizer = new ImageSanitizer();