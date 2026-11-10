# -*- coding: utf-8 -*-
"""
Phase 2.1 任务上下文契约层

纯定义与校验模块，不修改生产执行代码。定义：
- ProjectMode / CompatibilityPolicy 枚举
- AllowedPaths / ConfirmationScope / UserConfirmation 数据结构
- TaskContext 不可变数据类
- 显式异常类型（无 assert，全使用结构化异常）
- 校验顺序：结构 → 类型 → 枚举 → 路径归属 → 模式分支
- context_hash 计算规则
- 兼容模式构建（compat_readonly：仅允许读取，无写入和执行）

唯一 Schema 来源: contracts/task-protocol-v1.schema.json
"""

import hashlib
import json
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple


# ================================================================
# 1. 枚举
# ================================================================

class ProjectMode(str, Enum):
    CREATE_NEW_PROJECT = "create_new_project"
    MODIFY_EXISTING_PROJECT = "modify_existing_project"


class CompatibilityPolicy(str, Enum):
    STRICT = "strict"
    COMPAT_READONLY = "compat_readonly"
    NONE = "none"


VALID_MODES: Set[str] = {m.value for m in ProjectMode}
VALID_POLICIES: Set[str] = {p.value for p in CompatibilityPolicy}


# ================================================================
# 2. 显式异常类型（不使用 assert）
# ================================================================

class TaskContextValidationError(Exception):
    """task_context 结构或语义校验失败（类比 HTTP 400）。"""
    def __init__(self, message: str, reason_code: str, field: str = ""):
        super().__init__(message)
        self.reason_code = reason_code
        self.field = field


class AuthorizationDenied(Exception):
    """PathGuard 拒绝操作（类比 HTTP 403）。"""
    def __init__(self, message: str, reason_code: str, audit_record: Optional[dict] = None):
        super().__init__(message)
        self.reason_code = reason_code
        self.audit_record = audit_record or {}


class ConfirmationRequired(Exception):
    """需要用户确认后才能继续（类比 HTTP 401）。"""
    def __init__(self, message: str, confirmation_scope: "ConfirmationScope"):
        super().__init__(message)
        self.confirmation_scope = confirmation_scope


class UnsupportedProtocolVersion(Exception):
    """协议版本不支持。"""
    def __init__(self, message: str, version: str):
        super().__init__(message)
        self.version = version


class TargetPathConflict(Exception):
    """create_new_project 时目标路径已存在（类比 HTTP 409）。"""
    def __init__(self, message: str, target_path: str, existing_type: str = ""):
        super().__init__(message)
        self.target_path = target_path
        self.existing_type = existing_type


class TargetParentNotAuthorized(Exception):
    """目标父目录不在授权范围内（类比 HTTP 403）。"""
    def __init__(self, message: str, target_path: str, parent_path: str):
        super().__init__(message)
        self.target_path = target_path
        self.parent_path = parent_path


# ================================================================
# 3. 数据结构（不可变 dataclass）
# ================================================================

@dataclass(frozen=True)
class AllowedPaths:
    """六种操作能力映射到三个路径域。
    read  → read
    write → write (create/overwrite file content)
    create_dir → write + 父目录检查
    delete → write + 独立确认
    move   → write (源和目标两端均需授权)
    execute → execute (不授予文件写入权限)
    """
    read: List[str]
    write: List[str]
    execute: List[str]

    def to_dict(self) -> dict:
        return {
            "read": list(self.read),
            "write": list(self.write),
            "execute": list(self.execute),
        }

    @staticmethod
    def from_dict(data: dict) -> "AllowedPaths":
        if not isinstance(data, dict):
            raise TaskContextValidationError(
                "allowed_paths must be a dict",
                reason_code="INVALID_TYPE",
                field="allowed_paths",
            )
        read = data.get("read", [])
        write = data.get("write", [])
        execute = data.get("execute", [])
        if not isinstance(read, list) or not isinstance(write, list) or not isinstance(execute, list):
            raise TaskContextValidationError(
                "allowed_paths.read/write/execute must be arrays",
                reason_code="INVALID_TYPE",
                field="allowed_paths",
            )
        if len(read) == 0:
            raise TaskContextValidationError(
                "allowed_paths.read must have at least one path",
                reason_code="MISSING_REQUIRED",
                field="allowed_paths.read",
            )
        return AllowedPaths(read=list(read), write=list(write), execute=list(execute))


