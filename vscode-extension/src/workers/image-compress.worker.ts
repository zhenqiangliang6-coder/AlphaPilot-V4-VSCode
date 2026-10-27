// src/workers/image-compress.worker.ts
// Worker Thread — 纯物理计算，零业务逻辑
// 在独立线程中执行 sharp 压缩，避免阻塞 Extension Host 主线程
import { parentPort } from 'worker_threads';
import sharp from 'sharp';

interface CompressTask {
  buffer: ArrayBuffer;
  maxWidth: number;
  maxHeight: number;
  quality: number;
}

interface CompressResult {
  buffer: Buffer;
  originalSize: number;
  compressedSize: number;
  resized: boolean;
  originalDimensions: { w: number | undefined; h: number | undefined };
}

async function compress(task: CompressTask): Promise<CompressResult> {
  const input = Buffer.from(task.buffer);
  const metadata = await sharp(input).metadata();

  const needsResize =
    (metadata.width || 0) > task.maxWidth ||
    (metadata.height || 0) > task.maxHeight;

  let outputBuffer: Buffer;
  if (needsResize) {
    outputBuffer = await sharp(input)
      .resize({
        width: task.maxWidth,
        height: task.maxHeight,
        fit: 'inside',
        withoutEnlargement: true,
      })
      .jpeg({ quality: task.quality, progressive: true })
      .toBuffer();
  } else {
    outputBuffer = await sharp(input)
      .jpeg({ quality: task.quality, progressive: true })
      .toBuffer();
  }

  return {
    buffer: outputBuffer,
    originalSize: input.length,
    compressedSize: outputBuffer.length,
    resized: needsResize,
    originalDimensions: { w: metadata.width, h: metadata.height },
  };
}

parentPort?.on('message', async (task: CompressTask) => {
  try {
    const result = await compress(task);
    parentPort?.postMessage({ type: 'success', data: result });
  } catch (err) {
    parentPort?.postMessage({ type: 'error', error: String(err) });
  }
});