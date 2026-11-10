# -*- coding: utf-8 -*-
# pipeline_executor — 通用多阶段编排引擎
# ---------------------------------------------------------
# 架构合规性（Architecture Compliance）
#
# ✅ Worker = 真相（Truth Source）
#    - Pipeline 执行器完整运行在 Worker 进程内
#    - 所有编排逻辑、阶段转换、检查点均在 Worker 边界内
#
# ✅ 协议 = 宪法（Protocol = Constitution）
#    - 不引入新的 WebSocket / HTTP 端点 / Redis 通道
#    - 阶段进度通过现有 stream_chunk 推送
#
# 本包是 AlphaPilot 的工业级任务编排引擎，负责：
# 1. 将隐式的执行链升级为显式 PipelineStage → PipelineContract
# 2. 提供阶段间类型化制品传递（PlanArtifact → CodeArtifact → TestArtifact）
# 3. 支持检查点断点续跑（PipelineCheckpoint）
# 4. 定义三阶段管道模型（Preparatory → Generative → PostProcess）
#
# ---------------------------------------------------------

from .contract import (
    PipelineState,
    PipelineStage,
    PipelineContract,
    PlanArtifact,
    CodeArtifact,
    TestArtifact,
    FixArtifact,
    ChangelogArtifact,
)
from .checkpoint import PipelineCheckpoint
from .stages import (
    PreparatoryStage,
    GenerativeStage,
    PostProcessStage,
)
from .pipeline import PipelineExecutor

__all__ = [
    # 契约
    "PipelineState",
    "PipelineStage",
    "PipelineContract",
    # 制品
    "PlanArtifact",
    "CodeArtifact",
    "TestArtifact",
    "FixArtifact",
    "ChangelogArtifact",
    # 检查点
    "PipelineCheckpoint",
    # 阶段
    "PreparatoryStage",
    "GenerativeStage",
    "PostProcessStage",
    # 执行器
    "PipelineExecutor",
]