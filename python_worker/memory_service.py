# -*- coding: utf-8 -*-
"""
AlphaPilot 记忆中枢 - 核心服务模块
架构：海马体-新皮层协作模式
作者：World-Class AI Architect
版本：v1.0.0

功能：
- 记忆写入决策（Gatekeeper）
- 记忆检索与注入（Prompt 组装）
- 记忆生命周期管理（衰减、剪枝、合并）
- 向量相似度搜索
"""

import os
import json
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, field
from enum import Enum
import psycopg2
from psycopg2.extras import Json
import openai


# ============================================================
# 配置管理
# ============================================================
def _env_any(*names, default=None):
    """按优先级读取多个候选环境变量名，命中第一个非空值即返回。

    用于兼容两套命名：
    - MEMORY_DB_*：Python worker 内部使用
    - DB_*：.env.memory / docker-compose.yml 使用（无前缀）
    这样同一份配置文件能同时喂给容器编排与 Python 侧，无需重复维护。
    """
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return default


class MemoryConfig:
    """记忆中枢配置"""

    # PostgreSQL 连接配置
    DB_HOST = _env_any("MEMORY_DB_HOST", "DB_HOST", default="localhost")
    DB_PORT = int(_env_any("MEMORY_DB_PORT", "DB_PORT", default="5432"))
    DB_USER = _env_any("MEMORY_DB_USER", "DB_USER", default="alphapilot")
    # 密码不给默认值：必须通过环境变量提供，避免真实密码写进源码随仓库外泄
    DB_PASSWORD = _env_any("MEMORY_DB_PASSWORD", "DB_PASSWORD", default="")
    DB_NAME = _env_any("MEMORY_DB_NAME", "DB_NAME", default="alphapilot_memory")
    
    # OpenAI Embedding 配置（用于向量生成）
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    EMBEDDING_DIMENSION = 1536
    
    # 记忆生命周期参数
    ACTIVATION_DECAY_RATE_1D = 0.95      # 1天内衰减率
    ACTIVATION_DECAY_RATE_7D = 0.85      # 1-7天衰减率
    ACTIVATION_DECAY_RATE_30D = 0.70     # 7-30天衰减率
    ACTIVATION_DECAY_RATE_60D = 0.50     # 60天以上衰减率
    
    # 剪枝阈值
    PRUNE_ACTIVATION_THRESHOLD = 0.1     # 激活度低于此值且未访问过 → 删除
    ARCHIVE_ACTIVATION_THRESHOLD = 0.2   # 激活度低于此值且创建>30天 → 归档
    MERGE_SIMILARITY_THRESHOLD = 0.92    # 语义相似度高于此值 → 合并
    
    # 检索参数
    DEFAULT_TOP_K = 5
    MIN_ACTIVATION_FOR_SEARCH = 0.3
    MAX_CONTEXT_TOKENS = 2000


# ============================================================
# 枚举类型
# ============================================================
class MemoryType(str, Enum):
    """记忆类型"""
    PREFERENCE = "preference"      # 用户偏好
    FACT = "fact"                  # 事实知识
    SKILL = "skill"                # 技能经验
    CONVERSATION = "conversation"  # 对话记忆
    INSIGHT = "insight"            # 洞察领悟


class MemoryStatus(str, Enum):
    """记忆状态"""
    ACTIVE = "active"              # 活跃
    ARCHIVED = "archived"          # 归档
    PRUNED = "pruned"              # 已剪枝
    MERGED = "merged"              # 已合并


class RelationType(str, Enum):
    """关联关系类型"""
    RELATED_TO = "related_to"
    CONTRADICTS = "contradicts"
    DEPENDS_ON = "depends_on"
    IS_EXAMPLE_OF = "is_example_of"


# ============================================================
# 数据模型
# ============================================================
@dataclass
class MemoryItem:
    """记忆条目数据模型"""
    id: Optional[str] = None
    user_id: str = ""
    content: str = ""
    summary: Optional[str] = None
    embedding: Optional[List[float]] = None
    memory_type: MemoryType = MemoryType.FACT
    domain_tags: List[str] = field(default_factory=list)
    importance_score: float = 0.5
    activation_score: float = 1.0
    access_count: int = 0
    last_accessed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    status: MemoryStatus = MemoryStatus.ACTIVE
    merged_into: Optional[str] = None


