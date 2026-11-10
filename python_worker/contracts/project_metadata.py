# -*- coding: utf-8 -*-
# python_worker/contracts/project_metadata.py — 项目元数据契约
# ---------------------------------------------------------
# 契约 2/3：Project Metadata Contract
#
# 描述当前项目的技术特征，为能力实现选择提供依据。
# 元数据必须有来源（不是凭空声明）、有置信度（不是非黑即白）、
# 可更新（检测结果可以替换 LLM 推断）。
#
# 第五条原则：元数据可溯源
#   不能把 LLM 的一次猜测直接当成事实。
#   - MetadataSource.FILE_SYSTEM  — 从 pom.xml 检测 → 高置信度
#   - MetadataSource.TOOL_OUTPUT  — 从 mvn --version 解析 → 高置信度
#   - MetadataSource.LLM_INFER    — 模型推断 → 低置信度
#   - MetadataSource.MANUAL       — 用户/配置指定 → 最高置信度
# ---------------------------------------------------------

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
import os


# =========================================================
# 1. 枚举类型
# =========================================================

class MetadataSource(str, Enum):
    FILE_SYSTEM = "file_system"
    TOOL_OUTPUT = "tool_output"
    LLM_INFER = "llm_inference"
    MANUAL = "manual"
    UNKNOWN = "unknown"


class MetadataConfidence(str, Enum):
    HIGH = "high"        # 从真实构建文件或工具输出检测
    MEDIUM = "medium"    # 从间接证据推断（如文件扩展名）
    LOW = "low"          # 从 LLM 推断，未经工具验证
    UNKNOWN = "unknown"


class BuildSystem(str, Enum):
    MAVEN = "maven"
    GRADLE = "gradle"
    GRADLE_KTS = "gradle_kts"
    CARGO = "cargo"
    GO_MOD = "go_mod"
    NPM = "npm"
    YARN = "yarn"
    PNPM = "pnpm"
    PIP = "pip"
    SETUPTOOLS = "setuptools"
    POETRY = "poetry"
    NONE = "none"
    UNKNOWN = "unknown"


class TestFramework(str, Enum):
    PYTEST = "pytest"
    UNITTEST = "unittest"
    JUNIT = "junit"
    TESTNG = "testng"
    JEST = "jest"
    MOCHA = "mocha"
    GO_TEST = "go_test"
    CARGO_TEST = "cargo_test"
    NONE = "none"
    UNKNOWN = "unknown"


# =========================================================
# 2. 项目元数据
# =========================================================

@dataclass
class ProjectMetadata:
    language: str = "unknown"
    language_source: MetadataSource = MetadataSource.UNKNOWN
    language_confidence: MetadataConfidence = MetadataConfidence.UNKNOWN

    build_system: BuildSystem = BuildSystem.UNKNOWN
    build_system_source: MetadataSource = MetadataSource.UNKNOWN
    build_system_confidence: MetadataConfidence = MetadataConfidence.UNKNOWN

    test_framework: TestFramework = TestFramework.UNKNOWN
    test_framework_source: MetadataSource = MetadataSource.UNKNOWN
    test_framework_confidence: MetadataConfidence = MetadataConfidence.UNKNOWN

    package_manager: str = ""
    package_manager_source: MetadataSource = MetadataSource.UNKNOWN
    package_manager_confidence: MetadataConfidence = MetadataConfidence.UNKNOWN

    # 附加信息
    source_files: List[str] = field(default_factory=list)
    config_files: List[str] = field(default_factory=list)
    deployment_target: str = ""   # e.g. "docker", "lambda", "k8s"

    def to_dict(self) -> dict:
        return {
            "language": self.language,
            "language_source": self.language_source.value,
            "language_confidence": self.language_confidence.value,
            "build_system": self.build_system.value,
            "build_system_source": self.build_system_source.value,
            "build_system_confidence": self.build_system_confidence.value,
            "test_framework": self.test_framework.value,
            "test_framework_source": self.test_framework_source.value,
            "test_framework_confidence": self.test_framework_confidence.value,
            "package_manager": self.package_manager,
            "package_manager_source": self.package_manager_source.value,
            "package_manager_confidence": self.package_manager_confidence.value,
            "source_files": self.source_files,
            "config_files": self.config_files,
            "deployment_target": self.deployment_target,
        }

    def is_confident(self) -> bool:
        """所有关键字段置信度均为 HIGH 或至少非 UNKNOWN。"""
        return (
            self.language_confidence != MetadataConfidence.UNKNOWN
            and self.build_system_confidence != MetadataConfidence.UNKNOWN
        )


