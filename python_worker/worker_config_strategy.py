# -*- coding: utf-8 -*-
# worker_config.py — 配置驱动的运行时策略
# ---------------------------------------------------------
# 通过环境变量或配置文件控制执行策略
# ---------------------------------------------------------

import os
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class WorkerConfig:
    """Worker 配置（不可变）"""
    
    # 执行策略：local（本地）或 docker（沙箱）
    exec_strategy: str = os.getenv("ALPHAPILOT_EXEC_STRATEGY", "local")
    
    # Docker 配置
    docker_image: str = os.getenv("ALPHAPILOT_DOCKER_IMAGE", "python:3.11-slim")
    docker_memory_limit: str = os.getenv("ALPHAPILOT_DOCKER_MEMORY", "256m")
    docker_cpu_limit: str = os.getenv("ALPHAPILOT_DOCKER_CPU", "0.5")
    
    # 执行超时
    exec_timeout: int = int(os.getenv("ALPHAPILOT_EXEC_TIMEOUT", "10"))
    
    # 安全配置
    forbid_docker_host: bool = os.getenv("ALPHAPILOT_FORBID_DOCKER_HOST", "true").lower() == "true"
    
    @classmethod
    def get_config(cls) -> "WorkerConfig":
        """获取当前配置"""
        config = cls()
        
        # 安全检查：如果配置了 Docker 策略但禁止 DOCKER_HOST
        if config.exec_strategy == "docker" and config.forbid_docker_host:
            if "DOCKER_HOST" in os.environ:
                raise RuntimeError(
                    "⛔ 安全检查失败：检测到 DOCKER_HOST 环境变量，"
                    "但配置禁止使用自定义 Docker 主机。"
                    "这可能存在安全风险。"
                )
        
        return config
    
    def is_docker_available(self) -> bool:
        """检查 Docker 是否可用"""
        import subprocess
        try:
            subprocess.run(
                ["docker", "--version"],
                capture_output=True,
                timeout=5
            )
            return True
        except:
            return False


# 全局配置实例
_config_cache: Optional[WorkerConfig] = None


def get_worker_config() -> WorkerConfig:
    """获取 Worker 配置（单例模式）"""
    global _config_cache
    if _config_cache is None:
        _config_cache = WorkerConfig.get_config()
    return _config_cache
