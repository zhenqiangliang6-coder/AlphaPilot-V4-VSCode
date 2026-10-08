"""Run explicitly requested Python checks and project-environment operations."""

from ....worker_config import create_event, stream_chunk, stream_end, stream_start
from ....workspace_tools import detect_environment_requests, setup_python_environment


def run_workspace_step(step, context, events, task_id=None):
    import os as _os
    meta = context.get("meta", {})
    scan = meta.get("workspace_scan", {})
    request = meta.get("user_request", "")
    environment_request = detect_environment_requests(request)
    operations = []

    workspace_root = scan.get("root") or meta.get("workspace_path")
    if workspace_root and not _os.path.isdir(_os.path.join(workspace_root, ".venv")):
        environment_request["create_venv"] = True
        environment_request["install_dependencies"] = True

    def report(message):
        if "扫描完成" in message:
            status = "项目扫描完成，正在准备检查…"
        elif "创建虚拟环境" in message:
            status = "正在创建 Python 虚拟环境…"
        elif "复用现有虚拟环境" in message:
            status = "正在复用 Python 虚拟环境…"
        elif "安装" in message and "依赖" in message:
            status = "正在安装项目依赖…"
        elif "失败" in message:
            status = "项目环境操作遇到问题…"
        else:
            status = "正在检查项目环境…"
        print(f"[WORKSPACE_TOOL] {status}")
        if task_id:
            stream_chunk(task_id, status, phase="workspace", channel="tool")

    if task_id:
        stream_start(task_id, "🧰 正在执行项目检查与环境工具...", phase="workspace")

    report(
        f"Python 源文件扫描完成：{scan.get('python_file_count', 0)} 个文件，"
        f"{scan.get('fixable_issue_count', 0)} 个语法/缩进问题，"
        f"{len(scan.get('issues', []))} 个扫描问题。"
    )

    try:
        operations = setup_python_environment(
            workspace_path=scan.get("root") or meta.get("workspace_path"),
            venv_name=environment_request["venv_name"],
            create_venv=environment_request["create_venv"],
            install_dependencies=environment_request["install_dependencies"],
            progress=report,
            inferred_dependencies=scan.get("inferred_dependencies", []),
        )
    except (OSError, RuntimeError, ValueError) as error:
        operations.append({
            "name": "python_environment",
            "status": "failed",
            "stderr": str(error),
        })
        report(f"环境操作失败：{error}")

    failures = [operation for operation in operations if operation.get("status") == "failed"]
    skipped = [operation for operation in operations if operation.get("status") == "skipped"]
    issue_count = scan.get("fixable_issue_count", 0)
    repaired_paths = {
        operation.get("path")
        for operation in context.get("final_file_ops", [])
        if operation.get("from_step") == "fix"
    }
    repaired = len(repaired_paths)
    summary = (
        f"项目检查完成：扫描 {scan.get('python_file_count', 0)} 个 Python 文件，"
        f"发现 {issue_count} 个语法/缩进问题；生成 {repaired} 个代码修改提案。"
    )
    if repaired_paths:
        shown_paths = sorted(repaired_paths)
        summary += "\n修复文件：" + "、".join(shown_paths[:8])
        if len(shown_paths) > 8:
            summary += f" 等 {len(shown_paths)} 个文件"
    if environment_request["install_dependencies"]:
        installed_package_map = {
            package.casefold(): package
            for operation in operations
            if operation.get("name") in {
                "install_dependencies",
                "install_inferred_dependencies",
            }
            and operation.get("status") == "completed"
            for package in operation.get("installed_packages", [])
        }
        installed_packages = sorted(installed_package_map.values(), key=str.casefold)
        summary += f" 已安装 {len(installed_packages)} 个依赖包。"
    else:
        installed_packages = []
    if failures:
        summary += f" 环境操作有 {len(failures)} 项失败，请查看任务步骤详情。"
    if skipped and environment_request["install_dependencies"]:
        summary += " 依赖安装已跳过。"

    incomplete_scan = any(
        issue.get("kind") in {"read_error", "skipped_large_file"}
        for issue in scan.get("issues", [])
    )
    issue_paths = {
        issue.get("path")
        for issue in scan.get("issues", [])
        if issue.get("kind") in {"syntax", "indentation"}
    }
    incomplete_repairs = bool(issue_paths - repaired_paths)
    tool_result = {
        "tool": "workspace.python_maintenance",
        "status": (
            "partial"
            if failures
            or scan.get("scan_errors")
            or scan.get("file_limit_reached")
            or incomplete_scan
            or incomplete_repairs
            else "completed"
        ),
        "python_file_count": scan.get("python_file_count", 0),
        "installed_package_count": len(installed_packages),
        "installed_packages": installed_packages,
        "issues": scan.get("issues", []),
        "operations": operations,
    }
    context.setdefault("tool_outputs", []).append(tool_result)
    events.append(create_event("tool_completed", tool_result))
    step["output"] = {
        "text": summary,
        "tool_result": tool_result,
    }
    context.setdefault("intermediate_results", []).append({
        "type": "workspace",
        "tool_result": tool_result,
    })

    if task_id:
        stream_end(task_id)