# =========================================================
# 3. 项目检测函数
# =========================================================

def detect_project_metadata(workspace: str) -> ProjectMetadata:
    """从工作区文件系统检测项目元数据。

    检测规则按确定性从高到低：
      Java  (pom.xml / build.gradle)
      Rust  (Cargo.toml)
      Go    (go.mod)
      TS/JS (tsconfig.json / package.json)
      Python (requirements.txt / setup.py / pyproject.toml)
    """
    meta = ProjectMetadata()
    config_files = []

    # ── Java (Maven) ──
    if os.path.isfile(os.path.join(workspace, "pom.xml")):
        meta.language = "java"
        meta.language_source = MetadataSource.FILE_SYSTEM
        meta.language_confidence = MetadataConfidence.HIGH
        meta.build_system = BuildSystem.MAVEN
        meta.build_system_source = MetadataSource.FILE_SYSTEM
        meta.build_system_confidence = MetadataConfidence.HIGH
        meta.test_framework = TestFramework.JUNIT
        meta.test_framework_source = MetadataSource.FILE_SYSTEM
        meta.test_framework_confidence = MetadataConfidence.MEDIUM
        meta.package_manager = "maven"
        meta.package_manager_source = MetadataSource.FILE_SYSTEM
        meta.package_manager_confidence = MetadataConfidence.HIGH
        config_files.append("pom.xml")

    # ── Java (Gradle) ──
    elif os.path.isfile(os.path.join(workspace, "build.gradle.kts")):
        meta.language = "java"
        meta.language_source = MetadataSource.FILE_SYSTEM
        meta.language_confidence = MetadataConfidence.HIGH
        meta.build_system = BuildSystem.GRADLE_KTS
        meta.build_system_source = MetadataSource.FILE_SYSTEM
        meta.build_system_confidence = MetadataConfidence.HIGH
        meta.test_framework = TestFramework.JUNIT
        meta.test_framework_source = MetadataSource.FILE_SYSTEM
        meta.test_framework_confidence = MetadataConfidence.MEDIUM
        meta.package_manager = "gradle"
        meta.package_manager_source = MetadataSource.FILE_SYSTEM
        meta.package_manager_confidence = MetadataConfidence.HIGH
        config_files.append("build.gradle.kts")

    elif os.path.isfile(os.path.join(workspace, "build.gradle")):
        meta.language = "java"
        meta.language_source = MetadataSource.FILE_SYSTEM
        meta.language_confidence = MetadataConfidence.HIGH
        meta.build_system = BuildSystem.GRADLE
        meta.build_system_source = MetadataSource.FILE_SYSTEM
        meta.build_system_confidence = MetadataConfidence.HIGH
        meta.test_framework = TestFramework.JUNIT
        meta.test_framework_source = MetadataSource.FILE_SYSTEM
        meta.test_framework_confidence = MetadataConfidence.MEDIUM
        meta.package_manager = "gradle"
        meta.package_manager_source = MetadataSource.FILE_SYSTEM
        meta.package_manager_confidence = MetadataConfidence.HIGH
        config_files.append("build.gradle")

    # ── Rust ──
    elif os.path.isfile(os.path.join(workspace, "Cargo.toml")):
        meta.language = "rust"
        meta.language_source = MetadataSource.FILE_SYSTEM
        meta.language_confidence = MetadataConfidence.HIGH
        meta.build_system = BuildSystem.CARGO
        meta.build_system_source = MetadataSource.FILE_SYSTEM
        meta.build_system_confidence = MetadataConfidence.HIGH
        meta.test_framework = TestFramework.CARGO_TEST
        meta.test_framework_source = MetadataSource.FILE_SYSTEM
        meta.test_framework_confidence = MetadataConfidence.HIGH
        meta.package_manager = "cargo"
        meta.package_manager_source = MetadataSource.FILE_SYSTEM
        meta.package_manager_confidence = MetadataConfidence.HIGH
        config_files.append("Cargo.toml")

    # ── Go ──
    elif os.path.isfile(os.path.join(workspace, "go.mod")):
        meta.language = "go"
        meta.language_source = MetadataSource.FILE_SYSTEM
        meta.language_confidence = MetadataConfidence.HIGH
        meta.build_system = BuildSystem.GO_MOD
        meta.build_system_source = MetadataSource.FILE_SYSTEM
        meta.build_system_confidence = MetadataConfidence.HIGH
        meta.test_framework = TestFramework.GO_TEST
        meta.test_framework_source = MetadataSource.FILE_SYSTEM
        meta.test_framework_confidence = MetadataConfidence.HIGH
        meta.package_manager = "go mod"
        meta.package_manager_source = MetadataSource.FILE_SYSTEM
        meta.package_manager_confidence = MetadataConfidence.HIGH
        config_files.append("go.mod")

    # ── TypeScript ──
    elif os.path.isfile(os.path.join(workspace, "tsconfig.json")):
        meta.language = "typescript"
        meta.language_source = MetadataSource.FILE_SYSTEM
        meta.language_confidence = MetadataConfidence.HIGH
        meta.build_system = BuildSystem.NPM
        meta.build_system_source = MetadataSource.FILE_SYSTEM
        meta.build_system_confidence = MetadataConfidence.MEDIUM
        meta.test_framework = TestFramework.JEST
        meta.test_framework_source = MetadataSource.FILE_SYSTEM
        meta.test_framework_confidence = MetadataConfidence.MEDIUM

        if os.path.isfile(os.path.join(workspace, "pnpm-lock.yaml")):
            meta.package_manager = "pnpm"
        elif os.path.isfile(os.path.join(workspace, "yarn.lock")):
            meta.package_manager = "yarn"
        else:
            meta.package_manager = "npm"
        meta.package_manager_source = MetadataSource.FILE_SYSTEM
        meta.package_manager_confidence = MetadataConfidence.HIGH
        config_files.append("tsconfig.json")
        if os.path.isfile(os.path.join(workspace, "package.json")):
            config_files.append("package.json")

    # ── JavaScript ──
    elif os.path.isfile(os.path.join(workspace, "package.json")):
        meta.language = "javascript"
        meta.language_source = MetadataSource.FILE_SYSTEM
        meta.language_confidence = MetadataConfidence.HIGH
        meta.build_system = BuildSystem.NPM
        meta.build_system_source = MetadataSource.FILE_SYSTEM
        meta.build_system_confidence = MetadataConfidence.MEDIUM
        meta.test_framework = TestFramework.JEST
        meta.test_framework_source = MetadataSource.FILE_SYSTEM
        meta.test_framework_confidence = MetadataConfidence.MEDIUM

        if os.path.isfile(os.path.join(workspace, "pnpm-lock.yaml")):
            meta.package_manager = "pnpm"
        elif os.path.isfile(os.path.join(workspace, "yarn.lock")):
            meta.package_manager = "yarn"
        else:
            meta.package_manager = "npm"
        meta.package_manager_source = MetadataSource.FILE_SYSTEM
        meta.package_manager_confidence = MetadataConfidence.HIGH
        config_files.append("package.json")

    # ── Python ──
    elif os.path.isfile(os.path.join(workspace, "requirements.txt")) or \
         os.path.isfile(os.path.join(workspace, "setup.py")) or \
         os.path.isfile(os.path.join(workspace, "pyproject.toml")):
        meta.language = "python"
        meta.language_source = MetadataSource.FILE_SYSTEM
        meta.language_confidence = MetadataConfidence.HIGH
        meta.build_system = BuildSystem.PIP
        meta.build_system_source = MetadataSource.FILE_SYSTEM
        meta.build_system_confidence = MetadataConfidence.MEDIUM
        meta.test_framework = TestFramework.PYTEST
        meta.test_framework_source = MetadataSource.FILE_SYSTEM
        meta.test_framework_confidence = MetadataConfidence.MEDIUM

        if os.path.isfile(os.path.join(workspace, "pyproject.toml")):
            meta.package_manager = "pip"
            if _file_contains(os.path.join(workspace, "pyproject.toml"), "[tool.poetry]"):
                meta.package_manager = "poetry"
                meta.build_system = BuildSystem.POETRY
            config_files.append("pyproject.toml")
        elif os.path.isfile(os.path.join(workspace, "setup.py")):
            meta.package_manager = "setuptools"
            meta.build_system = BuildSystem.SETUPTOOLS
            config_files.append("setup.py")
        else:
            meta.package_manager = "pip"
        meta.package_manager_source = MetadataSource.FILE_SYSTEM
        meta.package_manager_confidence = MetadataConfidence.HIGH

        # 扫描 .py 文件
        for fname in os.listdir(workspace):
            fpath = os.path.join(workspace, fname)
            if os.path.isfile(fpath) and fname.endswith(".py"):
                meta.source_files.append(fname)
    else:
        # ── 降级：根据文件扩展名推断 ──
        meta = _detect_by_extension(workspace)

    meta.config_files = config_files
    return meta