@dataclass(frozen=True)
class ConfirmationScope:
    """用户确认了什么操作、在什么路径上、影响范围多大。"""
    target_project_path: str
    project_mode: str
    allowed_paths: AllowedPaths
    estimated_impact: str
    operation_specific: Optional[dict] = None

    def to_dict(self) -> dict:
        result: dict = {
            "target_project_path": self.target_project_path,
            "project_mode": self.project_mode,
            "allowed_paths": self.allowed_paths.to_dict(),
            "estimated_impact": self.estimated_impact,
        }
        if self.operation_specific:
            result["operation_specific"] = self.operation_specific
        return result

    @staticmethod
    def from_dict(data: dict) -> "ConfirmationScope":
        if not isinstance(data, dict):
            raise TaskContextValidationError(
                "confirmation_scope must be a dict",
                reason_code="INVALID_TYPE",
                field="confirmation_scope",
            )
        target = data.get("target_project_path", "")
        mode = data.get("project_mode", "")
        impact = data.get("estimated_impact", "")
        if not target:
            raise TaskContextValidationError(
                "confirmation_scope.target_project_path is required",
                reason_code="MISSING_REQUIRED",
                field="confirmation_scope.target_project_path",
            )
        if mode not in VALID_MODES:
            raise TaskContextValidationError(
                f"Invalid project_mode in confirmation_scope: {mode!r}",
                reason_code="INVALID_ENUM",
                field="confirmation_scope.project_mode",
            )
        if not impact:
            raise TaskContextValidationError(
                "confirmation_scope.estimated_impact is required",
                reason_code="MISSING_REQUIRED",
                field="confirmation_scope.estimated_impact",
            )
        allowed = AllowedPaths.from_dict(data.get("allowed_paths", {}))
        return ConfirmationScope(
            target_project_path=target,
            project_mode=mode,
            allowed_paths=allowed,
            estimated_impact=impact,
            operation_specific=data.get("operation_specific"),
        )


@dataclass(frozen=True)
class UserConfirmation:
    """用户确认记录。绑定特定任务、路径和授权范围。"""
    confirmation_id: str
    task_id: str
    scope: ConfirmationScope
    granted_at: str
    context_hash: str
    expires_at: Optional[str] = None

    def to_dict(self) -> dict:
        result: dict = {
            "confirmation_id": self.confirmation_id,
            "task_id": self.task_id,
            "scope": self.scope.to_dict(),
            "granted_at": self.granted_at,
            "context_hash": self.context_hash,
        }
        if self.expires_at:
            result["expires_at"] = self.expires_at
        return result

    @staticmethod
    def from_dict(data: dict) -> "UserConfirmation":
        if not isinstance(data, dict):
            raise TaskContextValidationError(
                "user_confirmation must be a dict",
                reason_code="INVALID_TYPE",
                field="user_confirmation",
            )
        cid = data.get("confirmation_id", "")
        tid = data.get("task_id", "")
        granted = data.get("granted_at", "")
        chash = data.get("context_hash", "")
        if not cid:
            raise TaskContextValidationError(
                "user_confirmation.confirmation_id is required",
                reason_code="MISSING_REQUIRED",
                field="user_confirmation.confirmation_id",
            )
        if not tid:
            raise TaskContextValidationError(
                "user_confirmation.task_id is required",
                reason_code="MISSING_REQUIRED",
                field="user_confirmation.task_id",
            )
        if not granted:
            raise TaskContextValidationError(
                "user_confirmation.granted_at is required",
                reason_code="MISSING_REQUIRED",
                field="user_confirmation.granted_at",
            )
        if not chash:
            raise TaskContextValidationError(
                "user_confirmation.context_hash is required",
                reason_code="MISSING_REQUIRED",
                field="user_confirmation.context_hash",
            )
        scope = ConfirmationScope.from_dict(data.get("scope", {}))
        return UserConfirmation(
            confirmation_id=cid,
            task_id=tid,
            scope=scope,
            granted_at=granted,
            context_hash=chash,
            expires_at=data.get("expires_at"),
        )

    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        from datetime import datetime, timezone
        try:
            expiry = datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))
            return datetime.now(timezone.utc) > expiry
        except (ValueError, TypeError):
            return False

    def matches_task(self, task_id: str) -> bool:
        return self.task_id == task_id

    def matches_context(self, current_context_hash: str) -> bool:
        return self.context_hash == current_context_hash


