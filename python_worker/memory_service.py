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
import re
import requests
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import Json
from pgvector.psycopg2 import register_vector


# Load local memory DB credentials without overriding explicitly supplied
# process environment variables.
load_dotenv(Path(__file__).resolve().parents[2] / ".env.memory", override=False)

# Also load python_worker/.env for API keys (e.g. DASHSCOPE_API_KEY)
load_dotenv(Path(__file__).resolve().parent / ".env", override=False)


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
    
    # Embedding 提供商配置：dashscope / openai / none
    EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "dashscope").lower()
    
    # DashScope Embedding 配置（阿里云通义千问，国内首选）
    DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
    DASHSCOPE_EMBEDDING_MODEL = os.getenv("DASHSCOPE_EMBEDDING_MODEL", "text-embedding-v2")
    DASHSCOPE_EMBEDDING_URL = (
        "https://dashscope.aliyuncs.com/api/v1/services/embeddings/text-embedding/text-embedding"
    )
    
    # OpenAI Embedding 配置（备选）
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    OPENAI_EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
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
    RECENT_HIGH_VALUE_DAYS = 7
    RECENT_HIGH_VALUE_MIN_IMPORTANCE = 0.3
    RECENT_HIGH_VALUE_LIMIT = 3


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
        self._embedding_warning_emitted = False
        self._memory_items_has_updated_at = False
        self._has_search_function = False
        self._embedding_provider = self._resolve_embedding_provider()
    
    def _resolve_embedding_provider(self) -> str:
        """解析实际可用的 embedding 提供商"""
        provider = self.config.EMBEDDING_PROVIDER
        
        if provider == "dashscope":
            if self.config.DASHSCOPE_API_KEY:
                return "dashscope"
            else:
                print("[MEMORY] ⚠️ EMBEDDING_PROVIDER=dashscope 但 DASHSCOPE_API_KEY 未配置，"
                      "尝试回退到 OpenAI")
                if self.config.OPENAI_API_KEY:
                    return "openai"
        
        if provider == "openai":
            if self.config.OPENAI_API_KEY:
                return "openai"
            else:
                print("[MEMORY] ⚠️ EMBEDDING_PROVIDER=openai 但 OPENAI_API_KEY 未配置，"
                      "尝试回退到 DashScope")
                if self.config.DASHSCOPE_API_KEY:
                    return "dashscope"
        
        if provider == "none":
            return "none"
        
        # 自动检测：优先 DashScope（国内），其次 OpenAI
        if self.config.DASHSCOPE_API_KEY:
            return "dashscope"
        if self.config.OPENAI_API_KEY:
            return "openai"
        
        return "none"
    
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
            connection = psycopg2.connect(
                host=self.config.DB_HOST,
                port=self.config.DB_PORT,
                user=self.config.DB_USER,
                password=self.config.DB_PASSWORD,
                dbname=self.config.DB_NAME
            )
            try:
                register_vector(connection)
                self._detect_memory_schema(connection)
            except Exception:
                connection.close()
                raise
            self._connection = connection
        return self._connection

    def _detect_memory_schema(self, connection) -> None:
        """Detect optional columns and functions to keep writes compatible with older schemas."""
        cursor = connection.cursor()
        try:
            cursor.execute("""
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_schema = current_schema()
                      AND table_name = 'memory_items'
                      AND column_name = 'updated_at'
                )
            """)
            self._memory_items_has_updated_at = bool(cursor.fetchone()[0])

            cursor.execute("""
                SELECT EXISTS (
                    SELECT 1
                    FROM pg_proc p
                    WHERE p.proname = 'search_similar_memories'
                      AND p.pronamespace IN (
                          SELECT oid FROM pg_namespace
                          WHERE nspname IN ('public', current_schema())
                      )
                )
            """)
            self._has_search_function = bool(cursor.fetchone()[0])
            if not self._has_search_function:
                print(
                    "[MEMORY] ⚠️ 数据库中未找到 search_similar_memories 函数，"
                    "语义向量搜索不可用。"
                )
                print(
                    "[MEMORY] 💡 请运行 init_memory_schema.sql 初始化数据库："
                    "psql -U alphapilot -d alphapilot_memory -f init_memory_schema.sql"
                )
            connection.commit()
        finally:
            cursor.close()
    
    def close(self):
        """关闭数据库连接"""
        if self._connection and not self._connection.closed:
            self._connection.close()
    
    # --------------------------------------------------------
    # Embedding 生成
    # --------------------------------------------------------
    def _get_embedding(self, text: str) -> Optional[List[float]]:
        """
        生成文本的 embedding 向量（多提供商支持）
        
        参数:
            text: 输入文本
            
        返回:
            List[float]: 1536维向量
        """
        if self._embedding_provider == "none":
            self._warn_embedding_unavailable(
                "未配置任何 embedding 提供商（DASHSCOPE_API_KEY / OPENAI_API_KEY）"
            )
            return None
        
        if self._embedding_provider == "dashscope":
            return self._get_embedding_dashscope(text)
        
        if self._embedding_provider == "openai":
            return self._get_embedding_openai(text)
        
        self._warn_embedding_unavailable(f"未知的 embedding 提供商: {self._embedding_provider}")
        return None
    
    def _get_embedding_dashscope(self, text: str) -> Optional[List[float]]:
        """通过 DashScope API 生成 embedding（text-embedding-v2, 1536维）"""
        try:
            response = requests.post(
                self.config.DASHSCOPE_EMBEDDING_URL,
                headers={
                    "Authorization": f"Bearer {self.config.DASHSCOPE_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.config.DASHSCOPE_EMBEDDING_MODEL,
                    "input": {"texts": [text]},
                },
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get("output") and data["output"].get("embeddings"):
                embedding = data["output"]["embeddings"][0].get("embedding")
                if embedding:
                    return embedding
            
            error_msg = data.get("message", "未知错误")
            self._warn_embedding_unavailable(f"DashScope 返回异常: {error_msg}")
            return None
            
        except requests.Timeout:
            self._warn_embedding_unavailable("DashScope Embedding 请求超时（APITimeoutError）")
            return None
        except requests.RequestException as error:
            self._warn_embedding_unavailable(
                f"DashScope Embedding 请求失败（{type(error).__name__}）"
            )
            return None
    
    def _get_embedding_openai(self, text: str) -> Optional[List[float]]:
        """通过 OpenAI API 生成 embedding"""
        try:
            import openai
            client = openai.OpenAI(api_key=self.config.OPENAI_API_KEY)
            response = client.embeddings.create(
                model=self.config.OPENAI_EMBEDDING_MODEL,
                input=text,
                dimensions=self.config.EMBEDDING_DIMENSION,
            )
            return response.data[0].embedding
        except Exception as error:
            self._warn_embedding_unavailable(
                f"OpenAI Embedding 请求失败（{type(error).__name__}）"
            )
            return None

    def _warn_embedding_unavailable(self, reason: str) -> None:
        if self._embedding_warning_emitted:
            return
        self._embedding_warning_emitted = True
        print(
            f"[MEMORY] WARNING: {reason}；语义向量检索暂不可用，"
            "将继续保存记忆并通过近期经验层召回。"
        )
    
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
        chitchat_patterns = {
            "你好", "hello", "hi", "嗨",
            "谢谢", "thanks", "thank you",
            "再见", "bye", "goodbye",
            "好的", "ok", "okay",
        }
        normalized = content.strip().lower().strip(" \t\r\n!！?？.,，。")
        return normalized in chitchat_patterns
    
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
            updated_at_update = (
                ",\n                    updated_at = NOW()"
                if self._memory_items_has_updated_at
                else ""
            )
            
            # 插入记忆
            cursor.execute(f"""
                INSERT INTO memory_items (
                    user_id, content, summary, embedding, memory_type,
                    domain_tags, importance_score, activation_score, status
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
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
            saved_row = cursor.fetchone()
            if saved_row is None:
                cursor.execute(f"""
                    UPDATE memory_items
                    SET status = 'active',
                        importance_score = GREATEST(importance_score, %s),
                        activation_score = GREATEST(activation_score, %s),
                        embedding = COALESCE(%s, embedding),
                        summary = COALESCE(%s, summary),
                        last_accessed_at = NOW(){updated_at_update}
                    WHERE user_id = %s
                      AND memory_type = %s
                      AND content = %s
                    RETURNING id
                """, (
                    memory.importance_score,
                    memory.activation_score,
                    embedding,
                    memory.summary,
                    memory.user_id,
                    memory.memory_type.value,
                    memory.content,
                ))
                saved_row = cursor.fetchone()
                if saved_row is None:
                    raise RuntimeError(
                        "记忆插入发生唯一键冲突，但无法定位现有记忆记录。"
                    )

            memory_id = saved_row[0]
            
            # 记录审计日志
            cursor.execute("""
                INSERT INTO memory_audit_log (user_id, memory_id, action, metadata)
                VALUES (%s, %s, %s, %s)
            """, (
                memory.user_id,
                memory_id,
                "upsert",
                Json({"content_preview": memory.content[:100]})
            ))
            
            conn.commit()
            if embedding is None:
                print(
                    "[MEMORY] 记忆已持久化，但没有向量索引；"
                    "有效期内可通过近期经验层召回。"
                )
            return memory_id
            
        except Exception as e:
            conn.rollback()
            print(f"[ERROR] 保存记忆失败: {e}")
            raise
        finally:
            cursor.close()

    def save_user_preference(self, user_id: str, preference: str) -> None:
        """Persist explicit preferences in the exact-match profile tier."""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO user_profiles (user_id, global_preferences, domain_expertise)
                VALUES (
                    %s,
                    jsonb_build_object('declared_preferences', jsonb_build_array(%s)),
                    '[]'::jsonb
                )
                ON CONFLICT (user_id) DO UPDATE
                SET global_preferences = jsonb_set(
                    COALESCE(user_profiles.global_preferences, '{}'::jsonb),
                    '{declared_preferences}',
                    (
                        SELECT COALESCE(jsonb_agg(to_jsonb(pref) ORDER BY pref), '[]'::jsonb)
                        FROM (
                            SELECT DISTINCT pref
                            FROM jsonb_array_elements_text(
                                COALESCE(
                                    user_profiles.global_preferences->'declared_preferences',
                                    '[]'::jsonb
                                ) || jsonb_build_array(%s)
                            ) AS preferences(pref)
                        ) AS unique_preferences
                    ),
                    true
                )
            """, (user_id, preference, preference))
            cursor.execute("""
                INSERT INTO memory_audit_log (user_id, action, metadata)
                VALUES (%s, 'preference_upsert', %s)
            """, (user_id, Json({"preference": preference[:100]})))
            conn.commit()
        except Exception:
            conn.rollback()
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

        如果数据库未初始化向量搜索函数，自动降级为关键词匹配搜索。
        
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
            query_embedding = self._get_embedding(query)

            if query_embedding is not None and self._has_search_function:
                cursor.execute("""
                    SELECT * FROM search_similar_memories(%s::vector(1536), %s, %s, %s)
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
                    self._bump_activation(memory.id)

                if results:
                    return results

            if not self._has_search_function:
                print(
                    "[MEMORY] 向量搜索不可用，使用关键词匹配作为降级方案"
                )

            results = self._keyword_search_memories(
                user_id, query, top_k, min_activation
            )
            return results

        except Exception as e:
            print(f"[ERROR] 向量搜索失败 (降级到关键词搜索): {e}")
            try:
                conn.rollback()
                results = self._keyword_search_memories(
                    user_id, query, top_k, min_activation
                )
                return results
            except Exception as fallback_error:
                print(f"[ERROR] 关键词搜索也失败: {fallback_error}")
                return []
        finally:
            cursor.close()

    def _keyword_search_memories(
        self,
        user_id: str,
        query: str,
        top_k: int,
        min_activation: float
    ) -> List[MemoryItem]:
        """关键词匹配搜索，作为向量搜索不可用时的降级方案"""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            keywords = [
                kw for kw in re.findall(r'[\u4e00-\u9fff]{2,}|[a-zA-Z]{3,}', query)
                if len(kw) >= 2
            ]
            if not keywords:
                return []

            like_clauses = []
            params = [user_id]
            for kw in keywords[:5]:
                safe_kw = kw.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
                like_clauses.append('m.content ILIKE %s')
                params.append(f'%{safe_kw}%')

            where_clause = ' OR '.join(like_clauses)

            sql = f"""
                SELECT m.id, m.content, m.summary, m.memory_type,
                       m.importance_score, m.activation_score
                FROM memory_items m
                WHERE m.user_id = %s
                  AND m.status = 'active'
                  AND ({where_clause})
                ORDER BY m.importance_score DESC, m.last_accessed_at DESC NULLS LAST
                LIMIT %s
            """
            params.append(top_k)

            cursor.execute(sql, params)

            results = []
            rows = cursor.fetchall()
            for row in rows:
                memory = MemoryItem(
                    id=str(row[0]),
                    user_id=user_id,
                    content=str(row[1] or ''),
                    summary=str(row[2] or ''),
                    memory_type=MemoryType(row[3]) if row[3] else MemoryType.INSIGHT,
                    importance_score=float(row[4] or 0),
                    activation_score=float(row[5] or 0)
                )
                results.append(memory)

            return results
        except Exception as e:
            import traceback
            conn.rollback()
            print(f"[ERROR] 关键词搜索失败: {e}")
            traceback.print_exc()
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
        related = self.search_similar_memories(
            user_id,
            current_query,
            top_k=self.config.DEFAULT_TOP_K,
        )
        included_memory_ids = set()
        for mem in related:
            included_memory_ids.add(mem.id)
            context_parts.append(f"【相关记忆】{mem.summary or mem.content[:200]}")
        
        # 第三层：近期高价值经验
        recent = self._get_recent_high_value(
            user_id,
            days=self.config.RECENT_HIGH_VALUE_DAYS,
            min_importance=self.config.RECENT_HIGH_VALUE_MIN_IMPORTANCE,
            limit=self.config.RECENT_HIGH_VALUE_LIMIT,
        )
        for mem in recent:
            if mem.id in included_memory_ids:
                continue
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
            conn.rollback()
            print(f"[ERROR] 获取用户画像失败: {e}")
            return None
        finally:
            cursor.close()
    
    def _get_recent_high_value(
        self,
        user_id: str,
        days: int,
        min_importance: float,
        limit: int
    ) -> List[MemoryItem]:
        """获取近期高价值记忆"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT id, content, summary, memory_type, importance_score
                FROM memory_items
                WHERE user_id = %s
                  AND status = 'active'
                  AND importance_score >= %s
                  AND created_at >= NOW() - make_interval(days => %s)
                ORDER BY importance_score DESC, created_at DESC
                LIMIT %s
            """, (user_id, min_importance, days, limit))
            
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
            conn.rollback()
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