def update_project_metadata(
    meta: ProjectMetadata,
    field: str,
    value: Any,
    source: MetadataSource,
    confidence: MetadataConfidence = MetadataConfidence.MEDIUM,
) -> ProjectMetadata:
    """更新元数据字段（仅在来源置信度更高时覆盖）。

    保护规则：不降低置信度。例如：
      - FILE_SYSTEM (HIGH) 不会被 LLM_INFER (LOW) 覆盖
      - LLM_INFER (LOW) 可以被 TOOL_OUTPUT (MEDIUM) 升级
    """
    source_strength = {
        MetadataSource.MANUAL: 4,
        MetadataSource.TOOL_OUTPUT: 3,
        MetadataSource.FILE_SYSTEM: 2,
        MetadataSource.LLM_INFER: 1,
        MetadataSource.UNKNOWN: 0,
    }

    current_source_field = f"{field}_source"
    current_confidence_field = f"{field}_confidence"

    current_source = getattr(meta, current_source_field, MetadataSource.UNKNOWN)
    current_strength = source_strength.get(current_source, 0)
    new_strength = source_strength.get(source, 0)

    if new_strength >= current_strength:
        setattr(meta, field, value)
        setattr(meta, current_source_field, source)
        setattr(meta, current_confidence_field, confidence)
        return meta

    # 同源升级
    if source == current_source and confidence.value >= getattr(meta, current_confidence_field).value:
        setattr(meta, field, value)
        setattr(meta, current_confidence_field, confidence)

    return meta