@dataclass(frozen=True)
class TaskContext:
    """任务上下文。服务端生成，入队后不可变。

    架构保证（非 Python 语言级）:
    - node-api 在任务提交时创建并固化
    - Redis 入队后，JSON 序列化副本不再被任何 Pipeline 阶段修改
    - Worker 在入口处读取，构造 PathGuard 实例并绑定
    - 需要扩大授权 → 显式重新授权流程
    """
    context_id: str
    workspace_roots: List[str]
    authorized_roots: List[str]
    allowed_paths: AllowedPaths
    target_project_path: str
    project_mode: str
    created_at: str
    schema_version: str = "1.0"
    user_confirmation: Optional[UserConfirmation] = None
    context_hash: str = ""
    compatibility_policy: str = "strict"

    def compute_context_hash(self) -> str:
        """计算授权相关字段的规范化 SHA-256 哈希。

        覆盖字段:
        - workspace_roots (规范化排序)
        - authorized_roots (规范化排序)
        - allowed_paths (read/write/execute 各自排序)
        - target_project_path
        - project_mode
        - schema_version

        不覆盖运行时字段:
        - context_id, created_at, user_confirmation
        - context_hash 自身
        - compatibility_policy
        - target_stack, validation_plan, parent_task_id 等（这些不属于 TaskContext）
        """
        canonical = json.dumps({
            "workspace_roots": sorted([_normalize_path(p) for p in self.workspace_roots]),
            "authorized_roots": sorted([_normalize_path(p) for p in self.authorized_roots]),
            "allowed_paths": {
                "read": sorted([_normalize_path(p) for p in self.allowed_paths.read]),
                "write": sorted([_normalize_path(p) for p in self.allowed_paths.write]),
                "execute": sorted([_normalize_path(p) for p in self.allowed_paths.execute]),
            },
            "target_project_path": _normalize_path(self.target_project_path),
            "project_mode": self.project_mode,
            "schema_version": self.schema_version,
        }, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict:
        result: dict = {
            "context_id": self.context_id,
            "workspace_roots": list(self.workspace_roots),
            "authorized_roots": list(self.authorized_roots),
            "allowed_paths": self.allowed_paths.to_dict(),
            "target_project_path": self.target_project_path,
            "project_mode": self.project_mode,
            "created_at": self.created_at,
            "schema_version": self.schema_version,
            "context_hash": self.context_hash or self.compute_context_hash(),
            "compatibility_policy": self.compatibility_policy,
        }
        if self.user_confirmation is not None:
            result["user_confirmation"] = self.user_confirmation.to_dict()
        return result

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


# ================================================================
# 4. 校验函数（校验顺序: 结构 → 类型 → 枚举 → 路径 → 模式分支）
# ================================================================

def _normalize_path(p: str) -> str:
    """跨平台路径规范化。去除末尾分隔符，统一为 posix 风格进行比较。"""
    if not p:
        return ""
    normalized = os.path.normpath(p)
    normalized = normalized.replace("\\", "/")
    return normalized.rstrip("/")


def _is_path_within(child: str, parent: str) -> bool:
    """检查 child 是否在 parent 目录内（规范化后比较）。"""
    nc = _normalize_path(child)
    np = _normalize_path(parent)
    if nc == np:
        return True
    if nc.startswith(np + "/"):
        return True
    return False


def _validate_common_structure(data: dict) -> None:
    """Phase 1 校验: 结构、必填字段、类型。

    先做结构校验，再做模式分支校验，避免不合法模式先走默认分支。
    """
    if not isinstance(data, dict):
        raise TaskContextValidationError(
            "task_context must be a dict",
            reason_code="INVALID_TYPE",
            field="task_context",
        )

    required_fields = [
        ("context_id", str),
        ("workspace_roots", list),
        ("authorized_roots", list),
        ("allowed_paths", dict),
        ("target_project_path", str),
        ("project_mode", str),
        ("created_at", str),
    ]

    for field_name, expected_type in required_fields:
        if field_name not in data:
            raise TaskContextValidationError(
                f"task_context.{field_name} is required",
                reason_code="MISSING_REQUIRED",
                field=f"task_context.{field_name}",
            )
        value = data[field_name]
        if not isinstance(value, expected_type):
            raise TaskContextValidationError(
                f"task_context.{field_name} must be {expected_type.__name__}, got {type(value).__name__}",
                reason_code="INVALID_TYPE",
                field=f"task_context.{field_name}",
            )

    context_id = data["context_id"]
    if not context_id or not isinstance(context_id, str) or not context_id.strip():
        raise TaskContextValidationError(
            "task_context.context_id must be a non-empty string",
            reason_code="INVALID_VALUE",
            field="task_context.context_id",
        )

    target = data["target_project_path"]
    if not target or not isinstance(target, str) or not target.strip():
        raise TaskContextValidationError(
            "task_context.target_project_path must be a non-empty string",
            reason_code="INVALID_VALUE",
            field="task_context.target_project_path",
        )

    created_at = data["created_at"]
    if not created_at or not isinstance(created_at, str) or not created_at.strip():
        raise TaskContextValidationError(
            "task_context.created_at must be a non-empty string",
            reason_code="INVALID_VALUE",
            field="task_context.created_at",
        )

    mode = data["project_mode"]
    if mode not in VALID_MODES:
        raise TaskContextValidationError(
            f"task_context.project_mode must be one of {VALID_MODES}, got {mode!r}",
            reason_code="INVALID_ENUM",
            field="task_context.project_mode",
        )


def _validate_path_hierarchy(data: dict) -> None:
    """Phase 2 校验: 路径层级关系。

    - workspace_roots 必须恰好有 1 个元素（v1 单根）
    - authorized_roots 必须是 workspace_roots 的子集
    - target_project_path 必须在 authorized_roots 内
    - allowed_paths 各域必须在 authorized_roots 内
    """
    ws_roots = data["workspace_roots"]
    auth_roots = data["authorized_roots"]
    target = data["target_project_path"]
    allowed = data["allowed_paths"]

    if len(ws_roots) == 0:
        raise TaskContextValidationError(
            "workspace_roots must not be empty",
            reason_code="INVALID_VALUE",
            field="task_context.workspace_roots",
        )
    if len(ws_roots) > 1:
        raise TaskContextValidationError(
            "v1 supports exactly one workspace root. Multi-root requests are rejected.",
            reason_code="MULTI_ROOT_NOT_SUPPORTED",
            field="task_context.workspace_roots",
        )

    if len(auth_roots) == 0:
        raise TaskContextValidationError(
            "authorized_roots must not be empty",
            reason_code="INVALID_VALUE",
            field="task_context.authorized_roots",
        )

    for ar in auth_roots:
        found = False
        for wr in ws_roots:
            if _is_path_within(ar, wr):
                found = True
                break
        if not found:
            raise AuthorizationDenied(
                f"authorized_root {ar!r} is not within any workspace_root",
                reason_code="AUTH_ROOT_OUTSIDE_WORKSPACE",
                audit_record={"authorized_root": ar, "workspace_roots": ws_roots},
            )

    target_in_auth = False
    for ar in auth_roots:
        if _is_path_within(target, ar):
            target_in_auth = True
            break
    if not target_in_auth:
        raise AuthorizationDenied(
            f"target_project_path {target!r} is not within any authorized_root",
            reason_code="TARGET_OUTSIDE_AUTH",
            audit_record={"target": target, "authorized_roots": auth_roots},
        )

    for domain in ("read", "write", "execute"):
        paths = allowed.get(domain, [])
        if not isinstance(paths, list):
            raise TaskContextValidationError(
                f"allowed_paths.{domain} must be an array",
                reason_code="INVALID_TYPE",
                field=f"task_context.allowed_paths.{domain}",
            )
        for p in paths:
            in_auth = False
            for ar in auth_roots:
                if _is_path_within(p, ar):
                    in_auth = True
                    break
            if not in_auth:
                raise AuthorizationDenied(
                    f"allowed_paths.{domain} path {p!r} is not within any authorized_root",
                    reason_code="ALLOWED_PATH_OUTSIDE_AUTH",
                    audit_record={"domain": domain, "path": p, "authorized_roots": auth_roots},
                )


def _validate_mode_specific(data: dict) -> None:
    """Phase 3 校验: 按 project_mode 分支。

    create_new_project:
    - 目标路径不能已存在（文件或目录）
    - 目标路径的父目录必须存在且在 authorized_roots 内
    - 父目录检查: 向上查找最近已存在父目录，必须在 authorized_roots 内

    modify_existing_project:
    - 目标路径必须存在且是目录
    """
    mode = data["project_mode"]
    target = data["target_project_path"]
    auth_roots = data["authorized_roots"]

    if mode == ProjectMode.CREATE_NEW_PROJECT.value:
        if os.path.exists(target):
            existing_type = "directory" if os.path.isdir(target) else "file"
            raise TargetPathConflict(
                f"Cannot create new project: target path {target!r} already exists as {existing_type}",
                target_path=target,
                existing_type=existing_type,
            )

        parent = os.path.dirname(os.path.abspath(target))
        if not os.path.exists(parent):
            raise TargetParentNotAuthorized(
                f"Parent directory {parent!r} does not exist for create_new_project target {target!r}",
                target_path=target,
                parent_path=parent,
            )

        parent_in_auth = False
        for ar in auth_roots:
            if _is_path_within(parent, ar):
                parent_in_auth = True
                break
        if not parent_in_auth:
            raise TargetParentNotAuthorized(
                f"Parent directory {parent!r} is not within any authorized_root",
                target_path=target,
                parent_path=parent,
            )

    elif mode == ProjectMode.MODIFY_EXISTING_PROJECT.value:
        if not os.path.exists(target):
            raise TaskContextValidationError(
                f"modify_existing_project target {target!r} does not exist",
                reason_code="TARGET_NOT_FOUND",
                field="task_context.target_project_path",
            )
        if not os.path.isdir(target):
            raise TaskContextValidationError(
                f"modify_existing_project target {target!r} is not a directory",
                reason_code="TARGET_NOT_DIRECTORY",
                field="task_context.target_project_path",
            )


def validate_task_context(data: dict) -> TaskContext:
    """验证并构建 TaskContext。

    校验顺序:
    1. 结构/类型/必填字段/枚举值
    2. 路径层级关系
    3. 按 project_mode 分支

    返回: 不可变的 TaskContext 实例
    抛出: TaskContextValidationError / AuthorizationDenied / TargetPathConflict / TargetParentNotAuthorized
    """
    _validate_common_structure(data)
    _validate_path_hierarchy(data)
    _validate_mode_specific(data)

    allowed = AllowedPaths.from_dict(data["allowed_paths"])

    confirmation = None
    if "user_confirmation" in data and data["user_confirmation"] is not None:
        confirmation = UserConfirmation.from_dict(data["user_confirmation"])

    policy = data.get("compatibility_policy", "strict")
    if policy not in VALID_POLICIES:
        raise TaskContextValidationError(
            f"compatibility_policy must be one of {VALID_POLICIES}, got {policy!r}",
            reason_code="INVALID_ENUM",
            field="task_context.compatibility_policy",
        )

    ctx = TaskContext(
        context_id=data["context_id"].strip(),
        workspace_roots=list(data["workspace_roots"]),
        authorized_roots=list(data["authorized_roots"]),
        allowed_paths=allowed,
        target_project_path=data["target_project_path"].strip(),
        project_mode=data["project_mode"],
        created_at=data["created_at"].strip(),
        schema_version=data.get("schema_version", "1.0"),
        user_confirmation=confirmation,
        context_hash=data.get("context_hash", ""),
        compatibility_policy=policy,
    )

    expected_hash = data.get("context_hash", "")
    computed_hash = ctx.compute_context_hash()
    if expected_hash and expected_hash != computed_hash:
        raise TaskContextValidationError(
            f"context_hash mismatch: expected {expected_hash[:16]}..., computed {computed_hash[:16]}...",
            reason_code="HASH_MISMATCH",
            field="task_context.context_hash",
        )

    return ctx


# ================================================================
# 5. 构建函数
# ================================================================

def build_task_context(
    context_id: str,
    workspace_roots: List[str],
    authorized_roots: List[str],
    allowed_paths: AllowedPaths,
    target_project_path: str,
    project_mode: str,
    created_at: str,
    user_confirmation: Optional[UserConfirmation] = None,
    compatibility_policy: str = "strict",
) -> TaskContext:
    """构建 TaskContext 并自动计算 context_hash。

    注意: 此函数不执行文件系统检查（如目标是否存在）。
    调用方应在 validate_task_context 中完成完整校验。
    """
    ctx = TaskContext(
        context_id=context_id,
        workspace_roots=workspace_roots,
        authorized_roots=authorized_roots,
        allowed_paths=allowed_paths,
        target_project_path=target_project_path,
        project_mode=project_mode,
        created_at=created_at,
        user_confirmation=user_confirmation,
        context_hash="",
        compatibility_policy=compatibility_policy,
    )
    computed = ctx.compute_context_hash()
    return TaskContext(
        context_id=ctx.context_id,
        workspace_roots=ctx.workspace_roots,
        authorized_roots=ctx.authorized_roots,
        allowed_paths=ctx.allowed_paths,
        target_project_path=ctx.target_project_path,
        project_mode=ctx.project_mode,
        created_at=ctx.created_at,
        schema_version=ctx.schema_version,
        user_confirmation=ctx.user_confirmation,
        context_hash=computed,
        compatibility_policy=ctx.compatibility_policy,
    )


def build_compat_task_context(
    workspace_path: str,
    context_id: str = "",
    created_at: str = "",
) -> TaskContext:
    """为不带 task_context 的旧任务构建兼容上下文。

    兼容策略: compat_readonly
    - 允许读取整个工作区
    - 禁止任何写入和命令执行
    - 旧任务需要修改或执行时必须重新提交新协议任务

    这是 P0-1 的修复：旧任务不会自动获得整个工作区的写入权限。
    """
    import uuid
    from datetime import datetime, timezone

    resolved = os.path.abspath(workspace_path)
    allowed = AllowedPaths(
        read=[resolved],
        write=[],   # 不授予写入权限
        execute=[],  # 不授予执行权限
    )
    return build_task_context(
        context_id=context_id or f"compat-{uuid.uuid4().hex[:12]}",
        workspace_roots=[resolved],
        authorized_roots=[resolved],
        allowed_paths=allowed,
        target_project_path=resolved,
        project_mode=ProjectMode.MODIFY_EXISTING_PROJECT.value,
        created_at=created_at or datetime.now(timezone.utc).isoformat(),
        compatibility_policy=CompatibilityPolicy.COMPAT_READONLY.value,
    )


def build_or_extract_task_context(task_payload: dict) -> TaskContext:
    """从任务 payload 中提取或构建 task_context。

    优先使用显式 task_context；不存在时回退到兼容构建。
    兼容构建仅授予 read 权限（compat_readonly）。
    """
    tc_data = task_payload.get("task_context")
    if tc_data and isinstance(tc_data, dict):
        return validate_task_context(tc_data)

    ws_path = task_payload.get("workspace_path", "")
    if not ws_path:
        raise TaskContextValidationError(
            "No task_context and no workspace_path in payload; cannot determine task context",
            reason_code="MISSING_REQUIRED",
            field="payload.task_context|workspace_path",
        )
    return build_compat_task_context(ws_path)


# ================================================================
# 6. 确认匹配
# ================================================================

def find_matching_confirmation(
    ctx: TaskContext,
    task_id: str,
    required_scope: Optional[ConfirmationScope] = None,
) -> Optional[UserConfirmation]:
    """在上下文中查找匹配的确认记录。

    匹配条件:
    1. task_id 匹配
    2. context_hash 匹配（授权范围未变化）
    3. 未过期
    4. 如果提供了 required_scope，还需匹配 target 和 mode
    """
    confirmation = ctx.user_confirmation
    if confirmation is None:
        return None

    if not confirmation.matches_task(task_id):
        return None

    if confirmation.is_expired():
        return None

    current_hash = ctx.compute_context_hash()
    if not confirmation.matches_context(current_hash):
        return None

    if required_scope is not None:
        if confirmation.scope.target_project_path != required_scope.target_project_path:
            return None
        if confirmation.scope.project_mode != required_scope.project_mode:
            return None

    return confirmation


# ================================================================
# 7. 序列化辅助
# ================================================================

def task_context_from_json(json_str: str) -> TaskContext:
    """从 JSON 字符串反序列化并校验 TaskContext。"""
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise TaskContextValidationError(
            f"Invalid JSON in task_context: {e}",
            reason_code="INVALID_JSON",
            field="task_context",
        )
    return validate_task_context(data)


def task_context_to_json(ctx: TaskContext) -> str:
    """将 TaskContext 序列化为 JSON 字符串。"""
    return ctx.to_json()