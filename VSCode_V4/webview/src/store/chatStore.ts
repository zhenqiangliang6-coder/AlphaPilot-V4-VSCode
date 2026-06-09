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
  
  // ⭐ v2.6 新增：意图和人格元数据
  intent?: string;      // 意图类型 (write_code/explain_code/creative_writing等)
  persona?: string;     // 人格类型 (engineer/creator/conversational)
  
  // ⭐ 新增：流式通道内容分离
  reasoningContent?: string;  // channel = reasoning (思考过程)
  contentChannel?: string;    // channel = content (最终产出)
}

export interface Step {
  id: string;
  type: 'analyze' | 'plan' | 'write' | 'refine' | 'test';
  status: 'pending' | 'running' | 'completed' | 'failed';
  output?: any;
  startedAt?: number;
  completedAt?: number;
  duration?: number;  // ⭐ v3.0 新增：步骤执行耗时（毫秒）
  
  // ⭐ 新增：阶段信息
  phase?: 'analyze' | 'plan' | 'write' | 'refine' | 'test';
}

export interface ChatState {
  messages: Message[];
  currentTaskId: string | null;
  isStreaming: boolean;
  selectedModel: string;
  currentPhase: string | null;  // ⭐ 新增：当前阶段
  
  // Actions
  addMessage: (message: Message) => void;
  updateMessage: (id: string, updates: Partial<Message> | ((prev: Message) => Message)) => void;
  setCurrentTaskId: (taskId: string | null) => void;
  setStreaming: (isStreaming: boolean) => void;
  setSelectedModel: (model: string) => void;
  clearMessages: () => void;
  addStep: (taskId: string, step: Step) => void;
  updateStep: (taskId: string, stepId: string, updates: Partial<Step>) => void;
  setCurrentPhase: (phase: string | null) => void;  // ⭐ 新增
}

export const useChatStore = create<ChatState>()(
  persist(
    (set, get) => ({
      messages: [],
      currentTaskId: null,
      isStreaming: false,
      selectedModel: 'qwen-turbo',  // ⭐ 改为默认模型名
      currentPhase: null,  // ⭐ 初始化
      
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
        set({ messages: [], currentTaskId: null, isStreaming: false, currentPhase: null }),
      
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
        })),
      
      // ⭐ 新增：设置当前阶段
      setCurrentPhase: (phase) =>
        set({ currentPhase: phase })
    }),
    {
      name: 'alphapilot-chat-storage',
      partialize: (state) => ({ 
        selectedModel: state.selectedModel 
      })
    }
  )
);