# =========================================================
# 4. 辅助函数
# =========================================================

def _file_contains(filepath: str, substring: str) -> bool:
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return substring in f.read(20000)
    except Exception:
        return False


def _detect_by_extension(workspace: str) -> ProjectMetadata:
    """降级检测：根据文件扩展名推断语言。置信度 LOW。"""
    meta = ProjectMetadata()
    extensions = {"py": 0, "js": 0, "ts": 0, "jsx": 0, "tsx": 0, "java": 0, "go": 0, "rs": 0}

    try:
        for fname in os.listdir(workspace):
            fpath = os.path.join(workspace, fname)
            if os.path.isfile(fpath):
                ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
                if ext in extensions:
                    extensions[ext] += 1
                    meta.source_files.append(fname)
    except OSError:
        pass

    dominant = max(extensions, key=extensions.get)
    if extensions[dominant] == 0:
        return meta

    ext_to_lang = {"py": "python", "js": "javascript", "jsx": "javascript",
                   "ts": "typescript", "tsx": "typescript",
                   "java": "java", "go": "go", "rs": "rust"}
    meta.language = ext_to_lang.get(dominant, "unknown")
    meta.language_source = MetadataSource.FILE_SYSTEM
    meta.language_confidence = MetadataConfidence.LOW

    return meta