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
  
  // P1：结构化产物列表
  artifacts?: Artifact[];
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

// P1：结构化产物
export interface Artifact {
  artifact_id: string;
  artifact_type: string;
  format: string;
  content: string;
  label?: string;
  sequence: number;
  created_at: number;
}

export interface ChatState {
  messages: Message[];
  currentTaskId: string | null;
  isStreaming: boolean;
  selectedModel: string;
  currentPhase: string | null;  // ⭐ 新增：当前阶段
  pendingImages: { id: string; name: string; base64: string }[];  // 待关联图片预览
  visionLimits: Record<string, { maxImages: number; maxResolution?: number; supportedFormats: string[]; maxWidth?: number; maxHeight?: number }>;  // 视觉模型限制
  
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
  addArtifact: (taskId: string, artifact: Artifact) => void;  // P1
  setPendingImages: (images: { id: string; name: string; base64: string }[]) => void;
}

export const useChatStore = create<ChatState>()(
  persist(
    (set, get) => ({
      messages: [],
      currentTaskId: null,
      isStreaming: false,
      // 默认值必须是 ModelSelector 中的 value（形如 xxx_generate）。
      // 此前为 'qwen-turbo'，与选择器取值格式不一致：首次使用（无 localStorage）
      // 提交时该值会作为任务 type 传给 Node API，命中 index.js 的兜底队列
      // "task_queue"，而没有任何 worker 监听该队列，任务会永久卡在 pending。
      selectedModel: 'qwen_generate',
      currentPhase: null,  // ⭐ 初始化
      pendingImages: [],
      visionLimits: {
        default: { maxImages: 3, supportedFormats: ['png', 'jpeg', 'jpg', 'webp'], maxWidth: 2048, maxHeight: 2048 },
        doubao_generate: { maxImages: 5, supportedFormats: ['png', 'jpeg', 'jpg', 'webp'], maxWidth: 4096, maxHeight: 4096 },
        gemini_generate: { maxImages: 5, supportedFormats: ['png', 'jpeg', 'jpg', 'webp'], maxWidth: 2048, maxHeight: 2048 },
      },
      
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
        set({ currentPhase: phase }),

      // P1：添加产物（幂等：同 (task_id, artifact_id) 只保留首次）
      addArtifact: (taskId, artifact) =>
        set((state) => ({
          messages: state.messages.map(msg => {
            if (msg.taskId !== taskId) return msg;
            const existing = msg.artifacts || [];
            const exists = existing.some(a => a.artifact_id === artifact.artifact_id);
            if (exists) return msg;
            return {
              ...msg,
              artifacts: [...existing, artifact].sort((a, b) => a.sequence - b.sequence)
            };
          })
        })),

      setPendingImages: (images) =>
        set({ pendingImages: images }),
    }),
    {
      name: 'alphapilot-chat-storage',
      version: 4,
      partialize: (state) => ({ 
        selectedModel: state.selectedModel,
      }),
      migrate: (persisted: unknown, version: number) => {
        const state = (persisted || {}) as { selectedModel?: string; collaborationMode?: string };

        // version < 4：修正 qwen-turbo 等非法值
        if (version < 4 && (state.selectedModel === 'qwen-turbo' || !state.selectedModel)) {
          state.selectedModel = 'qwen_generate';
        }
        delete state.collaborationMode;

        return state as ChatState;
      }
    }
  )
);