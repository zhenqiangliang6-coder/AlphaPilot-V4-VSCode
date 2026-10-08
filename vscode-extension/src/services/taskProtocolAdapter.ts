import { randomUUID } from 'crypto';
import {
  TASK_PROTOCOL_VERSION,
  TaskSubmission,
  TaskSubmissionResponse
} from '../types/taskContract';

export interface TaskSubmissionOptions {
  collaboration_mode?: string;
  context?: Record<string, unknown>;
  workspace_path?: string;
  source?: string;
}

export class TaskProtocolAdapter {
  createSubmission(type: string, prompt: string, options: TaskSubmissionOptions = {}): TaskSubmission {
    return {
      protocol_version: TASK_PROTOCOL_VERSION,
      trace_id: randomUUID(),
      type,
      payload: {
        prompt,
        ...(options.collaboration_mode
          ? { collaboration_mode: options.collaboration_mode }
          : {}),
        ...(options.context ? { context: options.context } : {}),
        ...(options.workspace_path ? { workspace_path: options.workspace_path } : {})
      },
      source: options.source || 'vscode-extension'
    };
  }

  adaptSubmissionResponse(response: unknown, expectedTraceId: string): TaskSubmissionResponse {
    if (!response || typeof response !== 'object' || Array.isArray(response)) {
      throw new Error('Node API returned a non-object task response');
    }

    const data = response as Record<string, unknown>;
    if (data.status !== 'submitted' || typeof data.task_id !== 'string' || !data.task_id) {
      throw new Error('Node API returned an invalid task submission response');
    }
    if (
      data.protocol_version !== undefined &&
      data.protocol_version !== TASK_PROTOCOL_VERSION
    ) {
      throw new Error(`Unsupported response protocol version: ${String(data.protocol_version)}`);
    }
    if (data.trace_id !== undefined && data.trace_id !== expectedTraceId) {
      throw new Error('Node API response trace_id does not match the submitted task');
    }

    return {
      status: 'submitted',
      task_id: data.task_id,
      ...(typeof data.protocol_version === 'string'
        ? { protocol_version: TASK_PROTOCOL_VERSION }
        : {}),
      ...(typeof data.trace_id === 'string' ? { trace_id: data.trace_id } : {}),
      ...(typeof data.model === 'string' ? { model: data.model } : {}),
      ...(typeof data.stream === 'boolean' ? { stream: data.stream } : {}),
      ...(typeof data.message === 'string' ? { message: data.message } : {})
    };
  }
}

export const taskProtocolAdapter = new TaskProtocolAdapter();
