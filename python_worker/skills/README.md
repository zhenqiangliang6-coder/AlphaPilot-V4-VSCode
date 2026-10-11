# Worker Skills

Skills are trusted, local Python modules discovered by `skills.router`. Each module
exports `register(registry)` and registers one versioned `Skill` containing a stable
ID, semantic version, routing triggers, supported capabilities, and execution
guidance. The registry supports runtime registration/removal and an explicit
`reload_skills()` operation; module reload executes trusted Python code and is not a
security sandbox.

Built-in skills are deliberately advisory:

### Domain Skills (v3.x)
- `frontend.ui`: VS Code Extension, TypeScript, React, and Webview work.
- `backend.python`: AlphaPilot Python Worker and backend API work.
- `dependency.manager`: manifest/lockfile review and dependency-change proposals.
- `workspace.file-deletion`: targeted file deletion with safety checks.
- `test.automation`: Pytest/gtest/Jest test suite generation.
- `database.sql`: SQL queries, schema design, migration scripts.
- `docker.container`: Dockerfile and Docker Compose work.
- `api.rest`: REST API endpoint design and OpenAPI specs.
- `infra.cicd`: GitHub Actions, GitLab CI, ArgoCD pipelines.

### V4.0 Creative & Vision Skills
- `creative.pure-text`: 纯文本创作（诗、文章、方案说明），极简链 [analyze, write]
- `creative.document-proposal`: 招商方案/商业文档创作
- `creative.brand-content`: 品牌文案/社交媒体内容创作
- `vision.image-analysis`: 图片分析（需 vision-capable LLM）

### V4.0 Diagnosis Skill
- `diagnosis.runtime-error` (priority=90): 运行时错误诊断与最小化修复。处理端口冲突、权限错误、配置/环境变量问题。**严禁修改无关业务逻辑**。覆盖 `backend.python` (60) 的默认 guidance。

### V4.0 Output Profile 合约

v4.0 Skill 携带 `output_profile` 作为能力合约，优先级高于意图默认 profile：

```
Skill.output_profile > 意图默认 profile > 兜底 code 模式
```

profile 字段: `output_mode`, `workspace_dependency`, `requires_fileops`, `requires_workspace_scan`, `requires_test`

Skills do not write files, run commands, install packages, access the network, or
grant permissions. Those effects remain unavailable until a host capability and
user-approval flow are implemented. Add new modules under this package and export
`register(registry)`; duplicate IDs and invalid versions fail during registration.