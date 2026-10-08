# MaaS and ModelScope Setup

## API Key Check

The configured credentials and default models were tested on 2026-09-29. ModelScope (`Qwen/Qwen3.8-Flash-Next`) and Tencent MaaS (`hy4-preview`) both returned HTTP 200.

Run the check from PowerShell:

```powershell
& 'D:\Copilot_Alphapilot\.venv_worker\Scripts\python.exe' `
  'D:\Copilot_Alphapilot\Copilot_Alphapilot\python_worker\test_api_keys.py'
```

The script reads `python_worker/.env`, makes short completion requests, and does not print API keys or raw error bodies. It checks the configured ModelScope model first, then the reference models if needed.

## ModelScope Long-Request Recovery

ModelScope uses a 10-second connection timeout and a 600-second read timeout by default. Transient connection/read failures and HTTP 500, 502, 503, or 504 responses are retried up to three times with exponential backoff. Override these values with `MODELSCOPE_CONNECT_TIMEOUT_SECONDS`, `MODELSCOPE_READ_TIMEOUT_SECONDS`, `MODELSCOPE_MAX_RETRIES`, and `MODELSCOPE_RETRY_BACKOFF_SECONDS` in `python_worker/.env`.

The ModelScope worker stores progress in its configured Redis under a task-specific key. Completed steps are checkpointed, and the `docstring` step also checkpoints each successfully processed Python file. A redelivered task resumes from the latest checkpoint only when it retains the same `task_id`. Checkpoints expire after seven days by default (`MODELSCOPE_CHECKPOINT_TTL_SECONDS`).

The worker writes failed tasks to the dead-letter queue but does not automatically requeue them. Resumption therefore requires the existing DLQ/retry flow to redeliver the original task with its original `task_id`. For streaming calls, a read failure before the first content chunk is retried transparently; after content has been emitted, the error is surfaced rather than restarting the stream and duplicating output.

## Start Local Redis

The root `docker-compose.yml` now provides `alphapilot-local-redis` on `127.0.0.1:6379`, with AOF persistence in the `redis_data` Docker volume. Start just Redis:

```powershell
$env:DB_PASSWORD = 'compose-validation-only'
docker compose -f 'D:\Copilot_Alphapilot\docker-compose.yml' up -d redis
Remove-Item Env:DB_PASSWORD
docker exec alphapilot-local-redis redis-cli ping
```

`DB_PASSWORD` is required by the existing PostgreSQL service during Compose interpolation, even when only the Redis service is selected. The temporary value above is not saved; do not use it to start PostgreSQL. If your environment already supplies the real database password, keep that value instead.

The project `.env` at `python_worker/.env` should contain:

```dotenv
REDIS_TYPE=auto
LOCAL_REDIS_MODELS=maas,modelscope
REDIS_HOST=127.0.0.1
REDIS_PORT=6379
```

Both Node API and Python workers read this file. `start_all.ps1` starts local Redis and launches `maas-worker-1` and `modelscope-worker-1` alongside the existing workers. Choose either new model in the AlphaPilot panel after restarting the extension.

## Compare Local and Cloud Redis

By default, only MaaS and ModelScope use Docker Redis. Other models retain their existing routes. To compare cloud Redis, clear the model list and restart Node API and workers:

```dotenv
LOCAL_REDIS_MODELS=
REDIS_TYPE=auto
```

In `auto` mode, MaaS uses Tair and ModelScope uses Upstash. To send all models to the local Redis instead, set `REDIS_TYPE=local`; to force a cloud provider globally, use `REDIS_TYPE=tair` or `REDIS_TYPE=upstash`.

`USE_MEMORY_REDIS=true` is a separate in-process simulator in each Python worker. It is useful for isolated worker debugging, but it is not shared with Node API and cannot validate the end-to-end task queue. Use Docker Redis for panel-to-worker tests.

## Troubleshooting

- Check container health with `docker ps --filter name=alphapilot-local-redis`.
- Check the Redis service with `docker exec alphapilot-local-redis redis-cli ping`; expected output is `PONG`.
- Confirm both Node API and workers were restarted after changing `python_worker/.env`.
- Check that the local worker environment has the `redis` package installed (`python_worker/worker_requirements.txt` already declares it).
- Confirm MaaS uses `TENCENT_MAAS_API_KEY`, `TENCENT_MAAS_BASE_URL`, and `TENCENT_MAAS_MODEL`; ModelScope uses `MODELSCOPE_API_KEY`, `MODELSCOPE_BASE_URL`, and `MODELSCOPE_MODEL`.
- HTTP 401/403 indicates an authentication or permission issue; HTTP 429 indicates quota/rate limiting; HTTP 404 usually means an endpoint or model name mismatch.

## Credential Safety

Keep real `.env` files out of source control and never copy keys into reports. Credentials included in the conversation should be rotated at their providers.