@dataclass
class GatekeeperDecision:
    """守门人决策结果"""
    remember: bool
    memory_type: Optional[MemoryType] = None
    importance: float = 0.5
    target: str = ""  # "user_profiles" 或 "memory_items"
    reason: str = ""


# ============================================================
# 核心服务类
# ============================================================
class MemoryService:
    """
    AlphaPilot 记忆中枢核心服务
    
    职责：
    1. 记忆写入决策（Gatekeeper）
    2. 记忆存储与检索
    3. 向量相似度搜索
    4. 生命周期管理（衰减、剪枝、合并）
    """
    
    def __init__(self, config: MemoryConfig = None):
        self.config = config or MemoryConfig()
        self._connection = None
        
        # 初始化 OpenAI client（用于 embedding）
        if self.config.OPENAI_API_KEY:
            openai.api_key = self.config.OPENAI_API_KEY
    
    # --------------------------------------------------------
    # 数据库连接管理
    # --------------------------------------------------------
    def _get_connection(self):
        """获取数据库连接（懒加载）"""
        if self._connection is None or self._connection.closed:
            if not self.config.DB_PASSWORD:
                raise EnvironmentError(
                    "数据库密码未配置：请设置环境变量 DB_PASSWORD 或 MEMORY_DB_PASSWORD。"
                    "可复制项目根目录的 .env.memory.example 为 .env.memory 后填写；"
                    "该文件已被 .gitignore 忽略，不会提交到仓库。"
                )
            self._connection = psycopg2.connect(
                host=self.config.DB_HOST,
                port=self.config.DB_PORT,
                user=self.config.DB_USER,
                password=self.config.DB_PASSWORD,
                dbname=self.config.DB_NAME
            )
        return self._connection
    
    def close(self):
        """关闭数据库连接"""
        if self._connection and not self._connection.closed:
            self._connection.close()
    
    # --------------------------------------------------------
    # Embedding 生成
    # --------------------------------------------------------
    def _get_embedding(self, text: str) -> List[float]:
        """
        生成文本的 embedding 向量
        
        参数:
            text: 输入文本
            
        返回:
            List[float]: 1536维向量
        """
        if not self.config.OPENAI_API_KEY:
            # 降级：返回零向量（仅用于测试）
            return [0.0] * self.config.EMBEDDING_DIMENSION
        
        try:
            response = openai.embeddings.create(
                model=self.config.EMBEDDING_MODEL,
                input=text,
                dimensions=self.config.EMBEDDING_DIMENSION
            )
            return response.data[0].embedding
        except Exception as e:
            print(f"[ERROR] Embedding 生成失败: {e}")
            # 降级：返回零向量
            return [0.0] * self.config.EMBEDDING_DIMENSION
    
    # --------------------------------------------------------
    # 记忆写入决策（Gatekeeper）
    # --------------------------------------------------------
    def should_remember(self, user_id: str, content: str, context: Dict = None) -> GatekeeperDecision:
        """
        记忆写入守门人 - 决定什么该记、什么该忘
        
        参数:
            user_id: 用户ID
            content: 内容
            context: 上下文信息
            
        返回:
            GatekeeperDecision: 决策结果
        """
        context = context or {}
        
        # 规则1：闲聊、寒暄、无信息量的内容 → 不记
        if self._is_chitchat(content):
            return GatekeeperDecision(
                remember=False,
                reason="chitchat"
            )
        
        # 规则2：用户明确表达的偏好 → 高优先级写入 user_profiles
        if preference := self._extract_preference(content):
            return GatekeeperDecision(
                remember=True,
                memory_type=MemoryType.PREFERENCE,
                importance=0.9,
                target="user_profiles",
                reason="explicit_preference"
            )
        
        # 规则3：技术事实、代码模式、调试经验 → 写入 memory_items
        if fact := self._extract_technical_fact(content, context):
            return GatekeeperDecision(
                remember=True,
                memory_type=MemoryType.SKILL,
                importance=self._calculate_importance(fact, context),
                target="memory_items",
                reason="technical_insight"
            )
        
        # 规则4：任务执行中的关键决策 → 写入 memory_items
        if context.get("task_outcome") == "success":
            return GatekeeperDecision(
                remember=True,
                memory_type=MemoryType.INSIGHT,
                importance=0.7,
                target="memory_items",
                reason="successful_pattern"
            )
        
        # 默认：不记录
        return GatekeeperDecision(
            remember=False,
            reason="low_signal"
        )
    
    def _is_chitchat(self, content: str) -> bool:
        """判断是否为闲聊内容"""
        chitchat_patterns = [
            "你好", "hello", "hi", "嗨",
            "谢谢", "thanks", "thank you",
            "再见", "bye", "goodbye",
            "好的", "ok", "okay",
        ]
        content_lower = content.lower()
        return any(pattern in content_lower for pattern in chitchat_patterns)
    
    def _extract_preference(self, content: str) -> Optional[str]:
        """提取用户偏好"""
        # 简单规则：包含"喜欢"、"偏好"等关键词
        preference_keywords = ["喜欢", "偏好", "prefer", "like", "习惯"]
        if any(keyword in content.lower() for keyword in preference_keywords):
            return content
        return None
    
    def _extract_technical_fact(self, content: str, context: Dict) -> Optional[str]:
        """提取技术事实"""
        # 简单规则：包含代码、技术术语等
        tech_keywords = ["代码", "函数", "类", "bug", "错误", "调试", "code", "function", "class"]
        if any(keyword in content.lower() for keyword in tech_keywords):
            return content
        return None
    
    def _calculate_importance(self, fact: str, context: Dict) -> float:
        """计算重要性评分"""
        # 简单规则：根据上下文调整
        base_score = 0.5
        
        # 任务成功 +0.2
        if context.get("task_outcome") == "success":
            base_score += 0.2
        
        # 复杂任务 +0.1
        if context.get("task_complexity", 0) > 0.7:
            base_score += 0.1
        
        return min(1.0, base_score)
    
    # --------------------------------------------------------
    # 记忆存储
    # --------------------------------------------------------
    def save_memory(self, memory: MemoryItem) -> str:
        """
        保存记忆到数据库
        
        参数:
            memory: 记忆对象
            
        返回:
            str: 记忆ID
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # 生成 embedding
            embedding = self._get_embedding(memory.content)
            
            # 插入记忆
            cursor.execute("""
                INSERT INTO memory_items (
                    user_id, content, summary, embedding, memory_type,
                    domain_tags, importance_score, activation_score, status
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                memory.user_id,
                memory.content,
                memory.summary,
                embedding,
                memory.memory_type.value,
                memory.domain_tags,
                memory.importance_score,
                memory.activation_score,
                memory.status.value
            ))
            
            memory_id = cursor.fetchone()[0]
            
            # 记录审计日志
            cursor.execute("""
                INSERT INTO memory_audit_log (user_id, memory_id, action, metadata)
                VALUES (%s, %s, %s, %s)
            """, (
                memory.user_id,
                memory_id,
                "create",
                Json({"content_preview": memory.content[:100]})
            ))
            
            conn.commit()
            return memory_id
            
        except Exception as e:
            conn.rollback()
            print(f"[ERROR] 保存记忆失败: {e}")
            raise
        finally:
            cursor.close()
    
    # --------------------------------------------------------
    # 记忆检索
    # --------------------------------------------------------
    def search_similar_memories(
        self,
        user_id: str,
        query: str,
        top_k: int = None,
        min_activation: float = None
    ) -> List[MemoryItem]:
        """
        向量相似度搜索
        
        参数:
            user_id: 用户ID
            query: 查询文本
            top_k: 返回数量
            min_activation: 最小激活度
            
        返回:
            List[MemoryItem]: 相似记忆列表
        """
        top_k = top_k or self.config.DEFAULT_TOP_K
        min_activation = min_activation or self.config.MIN_ACTIVATION_FOR_SEARCH
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # 生成查询 embedding
            query_embedding = self._get_embedding(query)
            
            # 调用数据库函数进行向量搜索
            cursor.execute("""
                SELECT * FROM search_similar_memories(%s, %s, %s, %s)
            """, (query_embedding, user_id, top_k, min_activation))
            
            results = []
            for row in cursor.fetchall():
                memory = MemoryItem(
                    id=str(row[0]),
                    user_id=user_id,
                    content=row[1],
                    summary=row[2],
                    memory_type=MemoryType(row[3]),
                    importance_score=row[4],
                    activation_score=row[5]
                )
                results.append(memory)
                
                # 访问即激活
                self._bump_activation(memory.id)
            
            return results
            
        except Exception as e:
            print(f"[ERROR] 搜索记忆失败: {e}")
            return []
        finally:
            cursor.close()
    
    def _bump_activation(self, memory_id: str):
        """提升记忆激活度"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT bump_memory_activation(%s)
            """, (memory_id,))
            conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"[WARN] 激活度提升失败: {e}")
        finally:
            cursor.close()
    
    # --------------------------------------------------------
    # 记忆上下文组装（Prompt 注入）
    # --------------------------------------------------------
    def build_memory_context(
        self,
        user_id: str,
        current_query: str,
        max_tokens: int = None
    ) -> str:
        """
        分层检索，按优先级注入记忆上下文
        
        参数:
            user_id: 用户ID
            current_query: 当前查询
            max_tokens: 最大 token 数
            
        返回:
            str: 组装后的记忆上下文
        """
        max_tokens = max_tokens or self.config.MAX_CONTEXT_TOKENS
        context_parts = []
        
        # 第一层：用户偏好（精确匹配）
        profile = self._get_user_profile(user_id)
        if profile:
            prefs = profile.get("global_preferences", {})
            if prefs:
                context_parts.append(f"【用户偏好】{json.dumps(prefs, ensure_ascii=False)}")
        
        # 第二层：语义相关记忆（向量检索）
        related = self.search_similar_memories(user_id, current_query, top_k=5)
        for mem in related:
            context_parts.append(f"【相关记忆】{mem.summary or mem.content[:200]}")
        
        # 第三层：近期高价值经验
        recent = self._get_recent_high_value(user_id, days=7, limit=3)
        for mem in recent:
            context_parts.append(f"【近期经验】{mem.content[:200]}")
        
        # 截断到 token 限制（简单按字符数估算）
        full_context = "\n\n".join(context_parts)
        return full_context[:max_tokens * 4]  # 粗略估算：1 token ≈ 4 字符
    
    def _get_user_profile(self, user_id: str) -> Optional[Dict]:
        """获取用户画像"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT global_preferences, domain_expertise
                FROM user_profiles
                WHERE user_id = %s
            """, (user_id,))
            
            row = cursor.fetchone()
            if row:
                return {
                    "global_preferences": row[0],
                    "domain_expertise": row[1]
                }
            return None
        except Exception as e:
            print(f"[ERROR] 获取用户画像失败: {e}")
            return None
        finally:
            cursor.close()
    
    def _get_recent_high_value(self, user_id: str, days: int, limit: int) -> List[MemoryItem]:
        """获取近期高价值记忆"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT id, content, summary, memory_type, importance_score
                FROM memory_items
                WHERE user_id = %s
                  AND status = 'active'
                  AND importance_score >= 0.7
                  AND created_at >= NOW() - INTERVAL '%s days'
                ORDER BY importance_score DESC, created_at DESC
                LIMIT %s
            """, (user_id, days, limit))
            
            results = []
            for row in cursor.fetchall():
                memory = MemoryItem(
                    id=str(row[0]),
                    user_id=user_id,
                    content=row[1],
                    summary=row[2],
                    memory_type=MemoryType(row[3]),
                    importance_score=row[4]
                )
                results.append(memory)
            
            return results
        except Exception as e:
            print(f"[ERROR] 获取近期记忆失败: {e}")
            return []
        finally:
            cursor.close()
    
    # --------------------------------------------------------
    # 生命周期管理（后台任务）
    # --------------------------------------------------------
    def decay_activation_scores(self):
        """
        激活度衰减（模拟遗忘曲线）
        建议：每小时执行一次
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            now = datetime.now(timezone.utc)
            
            # 最近1天
            cursor.execute("""
                UPDATE memory_items
                SET activation_score = activation_score * %s
                WHERE status = 'active'
                  AND last_accessed_at < %s
                  AND last_accessed_at >= %s
            """, (
                self.config.ACTIVATION_DECAY_RATE_1D,
                now - timedelta(days=1),
                now - timedelta(hours=1)
            ))
            
            # 1-7天
            cursor.execute("""
                UPDATE memory_items
                SET activation_score = activation_score * %s
                WHERE status = 'active'
                  AND last_accessed_at < %s
                  AND last_accessed_at >= %s
            """, (
                self.config.ACTIVATION_DECAY_RATE_7D,
                now - timedelta(days=7),
                now - timedelta(days=1)
            ))
            
            # 7-30天
            cursor.execute("""
                UPDATE memory_items
                SET activation_score = activation_score * %s
                WHERE status = 'active'
                  AND last_accessed_at < %s
                  AND last_accessed_at >= %s
            """, (
                self.config.ACTIVATION_DECAY_RATE_30D,
                now - timedelta(days=30),
                now - timedelta(days=7)
            ))
            
            # 60天以上
            cursor.execute("""
                UPDATE memory_items
                SET activation_score = activation_score * %s
                WHERE status = 'active'
                  AND last_accessed_at < %s
            """, (
                self.config.ACTIVATION_DECAY_RATE_60D,
                now - timedelta(days=60)
            ))
            
            conn.commit()
            print(f"[INFO] 激活度衰减任务完成 @ {now}")
            
        except Exception as e:
            conn.rollback()
            print(f"[ERROR] 激活度衰减失败: {e}")
        finally:
            cursor.close()
    
    def prune_memories(self):
        """
        自动剪枝（三层过滤网）
        建议：每天执行一次
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # 第一层：清除垃圾记忆（激活度<0.1 且 从未访问）
            cursor.execute("""
                UPDATE memory_items
                SET status = 'pruned'
                WHERE status = 'active'
                  AND activation_score < %s
                  AND access_count = 0
                  AND created_at < NOW() - INTERVAL '7 days'
            """, (self.config.PRUNE_ACTIVATION_THRESHOLD,))
            
            pruned_count = cursor.rowcount
            
            # 第二层：归档低价值记忆（激活度<0.2 且 创建>30天）
            cursor.execute("""
                UPDATE memory_items
                SET status = 'archived'
                WHERE status = 'active'
                  AND activation_score < %s
                  AND created_at < NOW() - INTERVAL '30 days'
            """, (self.config.ARCHIVE_ACTIVATION_THRESHOLD,))
            
            archived_count = cursor.rowcount
            
            conn.commit()
            print(f"[INFO] 剪枝任务完成：删除 {pruned_count} 条，归档 {archived_count} 条")
            
        except Exception as e:
            conn.rollback()
            print(f"[ERROR] 剪枝失败: {e}")
        finally:
            cursor.close()


# ============================================================
# 单例模式（全局访问点）
# ============================================================
_memory_service_instance = None

def get_memory_service() -> MemoryService:
    """获取记忆服务单例"""
    global _memory_service_instance
    if _memory_service_instance is None:
        _memory_service_instance = MemoryService()
    return _memory_service_instance


# ============================================================
# 测试入口
# ============================================================
if __name__ == "__main__":
    # 简单测试
    service = get_memory_service()
    
    # 测试守门人决策
    decision = service.should_remember(
        user_id="test_user",
        content="我喜欢使用 Python 进行开发",
        context={}
    )
    print(f"守门人决策: {decision}")
    
    # 测试保存记忆
    if decision.remember:
        memory = MemoryItem(
            user_id="test_user",
            content=decision.reason,
            memory_type=decision.memory_type,
            importance_score=decision.importance
        )
        memory_id = service.save_memory(memory)
        print(f"记忆已保存: {memory_id}")
    
    service.close()
