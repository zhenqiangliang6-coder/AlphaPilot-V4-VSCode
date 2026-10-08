export const TASK_PROTOCOL_VERSION = '1.0' as const;

export type ProtocolTaskStatus =
  | 'pending'
  | 'running'
  | 'awaiting_authorization'
  | 'completed'
  | 'done'
  | 'failed'
  | 'error'
  | 'cancelled';

export type AuthorizationStatus = 'pending' | 'approved' | 'denied' | 'expired';

export interface TaskAuthorization {
  request_id: string;
  status: AuthorizationStatus;
  actions: Array<Record<string, unknown>>;
  decision_id?: string;
  decided_at?: string;
}

export interface TaskSubmission {
  protocol_version: typeof TASK_PROTOCOL_VERSION;
  trace_id: string;
  type: string;
  payload: {
    prompt: string;
    collaboration_mode?: string;
    context?: Record<string, unknown>;
    workspace_path?: string;
  };
  source: string;
}

export interface TaskSubmissionResponse {
  status: 'submitted';
  task_id: string;
  trace_id?: string;
  protocol_version?: typeof TASK_PROTOCOL_VERSION;
  model?: string;
  stream?: boolean;
  message?: string;
}
