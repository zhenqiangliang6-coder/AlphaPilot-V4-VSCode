/**
 * TaskModel v2 - Node 端最终版
 * ------------------------------------------------
 * 这是智能体执行引擎的标准任务格式（与 Python Worker v2 完全一致）
 * 支持：
 * - 状态机（status）
 * - 任务树（steps）
 * - 事件流（events）
 * - 智能体上下文（context）
 * - 完整 meta 信息
 * - 向后兼容 v1 Worker（旧 Worker 忽略新增字段）
 */

function createTaskSubmit(task_id, type, payload, source = "vscode-extension") {
  const now = Date.now();

  return {
    version: "2.0",
    task_id,
    type,

    // 状态机入口
    status: "pending",

    // 任务输入
    payload,

    // 智能体上下文（未来 Planner / Tool / Subtask 都会写入）
    context: {
      memory: {},
      intermediate_results: [],
      tool_outputs: [],
      subtasks: []
    },

    // 任务树（未来 Task Decomposition 会填充）
    steps: [],

    // 事件流（stream_start / token / tool_call / step_start / ...）
    events: [],

    // 元信息
    meta: {
      created_at: now,
      started_at: null,
      finished_at: null,
      worker_id: null,
      retry_count: 0,
      source
    }
  };
}

/**
 * 创建成功结果（v2）
 */
function createTaskResultSuccess({
  task_id,
  task_type,
  result,
  worker_id = "node-worker",
  started_at,
  steps = [],
  events = [],
  context = {}
}) {
  const now = Date.now();

  return {
    version: "2.0",
    task_id,
    type: task_type,
    status: "done",

    result,
    error: null,

    steps,
    events,
    context,

    meta: {
      started_at,
      finished_at: now,
      worker_id,
      duration_ms: now - started_at
    }
  };
}

/**
 * 创建失败结果（v2）
 */
function createTaskResultError({
  task_id,
  task_type,
  error_message,
  worker_id = "node-worker",
  error_code = "UNKNOWN_ERROR",
  error_stack = null,
  retryable = true,
  started_at,
  retry_count = 0,
  steps = [],
  events = [],
  context = {}
}) {
  const now = Date.now();

  return {
    version: "2.0",
    task_id,
    type: task_type,
    status: "error",

    result: null,

    error: {
      message: error_message,
      code: error_code,
      stack: error_stack,
      retryable
    },

    steps,
    events,
    context,

    meta: {
      started_at,
      finished_at: now,
      worker_id,
      duration_ms: now - started_at,
      retry_count
    }
  };
}

/**
 * 创建 DLQ 项目（v2）
 */
function createDLQItem(original_task, failure_record, retry_count, first_failed_at) {
  const now = Date.now();

  return {
    version: "2.0",
    task_id: original_task.task_id,
    original_task,
    failure_record,
    retry_count,
    first_failed_at,
    last_failed_at: now,
    meta: {
      created_at: now,
      reason: failure_record.retryable
        ? "exceeded_max_retries"
        : "non_retryable"
    }
  };
}

module.exports = {
  createTaskSubmit,
  createTaskResultSuccess,
  createTaskResultError,
  createDLQItem
};
