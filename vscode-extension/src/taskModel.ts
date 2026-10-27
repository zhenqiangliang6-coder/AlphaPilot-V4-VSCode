export type TaskStatus = "pending" | "done" | "error";

export const TASK_STATE_COMPLETED = "COMPLETED";
export const TASK_STATE_FAILED = "FAILED";
export const TASK_STATE_WAITING_AUTHORIZATION = "WAITING_AUTHORIZATION";
export const TASK_STATE_RUNNING = "RUNNING";
export const TASK_STATE_PENDING = "PENDING";

const TASK_STATE_VALUES = new Set<string>([
    TASK_STATE_PENDING,
    TASK_STATE_RUNNING,
    TASK_STATE_COMPLETED,
    TASK_STATE_FAILED,
    TASK_STATE_WAITING_AUTHORIZATION,
]);

const TASK_STATE_TO_STATUS: Record<string, string> = {
    [TASK_STATE_COMPLETED]: "done",
    [TASK_STATE_FAILED]: "error",
    [TASK_STATE_WAITING_AUTHORIZATION]: "awaiting_authorization",
    [TASK_STATE_RUNNING]: "pending",
    [TASK_STATE_PENDING]: "pending",
};

interface ResolvedStatus {
    status: string | null;
    valid: boolean;
}

const VALID_STATUS_VALUES = new Set<string>(["done", "error", "pending", "awaiting_authorization"]);

export function resolveTaskStatus(result: any): ResolvedStatus {
    if (!result) {
        return { status: null, valid: false };
    }

    const hasTaskState = result && typeof result.task_state === "string" && result.task_state.trim() !== "";
    const hasStatus = result && typeof result.status === "string" && result.status.trim() !== "";
    const taskState = hasTaskState ? result.task_state.trim() : null;
    const rawStatus = hasStatus ? result.status.trim() : null;

    if (!hasTaskState && !hasStatus) {
        return { status: null, valid: false };
    }

    if (!hasTaskState) {
        if (rawStatus && VALID_STATUS_VALUES.has(rawStatus)) {
            return { status: rawStatus, valid: true };
        }
        return { status: null, valid: false };
    }

    if (!TASK_STATE_VALUES.has(taskState)) {
        return { status: null, valid: false };
    }

    const expectedStatus = TASK_STATE_TO_STATUS[taskState];

    if (!hasStatus) {
        return { status: expectedStatus, valid: true };
    }

    if (rawStatus === expectedStatus) {
        return { status: rawStatus, valid: true };
    }

    if (taskState === TASK_STATE_COMPLETED && rawStatus === "completed") {
        return { status: "done", valid: true };
    }

    return { status: null, valid: false };
}

export interface TaskResultSuccess {
    version: string;
    task_id: string;
    type: string;
    task_state?: typeof TASK_STATE_COMPLETED | typeof TASK_STATE_WAITING_AUTHORIZATION;
    status: "done";
    result: {
        value?: any;
        [key: string]: any;
    };
    error: null;
    meta: {
        started_at: number;
        finished_at: number;
        worker_id: string;
        duration_ms: number;
    };
}

export interface TaskResultError {
    version: string;
    task_id: string;
    type: string;
    task_state?: typeof TASK_STATE_FAILED;
    status: "error";
    result: null;
    error: {
        message: string;
        code: string;
        stack: string | null;
        retryable: boolean;
    };
    meta: {
        started_at: number;
        finished_at: number;
        worker_id: string;
        duration_ms: number;
        retry_count: number;
    };
}

export interface TaskResultPending {
    status: "pending";
    message?: string;
}

export type TaskResult = TaskResultSuccess | TaskResultError;

export function isTaskSuccess(result: any): result is TaskResultSuccess {
    if (!result) return false;
    const resolved = resolveTaskStatus(result);
    return resolved.valid && resolved.status === "done";
}

export function isTaskError(result: any): result is TaskResultError {
    if (!result) return false;
    const resolved = resolveTaskStatus(result);
    return resolved.valid && resolved.status === "error";
}

export function isTaskPending(result: any): result is TaskResultPending {
    if (!result) return false;
    const resolved = resolveTaskStatus(result);
    return resolved.valid && resolved.status === "pending";
}

export function validateTaskResult(result: any): { valid: boolean; errors: string[] } {
    const errors: string[] = [];

    if (!result.task_id) errors.push("task_id missing");
    if (!result.status && !result.task_state) errors.push("both status and task_state missing");
    if (result.task_state && !["COMPLETED", "FAILED", "WAITING_AUTHORIZATION", "RUNNING", "PENDING"].includes(result.task_state)) {
        errors.push(`unknown task_state: ${result.task_state}`);
    }

    return { valid: errors.length === 0, errors };
}

export function getResultDescription(result: TaskResult | TaskResultPending): string {
    if (isTaskPending(result)) {
        return "任务处理中...";
    }

    if (isTaskSuccess(result)) {
        const value = result.result?.value ?? result.result;
        return `完成 | 结果: ${JSON.stringify(value)} | 耗时: ${result.meta.duration_ms}ms`;
    }

    if (isTaskError(result)) {
        return `失败 | 错误: ${result.error.message}`;
    }

    return "未知状态";
}