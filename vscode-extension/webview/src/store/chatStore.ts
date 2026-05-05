// src/store/chatStore.ts
import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: number;
  taskId?: string;
  steps?: Step[];
}

export interface Step {
  id: string;
  type: 'analyze' | 'plan' | 'write' | 'refine' | 'test';
  status: 'pending' | 'running' | 'completed' | 'failed';
  output?: any;
  startedAt?: number;
  completedAt?: number;
}

export interface ChatState {
  messages: Message[];
  currentTaskId: string | null;
  isStreaming: boolean;
  selectedModel: string;
  
  // Actions
  addMessage: (message: Message) => void;
  updateMessage: (id: string, updates: Partial<Message> | ((prev: Message) => Message)) => void;
  setCurrentTaskId: (taskId: string | null) => void;
  setStreaming: (isStreaming: boolean) => void;
  setSelectedModel: (model: string) => void;
  clearMessages: () => void;
  addStep: (taskId: string, step: Step) => void;
  updateStep: (taskId: string, stepId: string, updates: Partial<Step>) => void;
}

export const useChatStore = create<ChatState>()(
  persist(
    (set, get) => ({
      messages: [],
      currentTaskId: null,
      isStreaming: false,
      selectedModel: 'qwen_generate',
      
      addMessage: (message) => 
        set((state) => ({ 
          messages: [...state.messages, message] 
        })),
      
      updateMessage: (id, updates) =>
        set((state) => ({
          messages: state.messages.map(msg => {
            if (msg.id === id) {
              // 支持函数式更新
              if (typeof updates === 'function') {
                return updates(msg);
              }
              // 支持对象合并更新
              return { ...msg, ...updates };
            }
            return msg;
          })
        })),
      
      setCurrentTaskId: (taskId) =>
        set({ currentTaskId: taskId }),
      
      setStreaming: (isStreaming) =>
        set({ isStreaming }),
      
      setSelectedModel: (model) =>
        set({ selectedModel: model }),
      
      clearMessages: () =>
        set({ messages: [], currentTaskId: null, isStreaming: false }),
      
      addStep: (taskId, step) =>
        set((state) => ({
          messages: state.messages.map(msg => {
            if (msg.taskId === taskId) {
              return {
                ...msg,
                steps: [...(msg.steps || []), step]
              };
            }
            return msg;
          })
        })),
      
      updateStep: (taskId, stepId, updates) =>
        set((state) => ({
          messages: state.messages.map(msg => {
            if (msg.taskId === taskId && msg.steps) {
              return {
                ...msg,
                steps: msg.steps.map(step =>
                  step.id === stepId ? { ...step, ...updates } : step
                )
              };
            }
            return msg;
          })
        }))
    }),
    {
      name: 'alphapilot-chat-storage',
      partialize: (state) => ({ 
        selectedModel: state.selectedModel 
      })
    }
  )
);
