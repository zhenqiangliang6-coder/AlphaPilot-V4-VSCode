# AlphaPilot task protocol

`task-protocol-v1.schema.json` is the shared envelope contract for task submission and
execution. The Extension creates versioned submissions, the Node API validates and
normalizes them before queueing, and Workers reject unsupported explicit protocol
versions. The Qwen Worker is the first Worker adapter; other model workers currently
ignore these additive fields and remain on their legacy result envelopes. A missing
version remains accepted at the Node/Worker boundary for legacy clients; newly
submitted tasks are always emitted as protocol `1.0`.

`trace_id` is assigned by the Extension and propagated unchanged through the queue and
Worker result. `task_id` remains the server-owned lifecycle identifier.

The schema reserves explicit `awaiting_authorization` and authorization decision
states. This defines the wire shape; it does not claim that a resumable approval
workflow or post-approval test execution is implemented yet.
