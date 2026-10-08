/**
 * AlphaPilot 记忆中枢 - 类型定义
 * 
 * 定义记忆管理面板所需的所有数据类型
 */

// ============================================================
// 记忆类型枚举
// ============================================================
export enum MemoryType {
  PREFERENCE = 'preference',      // 用户偏好
  FACT = 'fact',                  // 事实知识
  SKILL = 'skill',                // 技能经验
  CONVERSATION = 'conversation',  // 对话记忆
  INSIGHT = 'insight'             // 洞察领悟
}

export enum MemoryStatus {
  ACTIVE = 'active',              // 活跃
  ARCHIVED = 'archived',          // 归档
  PRUNED = 'pruned',              // 已剪枝
  MERGED = 'merged'               // 已合并
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
