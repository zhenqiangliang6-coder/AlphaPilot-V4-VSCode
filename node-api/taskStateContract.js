const TASK_STATE_PENDING = 'PENDING';
const TASK_STATE_RUNNING = 'RUNNING';
const TASK_STATE_COMPLETED = 'COMPLETED';
const TASK_STATE_FAILED = 'FAILED';
const TASK_STATE_WAITING_AUTHORIZATION = 'WAITING_AUTHORIZATION';

const TASK_STATE_VALUES = new Set([
  TASK_STATE_PENDING,
  TASK_STATE_RUNNING,
  TASK_STATE_COMPLETED,
  TASK_STATE_FAILED,
  TASK_STATE_WAITING_AUTHORIZATION,
]);

const TASK_STATE_TO_STATUS = {
  [TASK_STATE_COMPLETED]: 'done',
  [TASK_STATE_FAILED]: 'error',
  [TASK_STATE_WAITING_AUTHORIZATION]: 'awaiting_authorization',
  [TASK_STATE_RUNNING]: 'pending',
  [TASK_STATE_PENDING]: 'pending',
};

const TERMINAL_TASK_STATES = new Set([
  TASK_STATE_COMPLETED,
  TASK_STATE_FAILED,
  TASK_STATE_WAITING_AUTHORIZATION,
]);

function resolveStatus(result) {
  const violations = [];
  const warnings = [];
  const hasTaskState = result && typeof result.task_state === 'string' && result.task_state.trim() !== '';
  const hasStatus = result && typeof result.status === 'string' && result.status.trim() !== '';
  const taskState = hasTaskState ? result.task_state.trim() : null;
  const rawStatus = hasStatus ? result.status.trim() : null;

  if (!hasTaskState && !hasStatus) {
    violations.push({
      field: 'task_state|status',
      message: 'Both task_state and status are missing; cannot determine task outcome',
    });
    return { status: null, valid: false, violations, warnings };
  }

  if (!hasTaskState) {
    const mappedState = Object.entries(TASK_STATE_TO_STATUS).find(
      ([, s]) => s === rawStatus
    );
    if (mappedState) {
      warnings.push({
        field: 'task_state',
        message: `task_state missing; inferred from status: ${mappedState[0]}`,
      });
      return {
        status: rawStatus,
        valid: true,
        violations,
        warnings,
      };
    }
    violations.push({
      field: 'status',
      message: `Unknown status value '${rawStatus}' without task_state`,
    });
    return { status: null, valid: false, violations, warnings };
  }

  if (!TASK_STATE_VALUES.has(taskState)) {
    violations.push({
      field: 'task_state',
      message: `Unknown task_state value: '${taskState}'`,
    });
    return { status: null, valid: false, violations, warnings };
  }

  const expectedStatus = TASK_STATE_TO_STATUS[taskState];

  if (!hasStatus) {
    warnings.push({
      field: 'status',
      message: `status missing; derived from task_state: '${taskState}' → '${expectedStatus}'`,
    });
    return { status: expectedStatus, valid: true, violations, warnings };
  }

  if (rawStatus === expectedStatus) {
    return { status: rawStatus, valid: true, violations, warnings };
  }

  if (taskState === TASK_STATE_COMPLETED && rawStatus === 'completed') {
    warnings.push({
      field: 'status',
      message: "status 'completed' accepted as compatibility alias for task_state COMPLETED",
    });
    return { status: 'done', valid: true, violations, warnings };
  }

  violations.push({
    field: 'status',
    message: `task_state '${taskState}' maps to status '${expectedStatus}', but status is '${rawStatus}'`,
  });
  return { status: null, valid: false, violations, warnings };
}

module.exports = {
  TASK_STATE_PENDING,
  TASK_STATE_RUNNING,
  TASK_STATE_COMPLETED,
  TASK_STATE_FAILED,
  TASK_STATE_WAITING_AUTHORIZATION,
  TASK_STATE_VALUES,
  TASK_STATE_TO_STATUS,
  TERMINAL_TASK_STATES,
  resolveStatus,
};