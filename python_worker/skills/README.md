# Worker Skills

Skills are trusted, local Python modules discovered by `skills.router`. Each module
exports `register(registry)` and registers one versioned `Skill` containing a stable
ID, semantic version, routing triggers, supported capabilities, and execution
guidance. The registry supports runtime registration/removal and an explicit
`reload_skills()` operation; module reload executes trusted Python code and is not a
security sandbox.

Built-in skills are deliberately advisory:

- `frontend.ui`: VS Code Extension, TypeScript, React, and Webview work.
- `backend.python`: AlphaPilot Python Worker and backend API work.
- `dependency.manager`: manifest/lockfile review and dependency-change proposals.

Skills do not write files, run commands, install packages, access the network, or
grant permissions. Those effects remain unavailable until a host capability and
user-approval flow are implemented. Add new modules under this package and export
`register(registry)`; duplicate IDs and invalid versions fail during registration.
