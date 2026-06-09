// src/components/ChatInput.tsx
import React, { useState, KeyboardEvent } from 'react';
import { useChatStore } from '../store/chatStore';
import { submitTask } from '../utils/vscode';

export const ChatInput: React.FC = () => {
  const [input, setInput] = useState('');
  const { selectedModel, isStreaming } = useChatStore();

  const handleSubmit = () => {
    if (!input.trim() || isStreaming) return;
    
    submitTask(input.trim(), selectedModel);
    setInput('');
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="border-t border-vscode-border p-4 bg-vscode-bg">
      <div className="flex gap-2">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="输入任务描述... (Enter 发送, Shift+Enter 换行)"
          disabled={isStreaming}
          className="flex-1 px-3 py-2 bg-vscode-input-bg text-vscode-input-fg border border-vscode-border rounded resize-none focus:outline-none focus:border-vscode-accent disabled:opacity-50"
          rows={3}
        />
        <button
          onClick={handleSubmit}
          disabled={!input.trim() || isStreaming}
          className="px-4 py-2 bg-vscode-button-bg text-vscode-button-fg rounded hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed transition-opacity"
        >
          {isStreaming ? '⏳' : '📤'}
        </button>
      </div>
      <div className="mt-2 text-xs text-gray-500">
        当前模型: <span className="text-vscode-accent">{selectedModel.replace('_generate', '').toUpperCase()}</span>
      </div>
    </div>
  );
};
