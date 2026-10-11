# -*- coding: utf-8 -*-
# execution_strategy.py — 代码执行策略（策略模式）
# ---------------------------------------------------------
# 目标：
# 1. 保留本地测试能力（run_python）
# 2. 支持生产环境 Docker 沙箱
# 3. 通过配置驱动策略选择
# ---------------------------------------------------------

from abc import ABC, abstractmethod
from typing import Dict, Any
import subprocess
import tempfile
import os
from pathlib import Path


class ExecutionStrategy(ABC):
    """代码执行策略接口"""
    
    @abstractmethod
    def execute(self, code: str, timeout: int = 10) -> Dict[str, Any]:
        """
        执行代码
        
        参数:
            code: Python 代码字符串
            timeout: 超时时间（秒）
        
        返回:
            Dict[str, Any]: 包含 stdout, stderr, error 的结果
        """
        pass
    
    @abstractmethod
    def cleanup(self):
        """清理资源（如临时文件、Docker 容器）"""
        pass


class LocalExecutionStrategy(ExecutionStrategy):
    """本地执行策略（开发/测试用）"""
    
    def __init__(self):
        from ..code_executor import run_python
        self.run_python = run_python
    
    def execute(self, code: str, timeout: int = 10) -> Dict[str, Any]:
        """本地执行代码（使用现有的 run_python）"""
        return self.run_python(code, timeout=timeout)
    
    def cleanup(self):
        """本地执行无需清理"""
        pass


class DockerExecutionStrategy(ExecutionStrategy):
    """Docker 沙箱执行策略（生产环境用）"""
    
    def __init__(self, image: str = "python:3.11-slim"):
        self.image = image
        self.temp_dir = None
        self.container_name = None
    
    def execute(self, code: str, timeout: int = 10) -> Dict[str, Any]:
        """
        在 Docker 容器中执行代码
        
        流程：
        1. 创建临时文件保存代码
        2. 启动临时容器执行
        3. 捕获输出
        4. 清理容器
        """
        # 创建临时目录
        self.temp_dir = tempfile.mkdtemp(prefix="alphapilot_sandbox_")
        code_file = Path(self.temp_dir) / "execute.py"
        code_file.write_text(code, encoding="utf-8")
        
        # 生成唯一容器名
        import uuid
        self.container_name = f"alphapilot-sandbox-{uuid.uuid4().hex[:8]}"
        
        try:
            # 构建 Docker 命令
            cmd = [
                "docker", "run", "--rm",
                "--name", self.container_name,
                "--network=none",  # 禁止网络访问
                "--read-only",  # 只读根文件系统
                "--memory=256m",  # 内存限制
                "--cpus=0.5",  # CPU 限制
                "-v", f"{self.temp_dir}:/workspace:ro",  # 只读挂载
                "-w", "/workspace",
                self.image,
                "python", "execute.py"
            ]
            
            # 执行并捕获输出
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            return {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "error": None if result.returncode == 0 else result.stderr
            }
            
        except subprocess.TimeoutExpired:
            return {
                "stdout": "",
                "stderr": "",
                "error": f"⏱️ Docker 执行超时（{timeout}秒）"
            }
        except FileNotFoundError:
            return {
                "stdout": "",
                "stderr": "",
                "error": "❌ Docker 未安装或不在 PATH 中"
            }
        except Exception as e:
            return {
                "stdout": "",
                "stderr": "",
                "error": f"❌ Docker 执行失败: {str(e)}"
            }
    
    def cleanup(self):
        """清理临时目录和容器"""
        if self.temp_dir and os.path.exists(self.temp_dir):
            import shutil
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        
        if self.container_name:
            try:
                subprocess.run(
                    ["docker", "rm", "-f", self.container_name],
                    capture_output=True,
                    timeout=5
                )
            except:
                pass


class ExecutionStrategyFactory:
    """执行策略工厂"""
    
    @staticmethod
    def create(strategy_name: str = None) -> ExecutionStrategy:
        """
        创建执行策略
        
        参数:
            strategy_name: 策略名称（"local" 或 "docker"）
                          如果为 None，从环境变量读取
        
        返回:
            ExecutionStrategy: 执行策略实例
        """
        if strategy_name is None:
            strategy_name = os.getenv("ALPHAPILOT_EXEC_STRATEGY", "local")
        
        if strategy_name == "docker":
            return DockerExecutionStrategy()
        elif strategy_name == "local":
            return LocalExecutionStrategy()
        else:
            raise ValueError(f"未知的执行策略: {strategy_name}")
