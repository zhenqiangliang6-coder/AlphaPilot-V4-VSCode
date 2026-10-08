"""Provider-neutral docstring generation for workers with an injected model call."""

from .file_ops import create_file_op, filter_valid_file_ops, get_python_files
from .worker_config import create_event


def run_docstring_step(step, context, events, task_id=None):
    file_ops = context.get("final_file_ops") or context.get("file_ops") or []
    python_files = get_python_files(filter_valid_file_ops(file_ops))
    if not python_files:
        step["output"] = {"text": "docstring：未找到可处理的 Python 文件。"}
        return

    provider_call = context.get("_respond_call")
    if not callable(provider_call):
        raise RuntimeError("当前 Worker 未配置 docstring 模型适配器")

    from .agents.qwen.step_executor.prompts import docstring_prompt
    from .agents.qwen.step_executor.utils import extract_code

    persona_config = context.get("meta", {}).get("persona_config")
    documented = {}
    failures = []
    for file_op in python_files:
        path = file_op["path"]
        content = file_op.get("content", "")
        if not content:
            continue
        try:
            response = provider_call(docstring_prompt(content), persona_config, None)
            if not isinstance(response, str):
                response = "".join(response)
            code = extract_code(response, fallback_strategies=True)
            if not code:
                raise ValueError("模型未返回可识别的 Python 代码")
            compile(code, path, "exec")
            documented[path] = code
        except Exception as error:
            failures.append({"path": path, "error": str(error)})

    updated_ops = []
    matched_paths = set()
    for operation in file_ops:
        updated = dict(operation)
        path = updated.get("path")
        if path in documented:
            updated["content"] = documented[path]
            updated["from_step"] = "docstring"
            matched_paths.add(path)
        updated_ops.append(updated)
    for path, content in documented.items():
        if path not in matched_paths:
            updated_ops.append(create_file_op(
                "modify",
                path,
                content,
                reason="更新 docstring",
                from_step="docstring",
                intent=context.get("meta", {}).get("intent", ""),
            ))

    if documented:
        context["final_file_ops"] = updated_ops
        context["file_ops"] = updated_ops
    summary = f"已生成 {len(documented)} 个待确认的 docstring 修改。"
    if failures:
        summary += "\n未加入修改的文件：\n" + "\n".join(
            f"- {item['path']}: {item['error']}" for item in failures
        )
    step["output"] = {"text": summary, "documented_files": list(documented)}
    events.append(create_event("docstring_output", {
        "documented_files": list(documented),
        "failed_files": failures,
    }))
