export const MAX_REPAIR_ROUNDS = 3;
export const TEST_COMMAND_TIMEOUT_MS = 15 * 60 * 1000;

export interface TestRunEvidence {
  command: string;
  exitCode: number | null;
  stdout: string;
  stderr: string;
  timedOut: boolean;
  repairRounds: number;
  changedAfterTest: boolean;
}

export interface StopDecision {
  complete: boolean;
  reasons: string[];
}

const TEST_COMMAND_PREFIX = /^(?:pytest|python(?:\.exe)?\s+-m\s+(?:pytest|unittest)|py\s+-m\s+(?:pytest|unittest)|npm\s+(?:test|run\s+test)|node(?:\.exe)?\s+--test|dotnet\s+test|go\s+test|cargo\s+test|mvn\s+test|gradle\s+test)(?:\s|$)/i;
const SAFE_TEST_COMMAND_CHARACTERS = /^[A-Za-z0-9_./:=+\-\s]+$/;

export function isAllowedTestCommand(command: string): boolean {
  const normalized = command.trim();
  return TEST_COMMAND_PREFIX.test(normalized) && SAFE_TEST_COMMAND_CHARACTERS.test(normalized);
}

export function evaluateStopHook(evidence: TestRunEvidence): StopDecision {
  const reasons: string[] = [];
  if (!isAllowedTestCommand(evidence.command)) reasons.push('测试命令不在允许的测试命令范围内');
  if (evidence.timedOut) reasons.push('测试命令超时');
  if (evidence.exitCode !== 0) reasons.push(`测试退出码不是 0（${String(evidence.exitCode)}）`);
  if (/\b(?:FAILED|ERROR)\b/i.test(`${evidence.stdout}\n${evidence.stderr}`)) {
    reasons.push('测试输出包含 FAILED 或 ERROR');
  }
  if (evidence.changedAfterTest) reasons.push('测试后检测到源文件继续变化');
  if (evidence.repairRounds > MAX_REPAIR_ROUNDS) reasons.push('超过最大自动修复轮次');
  return { complete: reasons.length === 0, reasons };
}

export function buildSummaryHookPrompt(input: {
  goal: string;
  changedFiles: string[];
  evidence: TestRunEvidence;
  remainingIssues: string[];
}): string {
  return [
    '你是 AlphaPilot 的结项报告钩子。仅依据下列结构化证据写报告，不得补造测试、文件改动或成功状态。',
    '必须包含：本次任务目标、修改/新增文件及每个文件的改动、运行的测试命令、测试通过情况、遗留问题、下一步建议。',
    '如果文件仅由模型提出而未应用，必须标记为“提议/未应用”，不得写成已修改。',
    `任务目标：${input.goal || '未提供'}`,
    `已应用文件：${JSON.stringify(input.changedFiles)}`,
    `测试证据：${JSON.stringify(input.evidence)}`,
    `遗留事项：${JSON.stringify(input.remainingIssues)}`,
  ].join('\n\n');
}
