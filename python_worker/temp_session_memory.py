"""
临时会话记忆系统 (Temp Session Memory)

设计理念：
    当 PostgreSQL 记忆中枢不可用或无历史数据时，提供基于 JSON 文件的轻量级会话记忆。
    每个项目独立存储最近 N 条对话记录，当用户在同一个工作区中连续对话时，
    可以将前面的任务成果自动注入到后续任务的上下文中。

特性：
    - 零依赖：纯 JSON 文件，不需要任何数据库
    - 按项目隔离：以 workspace_path 的 hash 作为文件名
    - 自动裁剪：每个项目最多保留 MAX_ENTRIES 条记录
    - 启动时清空：start_all.ps1 启动时删除整个 .temp_memory 目录

目录结构：
    .temp_memory/
        <project_hash_1>.json
        <project_hash_2>.json
        ...
"""

import hashlib
import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class TempMemoryEntry:
    """单条临时记忆"""
    task_id: str
    prompt: str
    summary: str
    timestamp: int
    intent: str = "unknown"
    result_preview: str = ""


class TempSessionMemory:
    """
    临时会话记忆管理器

    用法:
        mem = TempSessionMemory()
        store = mem.get_or_create_store("d:\\my_project")

        # 保存一条记忆
        mem.append(store, task_id="...", prompt="...", ...)

        # 搜索相关记忆
        related = mem.search(store, query="...", top_k=5)
    """

    MAX_ENTRIES = 20
    STORE_FILE = ".temp_memory"

    def __init__(self, base_dir: str = None):
        if base_dir is None:
            base_dir = os.environ.get(
                "ALPHAPILOT_TEMP_MEMORY_DIR",
                self._default_temp_dir()
            )
        self._base = Path(base_dir)
        self._base.mkdir(parents=True, exist_ok=True)

    def _default_temp_dir(self) -> str:
        return str(Path(__file__).resolve().parent.parent / ".temp_memory")

    def _hash_path(self, workspace_path: str) -> str:
        return hashlib.md5(workspace_path.encode("utf-8")).hexdigest()[:12]

    def get_or_create_store(self, workspace_path: str) -> dict:
        """
        加载或创建一个项目记忆存储。

        返回格式:
        {
            "workspace_path": "...",
            "project_hash": "...",
            "entries": [...],
            "created_at": timestamp
        }
        """
        if not workspace_path:
            return self._empty_store("")

        safe_path = str(workspace_path).strip()
        project_hash = self._hash_path(safe_path)
        file_path = self._base / f"{project_hash}.json"

        if file_path.exists():
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    store = json.load(f)
                if isinstance(store, dict) and "entries" in store:
                    return store
            except (json.JSONDecodeError, OSError):
                pass

        return self._empty_store(safe_path, project_hash)

    def _empty_store(self, workspace_path: str, project_hash: str = None) -> dict:
        return {
            "workspace_path": workspace_path,
            "project_hash": project_hash or self._hash_path(workspace_path),
            "entries": [],
            "created_at": int(time.time() * 1000),
        }

    def _save_store(self, store: dict) -> bool:
        project_hash = store.get("project_hash", "")
        if not project_hash:
            return False
        file_path = self._base / f"{project_hash}.json"
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(store, f, ensure_ascii=False, indent=2)
            return True
        except OSError as e:
            print(f"[TEMP_MEMORY] 保存失败: {e}")
            return False

    def append(
        self,
        store: dict,
        task_id: str,
        prompt: str,
        summary: str = "",
        intent: str = "unknown",
        result_preview: str = "",
    ) -> bool:
        """追加一条对话记录"""
        if not task_id or not prompt:
            return False

        entry = TempMemoryEntry(
            task_id=str(task_id),
            prompt=str(prompt)[:2000],
            summary=str(summary)[:1000],
            timestamp=int(time.time() * 1000),
            intent=str(intent),
            result_preview=str(result_preview)[:800],
        )

        entries: list = store.get("entries", [])

        same_entry = any(e.get("task_id") == entry.task_id for e in entries)
        if not same_entry:
            entries.append({
                "task_id": entry.task_id,
                "prompt": entry.prompt,
                "summary": entry.summary,
                "timestamp": entry.timestamp,
                "intent": entry.intent,
                "result_preview": entry.result_preview,
            })

        if len(entries) > self.MAX_ENTRIES:
            entries[:] = sorted(
                entries, key=lambda e: e.get("timestamp", 0), reverse=True
            )[:self.MAX_ENTRIES]

        store["entries"] = entries
        store["updated_at"] = int(time.time() * 1000)

        return self._save_store(store)

    def search(
        self,
        store: dict,
        query: str,
        top_k: int = 5,
    ) -> List[TempMemoryEntry]:
        """关键词搜索相关的前置对话记录
        
        搜索策略（三层降级）：
        1. 双字/三字中文词 + 英文词 精确匹配
        2. 中文单字匹配（对"上面内容"、"前述设计"这类引用友好）
        3. 无匹配时返回最近一条记录（兜底"上面内容"引用）
        """
        if not query or not store:
            return []

        entries: list = store.get("entries", [])
        if not entries:
            return []

        # ---- 第一层：双字及以上关键词匹配 ----
        multi_keywords = [
            kw for kw in re.findall(r'[\u4e00-\u9fff]{2,}|[a-zA-Z]{3,}', query)
            if len(kw) >= 2
        ]

        # ---- 第二层：检测"上面内容"类引用词 ----
        reference_keywords = re.findall(
            r'(?:上面|上文|前面|之前|刚才|上一轮|前述|上述|以上|前述)',
            query
        )
        action_keywords = re.findall(
            r'(?:执行|实现|编写|开发|写代码|动手|继续|落地|完成)',
            query
        )

        # ---- 2.5层：检测确认词 + 动作词的组合 ----
        # "对的，运行吧" / "好的，开始吧" / "OK，来吧" 等
        confirmation_keywords = re.findall(
            r'(?:很好|好的|OK|okay?|对的|不错|行|可以|好|嗯嗯?|对|是的|没错|正是|没问题|可以啊)',
            query
        )
        short_action_keywords = re.findall(
            r'(?:执行|运行|实现|编译|部署|发布|开始|写|做|改|动手|来吧|做吧|继续|往下|进行)',
            query
        )

        scored: List[tuple] = []
        for entry in entries:
            text = (
                (entry.get("prompt", "") or "")
                + " "
                + (entry.get("summary", "") or "")
                + " "
                + (entry.get("result_preview", "") or "")
            ).lower()

            score = 0.0

            # 多字关键词匹配
            for kw in multi_keywords:
                if kw.lower() in text:
                    score += 1.0
                else:
                    score -= 0.1

            # 引用词（上面/上文/前述...）+ 动作词（执行/实现/编写...）的组合
            if reference_keywords and action_keywords:
                score += 2.0

            # 确认词（好的/对的/OK...）+ 动作词（运行/开始/执行...）的组合
            # 这种组合强烈暗示用户想基于上文继续执行
            if confirmation_keywords and short_action_keywords:
                score += 2.5

            if score > 0:
                scored.append((score, entry))

        # 按分数和新鲜度排序
        scored.sort(key=lambda x: (-x[0], -(x[1].get("timestamp", 0))))

        # ---- 第三层：无匹配时回退到最近一条 ----
        if not scored and (reference_keywords or action_keywords or confirmation_keywords):
            latest = max(entries, key=lambda e: e.get("timestamp", 0))
            scored.append((0.5, latest))

        results: List[TempMemoryEntry] = []
        for score, entry in scored[:top_k]:
            results.append(TempMemoryEntry(
                task_id=entry.get("task_id", ""),
                prompt=entry.get("prompt", ""),
                summary=entry.get("summary", ""),
                timestamp=entry.get("timestamp", 0),
                intent=entry.get("intent", "unknown"),
                result_preview=entry.get("result_preview", ""),
            ))

        return results

    def format_context(self, results: List[TempMemoryEntry]) -> str:
        """格式化为可注入 LLM 的上下文文本"""
        if not results:
            return ""

        lines = ["## 最近对话上下文（临时会话记忆）"]
        for i, entry in enumerate(results, 1):
            lines.append(f"\n### 对话 {i}（{entry.intent}）")
            lines.append(f"用户请求: {entry.prompt[:500]}")
            if entry.summary:
                lines.append(f"任务摘要: {entry.summary[:500]}")
            if entry.result_preview:
                lines.append(f"成果预览: {entry.result_preview[:400]}")
            lines.append("")

        return "\n".join(lines)

    def clear_all(self) -> bool:
        """清空所有临时记忆文件（start_all.ps1 启动时调用）"""
        try:
            for file in self._base.glob("*.json"):
                file.unlink(missing_ok=True)
            return True
        except OSError as e:
            print(f"[TEMP_MEMORY] 清空失败: {e}")
            return False


_temp_memory_instance: Optional[TempSessionMemory] = None


def get_temp_memory() -> TempSessionMemory:
    """获取全局临时记忆单例"""
    global _temp_memory_instance
    if _temp_memory_instance is None:
        _temp_memory_instance = TempSessionMemory()
    return _temp_memory_instance