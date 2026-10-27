/**
 * AlphaPilot 记忆中枢 - 类型定义
 * 
 * 定义记忆管理面板所需的所有数据类型
 */

// ============================================================
// 记忆类型枚举（v2.0：六大记忆分类体系）
// ============================================================
export enum MemoryType {
  PREFERENCE = 'preference',      // 用户偏好：语言、风格、工作习惯
  PROJECT_FACT = 'project_fact',  // 项目事实：技术栈、架构约束、路径约定
  DECISION = 'decision',          // 决策：已采纳/待确认的技术决策
  TASK_EPISODE = 'task_episode',  // 任务情景：文件修改、中断点、下一步
  KNOWLEDGE = 'knowledge',        // 知识经验：验证过的修复方法、已知陷阱
  FEEDBACK = 'feedback',          // 反馈纠错：用户否决、测试推翻的结论
  CONVERSATION = 'conversation',  // 对话记忆（低价值，默认不持久化）
  SKILL = 'skill',                // 技能经验
  FACT = 'fact',                  // 事实知识（向后兼容）
}

export enum MemoryStatus {
  ACTIVE = 'active',              // 当前有效
  PROPOSED = 'proposed',          // 模型候选，未确认
  CONFIRMED = 'confirmed',        // 用户/流程确认
  VERIFIED = 'verified',          // 工具/测试验证通过
  SUPERSEDED = 'superseded',      // 已被新版本替代
  EXPIRED = 'expired',            // 已过期不再适用
  REJECTED = 'rejected',          // 已被明确拒绝
  ARCHIVED = 'archived',          // 归档保留
  PRUNED = 'pruned',              // 已剪枝
  MERGED = 'merged',              // 已合并
}

// ============================================================
// 记忆条目接口
// ============================================================
export interface MemoryItem {
  id: string;
  user_id: string;
  content: string;
  summary?: string;
  memory_type: MemoryType;
  domain_tags: string[];
  importance_score: number;       // 0~1
  activation_score: number;       // 0~1
  access_count: number;
  last_accessed_at: string;       // ISO 8601
  created_at: string;             // ISO 8601
  status: MemoryStatus;
  merged_into?: string;
}

// ============================================================
// 记忆关联边接口
// ============================================================
export interface MemoryEdge {
  source_id: string;
  target_id: string;
  relation_type: 'related_to' | 'contradicts' | 'depends_on' | 'is_example_of';
  strength: number;               // 0~1
  created_at: string;
}

// ============================================================
// 记忆查询参数
// ============================================================
export interface MemoryQueryParams {
  user_id: string;
  memory_type?: MemoryType;
  status?: MemoryStatus;
  domain_tags?: string[];
  min_importance?: number;
  min_activation?: number;
  search_query?: string;
  limit?: number;
  offset?: number;
  sort_by?: 'created_at' | 'importance_score' | 'activation_score' | 'access_count';
  sort_order?: 'asc' | 'desc';
}

// ============================================================
// 记忆统计接口
// ============================================================
export interface MemoryStats {
  total_count: number;
  active_count: number;
  archived_count: number;
  by_type: Record<MemoryType, number>;
  by_status: Record<MemoryStatus, number>;
  average_importance: number;
  average_activation: number;
}

// ============================================================
// API 响应接口
// ============================================================
export interface MemoryApiResponse<T> {
  success: boolean;
  data?: T;
  error?: string;
  message?: string;
}

export interface MemoryListResponse {
  items: MemoryItem[];
  total: number;
  limit: number;
  offset: number;
}

// ============================================================
// 记忆图谱节点接口（用于可视化）
// ============================================================
export interface MemoryGraphNode {
  id: string;
  label: string;
  type: MemoryType;
  importance: number;
  activation: number;
  tags: string[];
  x?: number;
  y?: number;
}

export interface MemoryGraphEdge {
  source: string;
  target: string;
  type: string;
  strength: number;
}

export interface MemoryGraph {
  nodes: MemoryGraphNode[];
  edges: MemoryGraphEdge[];
}