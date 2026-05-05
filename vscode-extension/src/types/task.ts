// src/types/task.ts
// TaskModel 类型定义

export type TaskStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';

export interface Task {
  id: string;
  type: string;
  prompt: string;
  status: TaskStatus;
  steps: Step[];
  events: TaskEvent[];
  result?: any;
  metadata?: {
    worker_id?: string;
    source?: string;
    [key: string]: any;
  };
  createdAt: number;
  updatedAt: number;
  startedAt?: number;
  completedAt?: number;
}

export interface Step {
  id: string;
  type: StepType;
  status: StepStatus;
  input: any;
  output?: any;
  error?: string;
  startTime?: number;
  endTime?: number;
  duration?: number;
}

export type StepType = 
  | 'analyze'
  | 'plan'
  | 'write'
  | 'refine'
  | 'test'
  | 'fix'
  | 'profile'
  | 'doc';

export type StepStatus = 'pending' | 'running' | 'completed' | 'failed' | 'skipped';

export interface TaskEvent {
  event: string;
  task_id: string;
  step_id?: string;
  data?: any;
  timestamp: number;
}

export interface TaskProgress {
  totalSteps: number;
  completedSteps: number;
  currentStep?: Step;
  percentage: number;
  status: TaskStatus;
}
