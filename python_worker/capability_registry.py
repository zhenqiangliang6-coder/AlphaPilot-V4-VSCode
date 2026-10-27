# -*- coding: utf-8 -*-
"""Capability registry and controlled execution for AlphaPilot OS.

Architecture:
  Skill 声明能力 → Registry 解析注册情况 → Worker 授权后执行 → 结果验证

    ① resolve_all(capability_ids)
       → 只解析：检查每个 capability_id 是否已注册。
       → 返回 ResolvedCapabilities（含所有已注册的 CapabilitySpec）。
       → 缺失的能力通过 CapabilityNotAvailable 报告。

    ② ResolvedCapabilities.execute(capability_id, **kwargs)
       → 执行单个已解析的能力。
       → 必须在 resolve_all 之后调用。
       → 不可执行未解析的能力。

    ③ validate_result(spec, result) → CapabilityResult
       → 校验结果类型、工作区路径、执行状态。
       → 验证失败返回 CapabilityResult 带 error 信息，不抛异常。

Design constraints:
  - resolve 和 execute 是两个独立操作。
  - read_only 元数据是声明而非沙箱约束；实际安全由 Worker 执行策略保护。
  - 现有 14 个 Skill 无需修改即可共存。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple


CapabilityHandler = Callable[..., Any]


class CapabilityNotAvailable(RuntimeError):
    """一个或多个声明能力未在 Registry 中注册。"""

    def __init__(self, missing: Tuple[str, ...]):
        self.missing = missing
        super().__init__(
            "Capabilities are not registered: " + ", ".join(missing)
        )


class CapabilityExecutionError(RuntimeError):
    """能力处理函数执行时失败。"""

    def __init__(self, capability_id: str, detail: str):
        self.capability_id = capability_id
        self.detail = detail
        super().__init__(f"[{capability_id}] {detail}")


@dataclass(frozen=True)
class CapabilitySpec:
    """已注册能力的描述符。

    Attributes:
        capability_id: 能力唯一标识（如 "workspace.scan"）。
        handler: 可调用对象，执行实际逻辑。
        read_only: True 表示该能力不修改文件系统（声明性质，非安全保证）。
        description: 人类可读的能力说明。
        input_schema: 输入类型名称（如 "TreeResult"），供编排器引用。
        output_schema: 输出类型名称（如 "TreeResult"），供编排器引用。
    """

    capability_id: str
    handler: CapabilityHandler
    read_only: bool = True
    description: str = ""
    input_schema: str = ""
    output_schema: str = ""


@dataclass(frozen=True)
class CapabilityResult:
    """能力执行结果验证后的统一表示。

    Attributes:
        capability_id: 能力标识。
        success: 执行是否成功。
        data: 执行产出的数据（成功时）。
        error: 错误描述（失败时）。
        validated: 结果是否通过了 validate_result 检查。
    """

    capability_id: str
    success: bool
    data: Any = None
    error: Optional[str] = None
    validated: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ResolvedCapabilities:
    """resolve_all 的产出：已注册能力集合的不可变快照。

    不可直接调用 execute()——需通过 CapabilityRegistry.execute() 或
    此实例的 execute_one() 方法，确保执行前校验。
    """

    specs: Mapping[str, CapabilitySpec]
    resolved_ids: Tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self):
        if not self.resolved_ids:
            object.__setattr__(self, "resolved_ids", tuple(sorted(self.specs.keys())))

    def has(self, capability_id: str) -> bool:
        return capability_id in self.specs

    def get_spec(self, capability_id: str) -> CapabilitySpec:
        spec = self.specs.get(capability_id)
        if spec is None:
            raise CapabilityNotAvailable((capability_id,))
        return spec

    def execute_one(
        self, capability_id: str, **kwargs
    ) -> CapabilityResult:
        spec = self.get_spec(capability_id)
        try:
            data = spec.handler(**kwargs)
            return CapabilityResult(
                capability_id=capability_id,
                success=True,
                data=data,
                validated=False,
            )
        except Exception as error:
            return CapabilityResult(
                capability_id=capability_id,
                success=False,
                error=str(error),
                validated=False,
            )

    def list_ids(self) -> Tuple[str, ...]:
        return self.resolved_ids


class CapabilityRegistry:
    """能力注册中心。

    使用方式:
        registry = CapabilityRegistry()
        registry.register("workspace.scan", scan_workspace, read_only=True,
                          input_schema="str", output_schema="TreeResult")
        resolved = registry.resolve_all(["workspace.scan", "structure.tree"])
        result = registry.execute(resolved, "workspace.scan", root_path="/path")
    """

    def __init__(self):
        self._specs: Dict[str, CapabilitySpec] = {}

    def register(
        self,
        capability_id: str,
        handler: CapabilityHandler,
        read_only: bool = True,
        description: str = "",
        input_schema: str = "",
        output_schema: str = "",
    ) -> None:
        """注册一个能力。

        Raises:
            ValueError: capability_id 格式无效或重复注册。
        """
        if not isinstance(capability_id, str) or not capability_id.strip():
            raise ValueError("capability_id 不能为空")
        if not capability_id.replace(".", "").replace("_", "").replace("-", "").isalnum():
            raise ValueError(
                f"capability_id 格式无效: {capability_id}（仅允许字母数字、.、_、-）"
            )
        if capability_id in self._specs:
            existing = self._specs[capability_id]
            raise ValueError(
                f"能力 {capability_id} 已注册（handler: {existing.handler.__name__}）"
            )
        if not callable(handler):
            raise ValueError(
                f"handler 必须是可调用对象: {capability_id}"
            )

        self._specs[capability_id] = CapabilitySpec(
            capability_id=capability_id,
            handler=handler,
            read_only=read_only,
            description=description,
            input_schema=input_schema,
            output_schema=output_schema,
        )

    def unregister(self, capability_id: str) -> bool:
        if capability_id in self._specs:
            del self._specs[capability_id]
            return True
        return False

    def get(self, capability_id: str) -> Optional[CapabilitySpec]:
        return self._specs.get(capability_id)

    def list_ids(self) -> Tuple[str, ...]:
        return tuple(sorted(self._specs.keys()))

    def resolve_all(
        self, capability_ids: Tuple[str, ...]
    ) -> ResolvedCapabilities:
        """解析能力列表：只检查注册情况，不执行任何工具。

        Args:
            capability_ids: Skill.capabilities 元组中的能力 ID 列表。

        Returns:
            ResolvedCapabilities: 含所有已注册 CapabilitySpec 的快照。

        Raises:
            CapabilityNotAvailable: 存在未注册的能力 ID。
        """
        if not capability_ids:
            return ResolvedCapabilities(specs={})

        specs: Dict[str, CapabilitySpec] = {}
        missing: List[str] = []

        for cid in capability_ids:
            spec = self._specs.get(cid)
            if spec is not None:
                specs[cid] = spec
            else:
                missing.append(cid)

        if missing:
            raise CapabilityNotAvailable(tuple(missing))

        return ResolvedCapabilities(specs=specs)

    def execute(
        self,
        resolved: ResolvedCapabilities,
        capability_id: str,
        **kwargs,
    ) -> CapabilityResult:
        """在已解析的前提下，执行单个能力。

        要求 capability_id 必须已通过 resolve_all 解析。
        这提供了 double-check 保障：不可跨 resolve 边界偷偷执行。

        Args:
            resolved: 之前 resolve_all 返回的已解析能力集。
            capability_id: 要执行的能力 ID。
            **kwargs: 传递给 handler 的关键字参数。

        Returns:
            CapabilityResult: 含执行结果或错误信息。
        """
        if capability_id not in resolved.specs:
            raise CapabilityNotAvailable((capability_id,))
        return resolved.execute_one(capability_id, **kwargs)

    @staticmethod
    def validate_result(
        capability_id: str,
        result: CapabilityResult,
        expected_output_type: Optional[type] = None,
        expected_root_path: Optional[str] = None,
    ) -> CapabilityResult:
        """验证能力执行结果的结构完整性。

        检查:
          1. result.success 是否为 True。
          2. result.data 类型是否匹配 expected_output_type。
          3. 对于 TreeResult：验证 root_path 是否与 expected_root_path 一致。
          4. 对于 TreeResult：验证 scan_timestamp 是否存在。

        Returns:
            通过时返回 validated=True 的 CapabilityResult；
            未通过时返回 validated=False 带 error 的 CapabilityResult。
        """
        if not result.success:
            return CapabilityResult(
                capability_id=capability_id,
                success=False,
                error=result.error or "执行返回 success=False",
                validated=False,
            )

        if result.data is None:
            return CapabilityResult(
                capability_id=capability_id,
                success=False,
                error="执行结果 data 为 None",
                validated=False,
            )

        if expected_output_type is not None and not isinstance(
            result.data, expected_output_type
        ):
            return CapabilityResult(
                capability_id=capability_id,
                success=False,
                error=(
                    f"结果类型不匹配: 期望 {expected_output_type.__name__}, "
                    f"实际 {type(result.data).__name__}"
                ),
                validated=False,
            )

        # TreeResult 专项校验
        type_name = type(result.data).__name__
        if type_name == "TreeResult":
            if not getattr(result.data, "scan_timestamp", None):
                return CapabilityResult(
                    capability_id=capability_id,
                    success=False,
                    error="TreeResult 缺少 scan_timestamp",
                    validated=False,
                )
            if expected_root_path is not None:
                actual_root = getattr(result.data, "root_path", None)
                if actual_root and actual_root != expected_root_path:
                    return CapabilityResult(
                        capability_id=capability_id,
                        success=False,
                        error=(
                            f"root_path 不匹配: 期望 {expected_root_path}, "
                            f"实际 {actual_root}"
                        ),
                        validated=False,
                    )
            if getattr(result.data, "truncated", False):
                return CapabilityResult(
                    capability_id=capability_id,
                    success=True,
                    data=result.data,
                    validated=True,
                    metadata={"warning": "truncated", **result.metadata},
                )

        return CapabilityResult(
            capability_id=capability_id,
            success=True,
            data=result.data,
            validated=True,
            metadata=result.metadata,
        )


# ---- 全局单例 ----

_global_registry: Optional[CapabilityRegistry] = None


def get_registry() -> CapabilityRegistry:
    global _global_registry
    if _global_registry is None:
        _global_registry = CapabilityRegistry()
        _init_defaults(_global_registry)
    return _global_registry


def reset_registry() -> CapabilityRegistry:
    global _global_registry
    _global_registry = CapabilityRegistry()
    _init_defaults(_global_registry)
    return _global_registry


def _init_defaults(registry: CapabilityRegistry) -> None:
    try:
        from .capabilities.scan_workspace import TreeResult, scan_workspace
        from .capabilities.render_structure import tree_to_mermaid, tree_to_text
        from .capabilities.analyze_architecture import analyze_workspace_architecture
    except ImportError:
        from capabilities.scan_workspace import TreeResult, scan_workspace
        from capabilities.render_structure import tree_to_mermaid, tree_to_text
        from capabilities.analyze_architecture import analyze_workspace_architecture

    registry.register(
        capability_id="workspace.scan",
        handler=scan_workspace,
        read_only=True,
        description="只读扫描工作区目录，生成结构化 TreeResult。",
        input_schema="str (root_path)",
        output_schema="TreeResult",
    )
    registry.register(
        capability_id="structure.tree",
        handler=tree_to_text,
        read_only=True,
        description="将 TreeResult 转换为 ASCII 文本树。",
        input_schema="TreeResult",
        output_schema="str",
    )
    registry.register(
        capability_id="structure.mermaid",
        handler=tree_to_mermaid,
        read_only=True,
        description="将 TreeResult 转换为 Mermaid flowchart TD。",
        input_schema="TreeResult",
        output_schema="str",
    )
    registry.register(
        capability_id="arch.analyze",
        handler=analyze_workspace_architecture,
        read_only=True,
        description="只读分析项目架构：提取模块依赖、类/函数定义、分层推断、风险检测。",
        input_schema="str (root_path)",
        output_schema="ArchitectureReport",
    )