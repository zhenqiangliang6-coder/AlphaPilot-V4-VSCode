// src/components/ModelSelector.tsx
import React from 'react';
import { useChatStore } from '../store/chatStore';

const models = [
  { value: 'qwen_generate', label: '通义千问 (Qwen)', desc: '快速响应' },
  { value: 'deepseek_generate', label: '深度求索 (DeepSeek)', desc: '平衡性能' },
  { value: 'doubao_generate', label: '豆包 (Doubao)', desc: '多模态支持' }
];

export const ModelSelector: React.FC = () => {
  const { selectedModel, setSelectedModel } = useChatStore();

  return (
    <div className="border-b border-vscode-border p-3 bg-vscode-bg">
      <div className="flex items-center gap-2">
        <span className="text-sm font-semibold text-vscode-fg">🤖 模型:</span>
        <select
          value={selectedModel}
          onChange={(e) => setSelectedModel(e.target.value)}
          className="flex-1 px-3 py-1.5 bg-vscode-input-bg text-vscode-input-fg border border-vscode-border rounded text-sm focus:outline-none focus:border-vscode-accent"
        >
          {models.map((model) => (
            <option key={model.value} value={model.value}>
              {model.label} - {model.desc}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
};
