export type TaskStatus = "pending" | "done" | "error";

export interface TaskResultSuccess {
    version: string;
    task_id: string;
    type: string;
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
    return result && result.status === "done";
}

export function isTaskError(result: any): result is TaskResultError {
    return result && result.status === "error";
}

export function isTaskPending(result: any): result is TaskResultPending {
    return result && result.status === "pending";
}

export function validateTaskResult(result: any): { valid: boolean; errors: string[] } {
    const errors: string[] = [];

    if (!result.task_id) errors.push("task_id missing");
    if (!result.status) errors.push("status missing");

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
