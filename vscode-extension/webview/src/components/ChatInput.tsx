// src/components/ChatInput.tsx
import React, { useState, KeyboardEvent, useRef, ClipboardEvent, ChangeEvent } from 'react';
import { useChatStore } from '../store/chatStore';
import { submitTask, ImageAttachment, BROWSER_SAFETY_MAX_RAW_BYTES } from '../utils/vscode';

const DEFAULT_MAX_IMAGES = 3;

export const ChatInput: React.FC = () => {
  const [input, setInput] = useState('');
  const [images, setImages] = useState<ImageAttachment[]>([]);
  const { selectedModel, isStreaming, setPendingImages, visionLimits } = useChatStore();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const limits = visionLimits?.[selectedModel] || visionLimits?.['default'];
  const maxImages = limits?.maxImages ?? DEFAULT_MAX_IMAGES;

  const handleSubmit = async () => {
    const hasText = input.trim().length > 0;
    const hasImages = images.length > 0;
    if ((!hasText && !hasImages) || isStreaming) return;

    // 为 ChatBubble 预览生成 base64（File 对象无法存入 Zustand localStorage）
    const previewImages = await Promise.all(
      images.map(async (img) => {
        const base64 = await new Promise<string>((resolve) => {
          const reader = new FileReader();
          reader.onload = () => resolve(reader.result as string);
          reader.readAsDataURL(img.file);
        });
        return { id: img.id, name: img.name, base64 };
      })
    );
    setPendingImages(previewImages);

    // Transferable Objects — 零拷贝传输 ArrayBuffer
    await submitTask(input.trim(), selectedModel, images.length > 0 ? images : undefined);

    setInput('');
    setImages([]);
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  // 验证文件并创建 ImageAttachment
  const createImageAttachment = (file: File): ImageAttachment | null => {
    if (!file.type.startsWith('image/')) return null;

    // 浏览器安全阀 — 25MB 上限，防止 Webview OOM
    if (file.size > BROWSER_SAFETY_MAX_RAW_BYTES) {
      console.warn(`图片 ${file.name} 超过浏览器安全阀限制 (${Math.round(BROWSER_SAFETY_MAX_RAW_BYTES / 1024 / 1024)}MB)`);
      return null;
    }

    if (limits) {
      const format = file.type.replace('image/', '');
      if (!limits.supportedFormats.includes(format)) {
        console.warn(`图片格式 ${format} 不被模型 ${selectedModel} 支持`);
        return null;
      }
    }

    return {
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      name: file.name || 'pasted-image.png',
      file,
    };
  };

  const addImages = (files: FileList | File[]) => {
    if (images.length >= maxImages) return;

    const remaining = maxImages - images.length;
    const toAdd = Array.from(files).slice(0, remaining);

    const newImages: ImageAttachment[] = [];
    for (const file of toAdd) {
      const img = createImageAttachment(file);
      if (img) newImages.push(img);
    }

    if (newImages.length > 0) {
      setImages(prev => [...prev, ...newImages].slice(0, maxImages));
    }
  };

  const handlePaste = (e: ClipboardEvent<HTMLTextAreaElement>) => {
    const items = e.clipboardData?.items;
    if (!items) return;

    const imageFiles: File[] = [];
    for (let i = 0; i < items.length; i++) {
      if (items[i].type.startsWith('image/')) {
        const file = items[i].getAsFile();
        if (file) imageFiles.push(file);
      }
    }

    if (imageFiles.length > 0) {
      e.preventDefault();
      addImages(imageFiles);
    }
  };

  const handleFileChange = (e: ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      addImages(e.target.files);
      e.target.value = '';
    }
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.dataTransfer.files) {
      addImages(e.dataTransfer.files);
    }
  };

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const removeImage = (id: string) => {
    setImages(prev => prev.filter(img => img.id !== id));
  };

  const hasContent = input.trim().length > 0 || images.length > 0;
  const safetyLimitMB = Math.round(BROWSER_SAFETY_MAX_RAW_BYTES / 1024 / 1024);

  return (
    <div
      className="border-t border-vscode-border p-4 bg-vscode-bg"
      onDrop={handleDrop}
      onDragOver={handleDragOver}
    >
      {/* 图片预览区 */}
      {images.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-3">
          {images.map((img) => (
            <div key={img.id} className="relative group">
              <img
                src={URL.createObjectURL(img.file)}
                alt={img.name}
                className="w-20 h-20 object-cover rounded border border-vscode-border hover:opacity-90"
              />
              <button
                onClick={() => removeImage(img.id)}
                className="absolute -top-1 -right-1 w-5 h-5 bg-red-500 text-white rounded-full text-xs flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
                title="移除图片"
              >
                ×
              </button>
              <div className="text-[10px] text-gray-400 truncate w-20 text-center mt-0.5">
                {img.name.length > 12 ? img.name.slice(0, 10) + '…' : img.name}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* 输入区 */}
      <div className="flex gap-2">
        <textarea
          ref={textareaRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          onPaste={handlePaste}
          placeholder={
            images.length > 0
              ? '输入任务描述... (图片将附加到任务中)'
              : `输入任务描述... (Enter 发送, Shift+Enter 换行, 粘贴/拖拽上传图片, 最大 ${safetyLimitMB}MB)`
          }
          disabled={isStreaming}
          className="flex-1 px-3 py-2 bg-vscode-input-bg text-vscode-input-fg border border-vscode-border rounded resize-none focus:outline-none focus:border-vscode-accent disabled:opacity-50"
          rows={3}
        />
        <div className="flex flex-col gap-1">
          <button
            onClick={handleSubmit}
            disabled={!hasContent || isStreaming}
            className="flex-1 px-4 py-2 bg-vscode-button-bg text-vscode-button-fg rounded hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed transition-opacity"
            title="发送"
          >
            {isStreaming ? '⏳' : '📤'}
          </button>
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={isStreaming || images.length >= maxImages}
            className="px-4 py-2 bg-vscode-input-bg text-vscode-input-fg border border-vscode-border rounded hover:border-vscode-accent disabled:opacity-40 disabled:cursor-not-allowed transition-colors text-sm"
            title={images.length >= maxImages ? `最多 ${maxImages} 张图片` : '选择图片'}
          >
            🖼
          </button>
        </div>
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          multiple
          onChange={handleFileChange}
          className="hidden"
        />
      </div>

      {/* 底部提示 */}
      <div className="mt-2 flex justify-between text-xs text-gray-500">
        <span>
          模型: <span className="text-vscode-accent">{selectedModel.replace('_generate', '').toUpperCase()}</span>
          {limits && (
            <span> | 图片限制: {maxImages} 张, ≤{limits.maxWidth}×{limits.maxHeight}</span>
          )}
        </span>
        <span>
          {images.length > 0 && `${images.length}/${maxImages} 张`}
          {images.length === 0 && `最大 ${safetyLimitMB}MB · ${maxImages} 张`}
        </span>
      </div>
    </div>
  );
};