# AlphaPilot Automatic Task Routing

The chat UI asks only for the user's task. The Worker owns intent, persona, and execution-chain selection; `payload.collaboration_mode` is omitted by the current webview. Older clients may still send an explicit mode for compatibility. Missing or invalid modes resolve to automatic routing, not blanket engineer permissions.

The shared `IntentRouter` is the sole source of intent-to-chain decisions across workers. Chains are selected per intent and adapted only where a worker lacks a capability. Optional documentation, docstring, and profiling steps are appended only when requested; the full engineering sequence is not the default for every task.

Automatic mode maps explanations and ordinary chat to read-only teaching behavior, code review to read-only reviewer behavior, creative requests to creative behavior, and requested code changes to engineering behavior. Compound "explain and fix" requests keep both diagnosis and repair in the same plan. Unknown requests use a safe conversational route rather than assuming permission to modify files.

Modes are injected into the Worker persona and step prompts, but prompts are not treated as a write-safety boundary. Before a task result is persisted, the Worker clears `final_file_ops` and `file_ops` for read-only modes. The VS Code extension independently refuses writes for read-only modes and requires an explicit confirmation for every proposed file operation, including create/modify and delete. This review is the authorization boundary for the displayed paths and operation scope.

Workspace-wide Python syntax/indentation checks and Python environment setup use a dedicated Qwen Worker tool path. It scans real `.py` files (excluding generated and virtual-environment directories), supplies only diagnosed source files to the repair step, creates or reuses the requested `.venv`/`.vnev`, and installs dependencies only from a project manifest. Each operation reports its command, exit code, output, and status in the task result; missing manifests are reported rather than guessed. Other Workers must not claim this capability when it is unavailable.

The VS Code extension writes progress and actual command outcomes to the `AlphaPilot Execution` output channel. Project tests and other gated validation steps remain behind Worker authorization checks; generated FileOps are never applied solely because the Worker selected the engineering persona.

Focused routing and policy tests: `python -m pytest tests/test_intent_router.py tests/test_collaboration_modes.py tests/test_workspace_task_flow.py -q` from `python_worker/`.