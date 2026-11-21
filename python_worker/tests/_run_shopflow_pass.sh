#!/usr/bin/env bash
# ShopFlow 六轮 x 三遍验收驱动（主会话后台任务持有，避免子进程被代理生命周期带走）
# 用法: bash _run_shopflow_pass.sh <代数> <worker日志号> <node日志号>
set -u
# Windows 控制台默认 GBK，重定向日志写 emoji 会 UnicodeEncodeError（v60 首跑
# 7 errors 根因）。强制 Python 全链路 UTF-8 模式，worker 与 pytest 子进程均继承。
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8

V="${1:?version}"
WN="${2:?worker log no}"
NN="${3:?node log no}"

ROOT="D:/Copilot_Alphapilot/Copilot_Alphapilot"
TESTS="$ROOT/python_worker/tests"
PY="$ROOT/.venv_worker/Scripts/python.exe"
SUM="$TESTS/shopflow_v${V}_summary.txt"
PROG="$TESTS/g1042_progress.log"
NODE_LOG="$TESTS/node_api_run${NN}.log"
WORKER_LOG="$TESTS/worker_run${WN}.log"
SPEC="python_worker/tests/test_observe_task_system.py::TestShopFlowProductionPath"

echo "v${V} start $(date '+%Y-%m-%d %H:%M:%S')" > "$SUM"
echo "" >> "$PROG"
echo "=== v${V} START $(date '+%Y-%m-%d %H:%M:%S') | worker_run${WN} / node_api_run${NN} ===" >> "$PROG"

# 只允许加载新代码的全新实例：按 3000 端口 + qwen_worker_v2 命令行精确清理旧实例
cleanup_instances() {
  local p pids
  pids=$(netstat -ano 2>/dev/null | grep -a ":3000 " | grep -a LISTENING | awk '{print $NF}' | sort -u)
  for p in $pids; do taskkill //F //PID "$p" >/dev/null 2>&1; done
  # worker 是 Windows 原生进程，MSYS 的 ps -ef 看不到；改用 PowerShell 匹配命令行
  pids=$(powershell.exe -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='python.exe'\" | Where-Object CommandLine -match 'qwen_worker_v2' | Select-Object -ExpandProperty ProcessId" 2>/dev/null | tr -d '\r' | grep -oE '[0-9]+' | sort -u)
  for p in $pids; do taskkill //F //PID "$p" >/dev/null 2>&1; done
}
cleanup_instances

# 清空临时会话记忆：验收不走 start_all.ps1，.temp_memory 会跨轮累积历史对话，
# 污染 R5「从零开始」的上下文（v62 第 2 遍实证 source=temp 注入 11-14/11-15
# 的 4 条旧对话）。这是判卷基础设施隔离修复，不碰生产守卫语义。
rm -rf "$ROOT/.temp_memory"

cd "$ROOT/node-api" || exit 2
node index.js > "$NODE_LOG" 2>&1 &
NODE_PID=$!
cd "$ROOT/python_worker" || exit 2
PYTHONPATH="$ROOT" "$PY" -u -m python_worker.agents.qwen.qwen_worker_v2 > "$WORKER_LOG" 2>&1 &
WORKER_PID=$!
cd "$ROOT" || exit 2

# 等两个服务就绪（有限次数，不做失败重试循环）
READY=0
for k in $(seq 1 60); do
  if grep -aq "AlphaPilot Node API" "$NODE_LOG" 2>/dev/null && \
     grep -aq "Qwen Worker v3.0" "$WORKER_LOG" 2>/dev/null && \
     netstat -ano 2>/dev/null | grep -aq ":3000 .*LISTENING"; then
    READY=1
    break
  fi
  sleep 2
done
echo "READY=$READY node_pid=$NODE_PID worker_pid=$WORKER_PID at $(date '+%H:%M:%S')" >> "$PROG"
if [ "$READY" -ne 1 ]; then
  echo "ABORT: instances not ready" >> "$SUM"
  echo "ABORT: instances not ready" >> "$PROG"
  cleanup_instances
  exit 0
fi

for i in 1 2; do
  LOG="$TESTS/shopflow_v${V}_${i}.log"
  echo "--- v${V} pass ${i} START $(date '+%Y-%m-%d %H:%M:%S') ---" >> "$PROG"
  "$PY" -u -m pytest "$SPEC" -v -s > "$LOG" 2>&1
  rc=$?
  echo "pass ${i} rc=${rc} at $(date '+%Y-%m-%d %H:%M:%S')" >> "$SUM"
  LAST=$(grep -aE "passed|failed|error" "$LOG" 2>/dev/null | tail -1)
  echo "--- v${V} pass ${i} END rc=${rc} | ${LAST} ---" >> "$PROG"
  if [ "$rc" -ne 0 ]; then
    echo "STOP: pass ${i} failed, not burning remaining passes" >> "$SUM"
    break
  fi
done
echo "DONE" >> "$SUM"
echo "=== v${V} DONE $(date '+%Y-%m-%d %H:%M:%S') ===" >> "$PROG"

cleanup_instances
exit 0