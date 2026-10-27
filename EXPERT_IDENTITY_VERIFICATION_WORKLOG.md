# AlphaPilot 专家身份验证系统 - 实施工作日志

## 📋 项目概述

**目标**: 为 AlphaPilot 添加专家身份验证和能力认证机制，确保 AI 专家人格和技能的合理使用。

**核心原则**:
- 以 `qwen_worker_v2` 为主线实施
- 其他 Worker (Doubao/DeepSeek/Gemini) 可后续扩展
- 保持向后兼容，不影响现有功能
- 渐进式实施，每个阶段独立验证

**预期效果**:
- ✅ 用户无相关经验时，限制使用高级专家人格
- ✅ 技能路由前验证用户能力，动态调整指导
- ✅ 项目深度分析，提取复杂度和领域元数据
- ✅ 智能推荐最合适的专家人格

---

## 🎯 实施路线图

### Phase 1: Persona 验证层（优先级：🔴 最高）
**时间估算**: 1-2 天
**风险**: 低（不破坏现有流程）

### Phase 2: Skill 能力验证（优先级：🟠 高）
**时间估算**: 1-2 天
**风险**: 中（可能影响 Skill 路由）

### Phase 3: 项目深度分析（优先级：🟡 中）
**时间估算**: 2-3 天
**风险**: 低（独立模块）

### Phase 4: 智能专家匹配（优先级：🟢 低）
**时间估算**: 1-2 天
**风险**: 低（可选功能）

---

## 📝 Phase 1: Persona 验证层

### 目标
创建专家身份验证器，在用户使用高级人格前检查其资格。

### 文件清单

**新增文件**:
```
python_worker/
├── persona_verifier.py          # ⭐ 新增：专家身份验证器
└── tests/
    └── test_persona_verifier.py # ⭐ 新增：验证器单元测试
```

**修改文件**:
```
python_worker/agents/qwen/
├── qwen_worker_v2.py            # 🔧 修改：集成验证器
└── personas.py                  # 🔧 修改：添加验证规则元数据
```

### 具体任务

#### Task 1.1: 创建 PersonaVerifier 类

**文件**: `python_worker/persona_verifier.py`

**代码结构**:
```python
# -*- coding: utf-8 -*-
"""
AlphaPilot 专家身份验证器
职责：验证用户是否有资格使用指定专家人格
"""

from typing import Dict, Tuple, Optional
from dataclasses import dataclass

@dataclass
class PersonaRequirement:
    """人格使用要求"""
    min_project_complexity: float = 0.0      # 最低项目复杂度
    required_skills: Tuple[str, ...] = ()    # 必备技能关键词
    required_project_features: Tuple[str, ...] = ()  # 必备项目特征
    fallback_persona: str = "engineer"        # 不满足时降级人格


class PersonaVerifier:
    """专家身份验证器"""
    
    def __init__(self, memory_service=None):
        """
        初始化验证器
        
        参数:
            memory_service: MemoryService 实例（可选，用于查询用户历史）
        """
        self.memory = memory_service
        self._requirements = self._load_requirements()
    
    def _load_requirements(self) -> Dict[str, PersonaRequirement]:
        """加载各人格的使用要求"""
        return {
            "architect": PersonaRequirement(
                min_project_complexity=0.7,
                required_skills=("架构", "design", "architecture"),
                required_project_features=("has_code",),
                fallback_persona="engineer"
            ),
            "reviewer": PersonaRequirement(
                min_project_complexity=0.0,
                required_skills=("代码审查", "review", "code quality"),
                required_project_features=("has_code",),
                fallback_persona="engineer"
            ),
            "frontend": PersonaRequirement(
                min_project_complexity=0.0,
                required_skills=("前端", "frontend", "react", "vue"),
                required_project_features=("has_frontend",),
                fallback_persona="engineer"
            ),
            # 默认工程师人格无限制
            "engineer": PersonaRequirement(
                min_project_complexity=0.0,
                required_skills=(),
                required_project_features=(),
                fallback_persona="engineer"
            )
        }
    
    def verify_persona_access(
        self,
        user_id: str,
        persona_type: str,
        project_context: Dict,
        verbose: bool = False
    ) -> Tuple[bool, str, Optional[str]]:
        """
        验证用户是否有资格使用指定专家人格
        
        参数:
            user_id: 用户ID
            persona_type: 人格类型 (architect/reviewer/frontend/engineer)
            project_context: 项目上下文 {
                "complexity_score": float,
                "has_code": bool,
                "has_frontend": bool,
                "file_count": int,
                ...
            }
            verbose: 是否打印详细日志
        
        返回:
            (是否允许, 拒绝原因, 降级人格)
        """
        # 1. 检查人格是否存在
        if persona_type not in self._requirements:
            if verbose:
                print(f"[PersonaVerifier] ⚠️ 未知人格: {persona_type}")
            return True, "", "engineer"
        
        requirement = self._requirements[persona_type]
        
        # 2. 检查项目复杂度
        complexity = project_context.get("complexity_score", 0.0)
        if complexity < requirement.min_project_complexity:
            reason = (
                f"项目复杂度 ({complexity:.2f}) 低于要求 "
                f"({requirement.min_project_complexity:.2f})"
            )
            if verbose:
                print(f"[PersonaVerifier] ❌ {persona_type}: {reason}")
            return False, reason, requirement.fallback_persona
        
        # 3. 检查项目特征
        for feature in requirement.required_project_features:
            if not project_context.get(feature, False):
                reason = f"项目缺少必需特征: {feature}"
                if verbose:
                    print(f"[PersonaVerifier] ❌ {persona_type}: {reason}")
                return False, reason, requirement.fallback_persona
        
        # 4. 检查用户技能（如果有 Memory Service）
        if self.memory and requirement.required_skills:
            has_skill = self._check_user_skill(
                user_id, 
                requirement.required_skills
            )
            if not has_skill:
                reason = f"用户缺乏相关经验: {requirement.required_skills}"
                if verbose:
                    print(f"[PersonaVerifier] ❌ {persona_type}: {reason}")
                return False, reason, requirement.fallback_persona
        
        # 5. 验证通过
        if verbose:
            print(f"[PersonaVerifier] ✅ {persona_type}: 验证通过")
        return True, "", None
    
    def _check_user_skill(self, user_id: str, skill_keywords: Tuple[str, ...]) -> bool:
        """
        检查用户是否具备指定技能（基于 Memory Service）
        
        参数:
            user_id: 用户ID
            skill_keywords: 技能关键词元组
        
        返回:
            bool: 是否具备技能
        """
        try:
            # 查询用户技能记忆
            user_memories = self.memory.query_user_memories(
                user_id,
                memory_type="skill",
                limit=20
            )
            
            # 检查是否包含任一关键词
            for memory in user_memories:
                content = memory.content.lower()
                if any(keyword.lower() in content for keyword in skill_keywords):
                    return True
            
            return False
        except Exception as e:
            # Memory Service 不可用时，保守策略：允许通过
            print(f"[PersonaVerifier] ⚠️ Memory Service 查询失败: {e}")
            return True
    
    def get_persona_requirements(self, persona_type: str) -> Optional[PersonaRequirement]:
        """获取人格的使用要求"""
        return self._requirements.get(persona_type)
    
    def list_all_personas(self) -> Dict[str, PersonaRequirement]:
        """列出所有人格及其要求"""
        return self._requirements.copy()


# ============================================================
# 单例模式：全局验证器实例
# ============================================================
_global_verifier: Optional[PersonaVerifier] = None

def get_persona_verifier(memory_service=None) -> PersonaVerifier:
    """获取全局验证器实例（单例模式）"""
    global _global_verifier
    if _global_verifier is None:
        _global_verifier = PersonaVerifier(memory_service)
    return _global_verifier
```

#### Task 1.2: 集成到 qwen_worker_v2.py

**文件**: `python_worker/agents/qwen/qwen_worker_v2.py`

**修改点 1**: 导入验证器
```python
# 在文件顶部添加导入
from python_worker.persona_verifier import get_persona_verifier
```

**修改点 2**: 在 `create_steps_from_chain` 函数中添加验证
```python
def create_steps_from_chain(execution_chain: list, prompt: str, persona: str, intent: str = None) -> list:
    """
    v3.0：根据执行链动态生成步骤定义。
    - 不在这里做复杂逻辑，复杂逻辑交给各 step_xxx.py
    """
    
    # ⭐ 新增：Persona 验证
    try:
        verifier = get_persona_verifier()
        
        # 构建项目上下文（简化版，后续 Phase 3 会增强）
        project_context = {
            "complexity_score": 0.5,  # 默认中等复杂度
            "has_code": True,         # 默认有代码
            "has_frontend": False,    # 默认无前端
            "file_count": 10
        }
        
        # 验证人格访问权限
        user_id = "default_user"  # TODO: 从 task 获取真实 user_id
        allowed, reason, fallback = verifier.verify_persona_access(
            user_id=user_id,
            persona_type=persona,
            project_context=project_context,
            verbose=True
        )
        
        if not allowed:
            print(f"[Worker] ⚠️ Persona 降级: {persona} → {fallback} ({reason})")
            persona = fallback  # 降级到推荐人格
    except Exception as e:
        print(f"[Worker] ⚠️ Persona 验证失败，使用原人格: {e}")
        # 验证失败时不影响原有流程
    
    # 继续原有流程...
    steps = []
    step_templates = {
        # ... 原有代码
    }
    # ...
```

#### Task 1.3: 编写单元测试

**文件**: `python_worker/tests/test_persona_verifier.py`

```python
# -*- coding: utf-8 -*-
"""
PersonaVerifier 单元测试
"""

import pytest
from python_worker.persona_verifier import PersonaVerifier, PersonaRequirement


def test_architect_requires_high_complexity():
    """测试架构师人格需要高复杂度项目"""
    verifier = PersonaVerifier()
    
    # 低复杂度项目
    context = {"complexity_score": 0.3, "has_code": True}
    allowed, reason, fallback = verifier.verify_persona_access(
        user_id="test_user",
        persona_type="architect",
        project_context=context
    )
    
    assert not allowed
    assert "复杂度" in reason
    assert fallback == "engineer"


def test_architect_allowed_with_high_complexity():
    """测试高复杂度项目允许使用架构师人格"""
    verifier = PersonaVerifier()
    
    # 高复杂度项目
    context = {"complexity_score": 0.8, "has_code": True}
    allowed, reason, fallback = verifier.verify_persona_access(
        user_id="test_user",
        persona_type="architect",
        project_context=context
    )
    
    assert allowed
    assert reason == ""
    assert fallback is None


def test_engineer_persona_no_restrictions():
    """测试工程师人格无限制"""
    verifier = PersonaVerifier()
    
    # 任何项目都可以使用工程师人格
    context = {"complexity_score": 0.0, "has_code": False}
    allowed, reason, fallback = verifier.verify_persona_access(
        user_id="test_user",
        persona_type="engineer",
        project_context=context
    )
    
    assert allowed
    assert reason == ""


def test_unknown_persona_allowed():
    """测试未知人格默认允许"""
    verifier = PersonaVerifier()
    
    context = {"complexity_score": 0.5}
    allowed, reason, fallback = verifier.verify_persona_access(
        user_id="test_user",
        persona_type="unknown_persona",
        project_context=context
    )
    
    assert allowed
    assert fallback == "engineer"


def test_reviewer_requires_code():
    """测试审查者人格需要项目有代码"""
    verifier = PersonaVerifier()
    
    # 无代码项目
    context = {"complexity_score": 0.5, "has_code": False}
    allowed, reason, fallback = verifier.verify_persona_access(
        user_id="test_user",
        persona_type="reviewer",
        project_context=context
    )
    
    assert not allowed
    assert "has_code" in reason
    assert fallback == "engineer"


def test_memory_service_integration():
    """测试 Memory Service 集成（需要 mock）"""
    # TODO: 实现 Memory Service mock 测试
    pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

### 验证方法

```bash
# 1. 运行单元测试
cd D:\Copilot_Alphapilot\Copilot_Alphapilot
.venv_worker\Scripts\python.exe -m pytest python_worker/tests/test_persona_verifier.py -v

# 2. 集成测试：使用 qwen_worker_v2 提交任务
.venv_worker\Scripts\python.exe test_qwen_worker_v2.py

# 3. 观察日志输出
# 预期看到:
# [PersonaVerifier] ✅ architect: 验证通过
# 或
# [PersonaVerifier] ❌ architect: 项目复杂度 (0.30) 低于要求 (0.70)
# [Worker] ⚠️ Persona 降级: architect → engineer
```

### 风险评估

**风险**: 低
- 不修改核心执行逻辑
- 验证失败时有安全降级机制
- 可通过配置开关禁用

**回滚方案**:
```python
# 在 qwen_worker_v2.py 中添加开关
ENABLE_PERSONA_VERIFICATION = os.getenv("ENABLE_PERSONA_VERIFICATION", "true").lower() == "true"

if ENABLE_PERSONA_VERIFICATION:
    # 执行验证
```

---

## 📝 Phase 2: Skill 能力验证

### 目标
在 Skill 路由后验证用户能力，动态调整 Skill 的 guidance。

### 文件清单

**新增文件**:
```
python_worker/
├── skill_verifier.py             # ⭐ 新增：技能能力验证器
└── tests/
    └── test_skill_verifier.py    # ⭐ 新增：验证器单元测试
```

**修改文件**:
```
python_worker/skills/
├── router.py                     # 🔧 修改：集成验证器
└── base.py                       # 🔧 修改：Skill 支持动态增强
```

### 具体任务

#### Task 2.1: 创建 SkillVerifier 类

**文件**: `python_worker/skill_verifier.py`

```python
# -*- coding: utf-8 -*-
"""
AlphaPilot 技能能力验证器
职责：验证用户是否具备使用指定 Skill 的能力，动态增强指导
"""

from typing import Dict, Tuple, Optional
from dataclasses import dataclass, replace


@dataclass
class SkillEnhancement:
    """Skill 动态增强配置"""
    additional_guidance: str = ""      # 额外指导
    warning_message: str = ""          # 警告信息
    complexity_adjustment: int = 0     # 复杂度调整 (-5 到 +5)


class SkillVerifier:
    """技能能力验证器"""
    
    def __init__(self, memory_service=None):
        """
        初始化验证器
        
        参数:
            memory_service: MemoryService 实例（可选）
        """
        self.memory = memory_service
        self._skill_rules = self._load_skill_rules()
    
    def _load_skill_rules(self) -> Dict[str, Dict]:
        """加载各 Skill 的验证规则"""
        return {
            "docker.container": {
                "required_keywords": ("docker", "container", "dockerfile"),
                "min_project_files": 1,
                "first_time_guidance": (
                    "⚠️ 提醒：这是您的首次 Docker 任务，"
                    "请提供详细的注释和最佳实践说明。"
                )
            },
            "database.sql": {
                "required_keywords": ("sql", "database", "mysql", "postgresql"),
                "required_project_files": ("db", "sql", "migration"),
                "min_project_files": 1,
                "first_time_guidance": (
                    "⚠️ 提醒：请确保 SQL 语句符合数据库规范，"
                    "提供事务处理和错误处理建议。"
                )
            },
            "frontend.ui": {
                "required_keywords": ("react", "vue", "angular", "frontend", "ui"),
                "required_project_files": ("component", "view", "page"),
                "min_project_files": 1,
                "first_time_guidance": (
                    "⚠️ 提醒：请遵循 React/Vue 最佳实践，"
                    "注意组件复用和状态管理。"
                )
            },
            "backend.python": {
                "required_keywords": ("python", "flask", "fastapi", "django"),
                "min_project_files": 0,  # Python 技能无硬性要求
                "first_time_guidance": ""
            }
        }
    
    def verify_skill_capability(
        self,
        user_id: str,
        skill_id: str,
        workspace_context: Dict,
        verbose: bool = False
    ) -> Tuple[bool, str, Optional[SkillEnhancement]]:
        """
        验证用户是否具备使用该 Skill 的能力
        
        参数:
            user_id: 用户ID
            skill_id: Skill ID
            workspace_context: 工作区上下文 {
                "file_count": int,
                "database_files": List[str],
                "frontend_files": List[str],
                ...
            }
            verbose: 是否打印详细日志
        
        返回:
            (是否允许, 拒绝原因, 增强配置)
        """
        # 1. 检查 Skill 是否有验证规则
        if skill_id not in self._skill_rules:
            if verbose:
                print(f"[SkillVerifier] ℹ️ {skill_id}: 无验证规则，直接允许")
            return True, "", None
        
        rule = self._skill_rules[skill_id]
        
        # 2. 检查项目文件要求
        if rule.get("min_project_files", 0) > 0:
            file_count = workspace_context.get("file_count", 0)
            if file_count < rule["min_project_files"]:
                reason = f"项目文件数 ({file_count}) 不足 ({rule['min_project_files']})"
                if verbose:
                    print(f"[SkillVerifier] ❌ {skill_id}: {reason}")
                return False, reason, None
        
        # 3. 检查必需文件类型
        required_files = rule.get("required_project_files", ())
        if required_files:
            has_required = self._check_required_files(
                workspace_context,
                required_files
            )
            if not has_required:
                reason = f"项目缺少必需文件类型: {required_files}"
                if verbose:
                    print(f"[SkillVerifier] ❌ {skill_id}: {reason}")
                return False, reason, None
        
        # 4. 检查用户技能历史（如果有 Memory Service）
        enhancement = None
        if self.memory and rule.get("required_keywords"):
            has_skill = self._check_user_skill(
                user_id,
                rule["required_keywords"]
            )
            if not has_skill:
                # 首次使用该技能，添加增强指导
                enhancement = SkillEnhancement(
                    additional_guidance=rule.get("first_time_guidance", ""),
                    warning_message="检测到您首次使用此技能，已增强指导"
                )
                if verbose:
                    print(f"[SkillVerifier] ⚠️ {skill_id}: 首次使用，增强指导")
            else:
                if verbose:
                    print(f"[SkillVerifier] ✅ {skill_id}: 用户有相关经验")
        
        # 5. 验证通过
        if verbose and not enhancement:
            print(f"[SkillVerifier] ✅ {skill_id}: 验证通过")
        
        return True, "", enhancement
    
    def _check_required_files(self, workspace_context: Dict, required_keywords: Tuple[str, ...]) -> bool:
        """检查项目是否包含必需文件类型"""
        all_files = workspace_context.get("all_files", [])
        file_names = [f.lower() for f in all_files]
        
        for keyword in required_keywords:
            if any(keyword in name for name in file_names):
                return True
        
        return False
    
    def _check_user_skill(self, user_id: str, skill_keywords: Tuple[str, ...]) -> bool:
        """检查用户是否具备指定技能（基于 Memory Service）"""
        try:
            user_memories = self.memory.query_user_memories(
                user_id,
                memory_type="skill",
                limit=20
            )
            
            for memory in user_memories:
                content = memory.content.lower()
                if any(keyword.lower() in content for keyword in skill_keywords):
                    return True
            
            return False
        except Exception as e:
            print(f"[SkillVerifier] ⚠️ Memory Service 查询失败: {e}")
            return True  # 保守策略：允许通过
    
    def apply_enhancement(self, skill, enhancement: SkillEnhancement):
        """
        将增强配置应用到 Skill
        
        参数:
            skill: Skill 对象
            enhancement: 增强配置
        
        返回:
            增强后的 Skill 对象
        """
        if not enhancement:
            return skill
        
        # 合并 guidance
        new_guidance = skill.guidance + "\n\n" + enhancement.additional_guidance
        
        # 使用 dataclasses.replace 创建新对象
        return replace(skill, guidance=new_guidance)


# ============================================================
# 单例模式：全局验证器实例
# ============================================================
_global_verifier: Optional[SkillVerifier] = None

def get_skill_verifier(memory_service=None) -> SkillVerifier:
    """获取全局验证器实例（单例模式）"""
    global _global_verifier
    if _global_verifier is None:
        _global_verifier = SkillVerifier(memory_service)
    return _global_verifier
```

#### Task 2.2: 修改 Skill 路由器

**文件**: `python_worker/skills/router.py`

**修改点**: 在 `route` 方法中添加验证
```python
class SkillRegistry:
    def __init__(self):
        self._skills: Dict[str, Skill] = {}
        self._verifier = None  # 延迟初始化
    
    def set_verifier(self, verifier):
        """设置验证器"""
        self._verifier = verifier
    
    def route(self, prompt: str, user_id: str = None, workspace_context: Dict = None) -> Optional[Skill]:
        if not isinstance(prompt, str) or not prompt.strip():
            return None

        # 原有路由逻辑
        matches = [
            (skill, skill.match_count(prompt))
            for skill in self._skills.values()
            if skill.match_count(prompt) > 0
        ]
        if not matches:
            return None
        matches.sort(key=lambda item: (-item[0].priority, -item[1], item[0].id))
        skill = matches[0][0]
        
        # ⭐ 新增：验证技能能力
        if self._verifier and user_id and workspace_context:
            try:
                allowed, reason, enhancement = self._verifier.verify_skill_capability(
                    user_id=user_id,
                    skill_id=skill.id,
                    workspace_context=workspace_context,
                    verbose=True
                )
                
                if not allowed:
                    print(f"[SkillRouter] ❌ 拒绝 {skill.id}: {reason}")
                    return None  # 拒绝该 Skill
                
                if enhancement:
                    print(f"[SkillRouter] ⚠️ 增强 {skill.id}: {enhancement.warning_message}")
                    skill = self._verifier.apply_enhancement(skill, enhancement)
            except Exception as e:
                print(f"[SkillRouter] ⚠️ Skill 验证失败: {e}")
        
        return skill
```

#### Task 2.3: 修改 qwen_worker_v2.py 初始化验证器

**文件**: `python_worker/agents/qwen/qwen_worker_v2.py`

**修改点**: 在 Worker 初始化时设置验证器
```python
# 在 Worker 类的 __init__ 或初始化代码中
from python_worker.skills import get_registry
from python_worker.skill_verifier import get_skill_verifier

# 初始化 Skill 验证器
try:
    skill_verifier = get_skill_verifier(memory_service)
    get_registry().set_verifier(skill_verifier)
    print("[Worker] ✅ Skill 验证器已启用")
except Exception as e:
    print(f"[Worker] ⚠️ Skill 验证器初始化失败: {e}")
```

#### Task 2.4: 编写单元测试

**文件**: `python_worker/tests/test_skill_verifier.py`

```python
# -*- coding: utf-8 -*-
"""
SkillVerifier 单元测试
"""

import pytest
from python_worker.skill_verifier import SkillVerifier, SkillEnhancement


def test_docker_requires_files():
    """测试 Docker 技能需要项目文件"""
    verifier = SkillVerifier()
    
    # 无文件项目
    context = {"file_count": 0}
    allowed, reason, enhancement = verifier.verify_skill_capability(
        user_id="test_user",
        skill_id="docker.container",
        workspace_context=context
    )
    
    assert not allowed
    assert "文件数" in reason


def test_docker_allowed_with_files():
    """测试有文件项目允许使用 Docker 技能"""
    verifier = SkillVerifier()
    
    context = {"file_count": 5}
    allowed, reason, enhancement = verifier.verify_skill_capability(
        user_id="test_user",
        skill_id="docker.container",
        workspace_context=context
    )
    
    assert allowed


def test_first_time_docker_gets_enhancement():
    """测试首次使用 Docker 技能获得增强指导"""
    verifier = SkillVerifier()
    
    context = {"file_count": 5}
    allowed, reason, enhancement = verifier.verify_skill_capability(
        user_id="test_user",
        skill_id="docker.container",
        workspace_context=context
    )
    
    assert allowed
    assert enhancement is not None
    assert "首次" in enhancement.warning_message
    assert "注释" in enhancement.additional_guidance


def test_backend_python_no_restrictions():
    """测试 Python 技能无限制"""
    verifier = SkillVerifier()
    
    context = {"file_count": 0}
    allowed, reason, enhancement = verifier.verify_skill_capability(
        user_id="test_user",
        skill_id="backend.python",
        workspace_context=context
    )
    
    assert allowed
    assert enhancement is None


def test_unknown_skill_allowed():
    """测试未知 Skill 默认允许"""
    verifier = SkillVerifier()
    
    context = {"file_count": 5}
    allowed, reason, enhancement = verifier.verify_skill_capability(
        user_id="test_user",
        skill_id="unknown.skill",
        workspace_context=context
    )
    
    assert allowed


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

### 验证方法

```bash
# 1. 运行单元测试
.venv_worker\Scripts\python.exe -m pytest python_worker/tests/test_skill_verifier.py -v

# 2. 集成测试：提交 Docker 相关任务
# 观察日志输出
# 预期看到:
# [SkillVerifier] ⚠️ docker.container: 首次使用，增强指导
# [SkillRouter] ⚠️ 增强 docker.container: 检测到您首次使用此技能，已增强指导
```

### 风险评估

**风险**: 中
- 修改了 Skill 路由核心逻辑
- 可能影响现有 Skill 的路由行为

**回滚方案**:
```python
# 添加开关
ENABLE_SKILL_VERIFICATION = os.getenv("ENABLE_SKILL_VERIFICATION", "true").lower() == "true"

if ENABLE_SKILL_VERIFICATION and self._verifier:
    # 执行验证
```

---

## 📝 Phase 3: 项目深度分析

### 目标
创建项目分析器，提取复杂度、领域、架构等元数据，为后续专家匹配提供依据。

### 文件清单

**新增文件**:
```
python_worker/
├── project_analyzer.py           # ⭐ 新增：项目深度分析器
└── tests/
    └── test_project_analyzer.py  # ⭐ 新增：分析器单元测试
```

**修改文件**:
```
python_worker/
├── context_builder.py            # 🔧 修改：增强上下文构建
└── memory_service.py             # 🔧 修改：存储项目元数据
```

### 具体任务

#### Task 3.1: 创建 ProjectAnalyzer 类

**文件**: `python_worker/project_analyzer.py`

```python
# -*- coding: utf-8 -*-
"""
AlphaPilot 项目深度分析器
职责：分析项目结构，提取复杂度、领域、架构等元数据
"""

from typing import Dict, List, Tuple
from dataclasses import dataclass
import os
from pathlib import Path


@dataclass
class ProjectMetadata:
    """项目元数据"""
    complexity_score: float = 0.0          # 复杂度 0-1
    domain_tags: List[str] = None          # 领域标签 ["web", "ai", "data"]
    architecture_pattern: str = "monolith" # 架构模式
    tech_stack: List[str] = None           # 技术栈
    has_database: bool = False             # 是否有数据库
    has_frontend: bool = False             # 是否有前端
    has_backend: bool = False              # 是否有后端
    file_count: int = 0                    # 文件总数
    python_file_count: int = 0             # Python 文件数
    dependency_count: int = 0              # 依赖数量
    language_counts: Dict[str, int] = None # 语言统计
    
    def __post_init__(self):
        if self.domain_tags is None:
            self.domain_tags = []
        if self.tech_stack is None:
            self.tech_stack = []
        if self.language_counts is None:
            self.language_counts = {}


class ProjectAnalyzer:
    """项目深度分析器"""
    
    def __init__(self):
        pass
    
    def analyze_project(self, workspace_path: str) -> ProjectMetadata:
        """
        深度分析项目，提取元数据
        
        参数:
            workspace_path: 工作区路径
        
        返回:
            ProjectMetadata: 项目元数据
        """
        # 复用 context_builder 的现有功能
        try:
            from python_worker.context_builder import inspect_python_project
            context = inspect_python_project(workspace_path)
        except Exception as e:
            print(f"[ProjectAnalyzer] ⚠️ context_builder 调用失败: {e}")
            context = {}
        
        # 计算各项指标
        complexity = self._calculate_complexity(context)
        domain = self._identify_domain(context)
        architecture = self._identify_architecture(context)
        tech_stack = self._extract_tech_stack(context)
        
        # 识别项目特征
        has_database = self._has_database(context)
        has_frontend = self._has_frontend(context)
        has_backend = self._has_backend(context)
        
        return ProjectMetadata(
            complexity_score=complexity,
            domain_tags=domain,
            architecture_pattern=architecture,
            tech_stack=tech_stack,
            has_database=has_database,
            has_frontend=has_frontend,
            has_backend=has_backend,
            file_count=context.get("total_file_count", 0),
            python_file_count=context.get("python_file_count", 0),
            dependency_count=len(context.get("unified_dependencies", [])),
            language_counts=context.get("language_counts", {})
        )
    
    def _calculate_complexity(self, context: Dict) -> float:
        """
        基于多维度计算项目复杂度
        
        维度：
        - 文件数量 (权重 0.3)
        - 依赖数量 (权重 0.3)
        - 代码问题数 (权重 0.2)
        - 语言多样性 (权重 0.2)
        """
        score = 0.0
        
        # 文件数量维度
        file_count = context.get("total_file_count", 0)
        file_score = min(file_count / 100, 1.0)
        score += file_score * 0.3
        
        # 依赖数量维度
        dep_count = len(context.get("unified_dependencies", []))
        dep_score = min(dep_count / 50, 1.0)
        score += dep_score * 0.3
        
        # 代码问题维度
        issue_count = len(context.get("issues", []))
        issue_score = min(issue_count / 20, 1.0)
        score += issue_score * 0.2
        
        # 语言多样性维度
        lang_count = len(context.get("language_counts", {}))
        lang_score = min(lang_count / 5, 1.0)
        score += lang_score * 0.2
        
        return min(score, 1.0)
    
    def _identify_domain(self, context: Dict) -> List[str]:
        """
        识别项目领域
        
        规则：
        - web: Flask/FastAPI/Django/Express/React/Vue
        - ai: Torch/TensorFlow/Scikit-learn
        - data: Pandas/NumPy/Polars
        - testing: Pytest/Unittest/Jest
        """
        deps = [d["name"].lower() for d in context.get("unified_dependencies", [])]
        domains = []
        
        web_keywords = ["flask", "fastapi", "django", "express", "react", "vue", "angular"]
        ai_keywords = ["torch", "tensorflow", "sklearn", "keras", "transformers"]
        data_keywords = ["pandas", "numpy", "polars", "dask"]
        testing_keywords = ["pytest", "unittest", "jest", "mocha"]
        
        if any(kw in " ".join(deps) for kw in web_keywords):
            domains.append("web")
        if any(kw in " ".join(deps) for kw in ai_keywords):
            domains.append("ai")
        if any(kw in " ".join(deps) for kw in data_keywords):
            domains.append("data")
        if any(kw in " ".join(deps) for kw in testing_keywords):
            domains.append("testing")
        
        return domains or ["general"]
    
    def _identify_architecture(self, context: Dict) -> str:
        """
        识别架构模式
        
        规则（简化版）：
        - microservice: 有 docker-compose.yml 和多个独立模块
        - monolith: 单体应用
        """
        # 检查是否有 docker-compose
        has_docker_compose = context.get("has_docker_compose", False)
        
        # 检查模块数量
        python_file_count = context.get("python_file_count", 0)
        
        if has_docker_compose and python_file_count > 20:
            return "microservice"
        
        return "monolith"
    
    def _extract_tech_stack(self, context: Dict) -> List[str]:
        """提取技术栈"""
        deps = context.get("unified_dependencies", [])
        return [d["name"] for d in deps[:10]]  # 取前 10 个主要依赖
    
    def _has_database(self, context: Dict) -> bool:
        """检查项目是否有数据库"""
        db_keywords = ["sql", "sqlite", "mysql", "postgresql", "mongodb", "redis"]
        deps = [d["name"].lower() for d in context.get("unified_dependencies", [])]
        return any(kw in " ".join(deps) for kw in db_keywords)
    
    def _has_frontend(self, context: Dict) -> bool:
        """检查项目是否有前端"""
        frontend_keywords = ["react", "vue", "angular", "typescript", "javascript"]
        deps = [d["name"].lower() for d in context.get("unified_dependencies", [])]
        return any(kw in " ".join(deps) for kw in frontend_keywords)
    
    def _has_backend(self, context: Dict) -> bool:
        """检查项目是否有后端"""
        backend_keywords = ["flask", "fastapi", "django", "express", "spring"]
        deps = [d["name"].lower() for d in context.get("unified_dependencies", [])]
        return any(kw in " ".join(deps) for kw in backend_keywords)


# ============================================================
# 单例模式：全局分析器实例
# ============================================================
_global_analyzer: Optional[ProjectAnalyzer] = None

def get_project_analyzer() -> ProjectAnalyzer:
    """获取全局分析器实例（单例模式）"""
    global _global_analyzer
    if _global_analyzer is None:
        _global_analyzer = ProjectAnalyzer()
    return _global_analyzer
```

#### Task 3.2: 集成到 qwen_worker_v2.py

**文件**: `python_worker/agents/qwen/qwen_worker_v2.py`

**修改点**: 在任务开始时分析项目
```python
from python_worker.project_analyzer import get_project_analyzer

def execute_task(task: TaskModel):
    # ⭐ 新增：项目分析
    try:
        analyzer = get_project_analyzer()
        project_meta = analyzer.analyze_project(task.workspace_path)
        
        print(f"[ProjectAnalyzer] 📊 项目元数据:")
        print(f"  - 复杂度: {project_meta.complexity_score:.2f}")
        print(f"  - 领域: {', '.join(project_meta.domain_tags)}")
        print(f"  - 架构: {project_meta.architecture_pattern}")
        print(f"  - 文件数: {project_meta.file_count}")
        print(f"  - 依赖数: {project_meta.dependency_count}")
        
        # 存储到 task context
        task.context["project_meta"] = project_meta
        
        # 存储到 Memory Service（如果可用）
        try:
            from python_worker.memory_service import MemoryService
            memory = MemoryService()
            memory.createMemory(
                owner_type="project",
                owner_id=task.project_id or "default",
                memory_type="fact",
                content=f"项目元数据: 复杂度={project_meta.complexity_score:.2f}, "
                       f"领域={','.join(project_meta.domain_tags)}, "
                       f"架构={project_meta.architecture_pattern}",
                importance=0.8
            )
        except Exception as e:
            print(f"[Worker] ⚠️ Memory Service 存储失败: {e}")
    except Exception as e:
        print(f"[Worker] ⚠️ 项目分析失败: {e}")
        # 提供默认元数据
        task.context["project_meta"] = {
            "complexity_score": 0.5,
            "domain_tags": ["general"],
            "architecture_pattern": "monolith",
            "has_code": True,
            "has_frontend": False,
            "file_count": 10
        }
    
    # 继续原有流程...
```

#### Task 3.3: 更新 Persona 验证器使用真实元数据

**文件**: `python_worker/agents/qwen/qwen_worker_v2.py`

**修改点**: 使用真实的项目元数据
```python
def create_steps_from_chain(execution_chain: list, prompt: str, persona: str, intent: str = None) -> list:
    # ⭐ 改进：使用真实的项目元数据
    try:
        verifier = get_persona_verifier()
        
        # 从 task context 获取项目元数据
        project_meta = task.context.get("project_meta", {})
        
        # 构建验证用的上下文
        project_context = {
            "complexity_score": project_meta.get("complexity_score", 0.5),
            "has_code": True,
            "has_frontend": project_meta.get("has_frontend", False),
            "file_count": project_meta.get("file_count", 10)
        }
        
        # 验证人格访问权限
        user_id = task.user_id or "default_user"
        allowed, reason, fallback = verifier.verify_persona_access(
            user_id=user_id,
            persona_type=persona,
            project_context=project_context,
            verbose=True
        )
        
        if not allowed:
            print(f"[Worker] ⚠️ Persona 降级: {persona} → {fallback} ({reason})")
            persona = fallback
    except Exception as e:
        print(f"[Worker] ⚠️ Persona 验证失败: {e}")
    
    # 继续原有流程...
```

#### Task 3.4: 编写单元测试

**文件**: `python_worker/tests/test_project_analyzer.py`

```python
# -*- coding: utf-8 -*-
"""
ProjectAnalyzer 单元测试
"""

import pytest
from python_worker.project_analyzer import ProjectAnalyzer, ProjectMetadata


def test_calculate_complexity_simple():
    """测试简单项目复杂度计算"""
    analyzer = ProjectAnalyzer()
    
    context = {
        "total_file_count": 10,
        "unified_dependencies": [],
        "issues": [],
        "language_counts": {".py": 10}
    }
    
    complexity = analyzer._calculate_complexity(context)
    assert 0.0 <= complexity <= 0.5  # 简单项目


def test_calculate_complexity_complex():
    """测试复杂项目复杂度计算"""
    analyzer = ProjectAnalyzer()
    
    context = {
        "total_file_count": 100,
        "unified_dependencies": [{"name": dep} for dep in range(50)],
        "issues": [{"kind": "error"} for _ in range(20)],
        "language_counts": {".py": 50, ".js": 30, ".ts": 20}
    }
    
    complexity = analyzer._calculate_complexity(context)
    assert complexity > 0.8  # 复杂项目


def test_identify_domain_web():
    """测试 Web 项目领域识别"""
    analyzer = ProjectAnalyzer()
    
    context = {
        "unified_dependencies": [
            {"name": "flask"},
            {"name": "react"}
        ]
    }
    
    domains = analyzer._identify_domain(context)
    assert "web" in domains


def test_identify_domain_ai():
    """测试 AI 项目领域识别"""
    analyzer = ProjectAnalyzer()
    
    context = {
        "unified_dependencies": [
            {"name": "torch"},
            {"name": "transformers"}
        ]
    }
    
    domains = analyzer._identify_domain(context)
    assert "ai" in domains


def test_has_database():
    """测试数据库检测"""
    analyzer = ProjectAnalyzer()
    
    context = {
        "unified_dependencies": [
            {"name": "sqlalchemy"},
            {"name": "postgresql"}
        ]
    }
    
    assert analyzer._has_database(context) is True


def test_has_frontend():
    """测试前端检测"""
    analyzer = ProjectAnalyzer()
    
    context = {
        "unified_dependencies": [
            {"name": "react"},
            {"name": "typescript"}
        ]
    }
    
    assert analyzer._has_frontend(context) is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

### 验证方法

```bash
# 1. 运行单元测试
.venv_worker\Scripts\python.exe -m pytest python_worker/tests/test_project_analyzer.py -v

# 2. 集成测试：提交真实项目任务
# 观察日志输出
# 预期看到:
# [ProjectAnalyzer] 📊 项目元数据:
#   - 复杂度: 0.75
#   - 领域: web, testing
#   - 架构: monolith
#   - 文件数: 45
#   - 依赖数: 23
```

### 风险评估

**风险**: 低
- 独立模块，不影响现有逻辑
- 失败时有默认值兜底

---

## 📝 Phase 4: 智能专家匹配

### 目标
根据项目元数据和用户历史，智能推荐最合适的专家人格。

### 文件清单

**新增文件**:
```
python_worker/
├── expert_matcher.py             # ⭐ 新增：专家匹配器
└── tests/
    └── test_expert_matcher.py    # ⭐ 新增：匹配器单元测试
```

**修改文件**:
```
python_worker/agents/qwen/
└── qwen_worker_v2.py             # 🔧 修改：集成智能匹配
```

### 具体任务

#### Task 4.1: 创建 ExpertMatcher 类

**文件**: `python_worker/expert_matcher.py`

```python
# -*- coding: utf-8 -*-
"""
AlphaPilot 专家智能匹配器
职责：根据项目元数据和用户历史，推荐最合适的专家人格
"""

from typing import Dict, Tuple, Optional
from dataclasses import dataclass


@dataclass
class ExpertRecommendation:
    """专家推荐结果"""
    persona_type: str               # 推荐人格
    confidence: float               # 推荐置信度 0-1
    reason: str                     # 推荐理由
    alternative_personas: Tuple[str, ...] = ()  # 备选人格


class ExpertMatcher:
    """专家智能匹配器"""
    
    def __init__(self, memory_service=None):
        """
        初始化匹配器
        
        参数:
            memory_service: MemoryService 实例（可选）
        """
        self.memory = memory_service
        self._matching_rules = self._load_matching_rules()
    
    def _load_matching_rules(self) -> Dict[str, Dict]:
        """加载匹配规则"""
        return {
            "architect": {
                "min_complexity": 0.8,
                "domains": ("all",),
                "required_features": ("has_code",),
                "priority": 90
            },
            "frontend": {
                "min_complexity": 0.0,
                "domains": ("web",),
                "required_features": ("has_frontend",),
                "priority": 70
            },
            "backend": {
                "min_complexity": 0.0,
                "domains": ("web",),
                "required_features": ("has_backend",),
                "priority": 70
            },
            "ai_scientist": {
                "min_complexity": 0.0,
                "domains": ("ai",),
                "required_features": (),
                "priority": 80
            },
            "database": {
                "min_complexity": 0.0,
                "domains": ("all",),
                "required_features": ("has_database",),
                "priority": 70
            },
            "engineer": {
                "min_complexity": 0.0,
                "domains": ("all",),
                "required_features": (),
                "priority": 50  # 默认最低优先级
            }
        }
    
    def recommend_expert(
        self,
        user_id: str,
        project_meta: Dict,
        prompt: str,
        verbose: bool = False
    ) -> ExpertRecommendation:
        """
        智能推荐最合适的专家人格
        
        参数:
            user_id: 用户ID
            project_meta: 项目元数据 {
                "complexity_score": float,
                "domain_tags": List[str],
                "has_frontend": bool,
                "has_backend": bool,
                "has_database": bool,
                ...
            }
            prompt: 用户输入提示
            verbose: 是否打印详细日志
        
        返回:
            ExpertRecommendation: 推荐结果
        """
        candidates = []
        
        # 1. 基于项目元数据匹配
        for persona_type, rule in self._matching_rules.items():
            if self._match_rule(persona_type, rule, project_meta):
                confidence = self._calculate_confidence(rule, project_meta)
                candidates.append((persona_type, confidence, rule["priority"]))
        
        # 2. 按优先级和置信度排序
        candidates.sort(key=lambda x: (-x[2], -x[1]))
        
        if not candidates:
            if verbose:
                print("[ExpertMatcher] ℹ️ 无匹配专家，使用默认工程师")
            return ExpertRecommendation(
                persona_type="engineer",
                confidence=0.5,
                reason="无匹配专家，使用默认工程师人格"
            )
        
        # 3. 选择最佳匹配
        best_persona, best_confidence, _ = candidates[0]
        reason = self._generate_reason(best_persona, project_meta)
        
        # 4. 检查用户历史偏好（如果有 Memory Service）
        if self.memory:
            preferred_persona = self._check_user_preference(user_id)
            if preferred_persona and preferred_persona in [c[0] for c in candidates]:
                # 用户偏好的人格在候选列表中，优先使用
                best_persona = preferred_persona
                reason = f"用户偏好 + {reason}"
        
        if verbose:
            print(f"[ExpertMatcher] 🎯 推荐: {best_persona} (置信度: {best_confidence:.2f})")
            print(f"[ExpertMatcher]   理由: {reason}")
        
        # 5. 返回推荐结果
        alternatives = [c[0] for c in candidates[1:4]]  # 取前 3 个备选
        return ExpertRecommendation(
            persona_type=best_persona,
            confidence=best_confidence,
            reason=reason,
            alternative_personas=tuple(alternatives)
        )
    
    def _match_rule(self, persona_type: str, rule: Dict, project_meta: Dict) -> bool:
        """检查人格是否匹配规则"""
        # 检查复杂度
        complexity = project_meta.get("complexity_score", 0.0)
        if complexity < rule.get("min_complexity", 0.0):
            return False
        
        # 检查领域
        domains = rule.get("domains", ())
        if "all" not in domains:
            project_domains = project_meta.get("domain_tags", [])
            if not any(d in domains for d in project_domains):
                return False
        
        # 检查必需特征
        required_features = rule.get("required_features", ())
        for feature in required_features:
            if not project_meta.get(feature, False):
                return False
        
        return True
    
    def _calculate_confidence(self, rule: Dict, project_meta: Dict) -> float:
        """计算匹配置信度"""
        confidence = 0.5  # 基础置信度
        
        # 复杂度越高，置信度越高
        complexity = project_meta.get("complexity_score", 0.0)
        confidence += complexity * 0.3
        
        # 优先级越高，置信度越高
        priority = rule.get("priority", 50)
        confidence += (priority / 100) * 0.2
        
        return min(confidence, 1.0)
    
    def _generate_reason(self, persona_type: str, project_meta: Dict) -> str:
        """生成推荐理由"""
        reasons = []
        
        complexity = project_meta.get("complexity_score", 0.0)
        if complexity > 0.8:
            reasons.append("项目复杂度高")
        
        domains = project_meta.get("domain_tags", [])
        if "web" in domains:
            reasons.append("Web 项目")
        if "ai" in domains:
            reasons.append("AI 项目")
        if "data" in domains:
            reasons.append("数据项目")
        
        if project_meta.get("has_database"):
            reasons.append("包含数据库")
        if project_meta.get("has_frontend"):
            reasons.append("包含前端")
        
        if not reasons:
            reasons.append("通用项目")
        
        return "，".join(reasons)
    
    def _check_user_preference(self, user_id: str) -> Optional[str]:
        """检查用户历史偏好（基于 Memory Service）"""
        try:
            user_memories = self.memory.query_user_memories(
                user_id,
                memory_type="preference",
                limit=10
            )
            
            for memory in user_memories:
                content = memory.content.lower()
                if "架构" in content or "architect" in content:
                    return "architect"
                if "前端" in content or "frontend" in content:
                    return "frontend"
                if "ai" in content:
                    return "ai_scientist"
            
            return None
        except Exception as e:
            print(f"[ExpertMatcher] ⚠️ 用户偏好查询失败: {e}")
            return None


# ============================================================
# 单例模式：全局匹配器实例
# ============================================================
_global_matcher: Optional[ExpertMatcher] = None

def get_expert_matcher(memory_service=None) -> ExpertMatcher:
    """获取全局匹配器实例（单例模式）"""
    global _global_matcher
    if _global_matcher is None:
        _global_matcher = ExpertMatcher(memory_service)
    return _global_matcher
```

#### Task 4.2: 集成到 qwen_worker_v2.py

**文件**: `python_worker/agents/qwen/qwen_worker_v2.py`

**修改点**: 在任务开始时推荐专家
```python
from python_worker.expert_matcher import get_expert_matcher

def execute_task(task: TaskModel):
    # ... 项目分析代码 ...
    
    # ⭐ 新增：智能专家匹配
    try:
        matcher = get_expert_matcher(memory_service)
        recommendation = matcher.recommend_expert(
            user_id=task.user_id or "default_user",
            project_meta=task.context.get("project_meta", {}),
            prompt=task.prompt,
            verbose=True
        )
        
        print(f"[ExpertMatcher] 🎯 推荐人格: {recommendation.persona_type}")
        print(f"[ExpertMatcher]   置信度: {recommendation.confidence:.2f}")
        print(f"[ExpertMatcher]   理由: {recommendation.reason}")
        
        # 使用推荐的人格（如果用户未指定）
        if not task.persona or task.persona == "default":
            task.persona = recommendation.persona_type
            print(f"[Worker] ✅ 使用推荐人格: {task.persona}")
    except Exception as e:
        print(f"[Worker] ⚠️ 专家匹配失败: {e}")
        task.persona = task.persona or "engineer"
    
    # 继续原有流程...
```

#### Task 4.3: 编写单元测试

**文件**: `python_worker/tests/test_expert_matcher.py`

```python
# -*- coding: utf-8 -*-
"""
ExpertMatcher 单元测试
"""

import pytest
from python_worker.expert_matcher import ExpertMatcher, ExpertRecommendation


def test_recommend_architect_for_complex_project():
    """测试高复杂度项目推荐架构师"""
    matcher = ExpertMatcher()
    
    project_meta = {
        "complexity_score": 0.9,
        "domain_tags": ["web"],
        "has_code": True,
        "has_frontend": True
    }
    
    recommendation = matcher.recommend_expert(
        user_id="test_user",
        project_meta=project_meta,
        prompt="设计系统架构"
    )
    
    assert recommendation.persona_type == "architect"
    assert recommendation.confidence > 0.8


def test_recommend_frontend_for_web_project():
    """测试 Web 项目推荐前端专家"""
    matcher = ExpertMatcher()
    
    project_meta = {
        "complexity_score": 0.5,
        "domain_tags": ["web"],
        "has_frontend": True,
        "has_backend": True
    }
    
    recommendation = matcher.recommend_expert(
        user_id="test_user",
        project_meta=project_meta,
        prompt="优化 React 组件"
    )
    
    assert recommendation.persona_type == "frontend"


def test_recommend_ai_scientist_for_ai_project():
    """测试 AI 项目推荐 AI 专家"""
    matcher = ExpertMatcher()
    
    project_meta = {
        "complexity_score": 0.6,
        "domain_tags": ["ai"],
        "has_code": True
    }
    
    recommendation = matcher.recommend_expert(
        user_id="test_user",
        project_meta=project_meta,
        prompt="训练神经网络"
    )
    
    assert recommendation.persona_type == "ai_scientist"


def test_fallback_to_engineer():
    """测试无匹配时降级到工程师"""
    matcher = ExpertMatcher()
    
    project_meta = {
        "complexity_score": 0.2,
        "domain_tags": ["general"],
        "has_code": False
    }
    
    recommendation = matcher.recommend_expert(
        user_id="test_user",
        project_meta=project_meta,
        prompt="简单任务"
    )
    
    assert recommendation.persona_type == "engineer"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

### 验证方法

```bash
# 1. 运行单元测试
.venv_worker\Scripts\python.exe -m pytest python_worker/tests/test_expert_matcher.py -v

# 2. 集成测试：提交不同类型任务
# 观察日志输出
# 预期看到:
# [ExpertMatcher] 🎯 推荐: architect (置信度: 0.85)
# [ExpertMatcher]   理由: 项目复杂度高，Web 项目
# [Worker] ✅ 使用推荐人格: architect
```

### 风险评估

**风险**: 低
- 可选功能，不影响现有逻辑
- 用户仍可手动指定人格

---

## 🎯 总体验证流程

### 端到端测试

```bash
# 1. 启动所有服务
cd D:\Copilot_Alphapilot\Copilot_Alphapilot
.\start_all.ps1

# 2. 提交高复杂度任务
# 预期流程:
# [ProjectAnalyzer] 📊 项目元数据: 复杂度=0.85, 领域=web
# [ExpertMatcher] 🎯 推荐: architect (置信度: 0.88)
# [PersonaVerifier] ✅ architect: 验证通过
# [Worker] ✅ 使用推荐人格: architect

# 3. 提交低复杂度任务
# 预期流程:
# [ProjectAnalyzer] 📊 项目元数据: 复杂度=0.30, 领域=general
# [ExpertMatcher] 🎯 推荐: engineer (置信度: 0.60)
# [PersonaVerifier] ✅ engineer: 验证通过
# [Worker] ✅ 使用推荐人格: engineer

# 4. 提交 Docker 相关任务（首次）
# 预期流程:
# [SkillRouter] 🎯 路由到: docker.container
# [SkillVerifier] ⚠️ docker.container: 首次使用，增强指导
# [SkillRouter] ⚠️ 增强 docker.container: 检测到您首次使用此技能
```

### 性能测试

```bash
# 测试分析器性能
.venv_worker\Scripts\python.exe -c "
from python_worker.project_analyzer import get_project_analyzer
import time

analyzer = get_project_analyzer()
start = time.time()
meta = analyzer.analyze_project('.')
elapsed = time.time() - start
print(f'分析耗时: {elapsed:.2f}s')
print(f'复杂度: {meta.complexity_score}')
"

# 预期: 分析耗时 < 2s
```

---

## 📊 实施检查清单

### Phase 1: Persona 验证层
- [ ] 创建 `persona_verifier.py`
- [ ] 实现 PersonaVerifier 类
- [ ] 修改 `qwen_worker_v2.py` 集成验证器
- [ ] 编写 `test_persona_verifier.py`
- [ ] 运行单元测试
- [ ] 集成测试验证
- [ ] 文档更新

### Phase 2: Skill 能力验证
- [ ] 创建 `skill_verifier.py`
- [ ] 实现 SkillVerifier 类
- [ ] 修改 `skills/router.py` 集成验证器
- [ ] 修改 `qwen_worker_v2.py` 初始化验证器
- [ ] 编写 `test_skill_verifier.py`
- [ ] 运行单元测试
- [ ] 集成测试验证
- [ ] 文档更新

### Phase 3: 项目深度分析
- [ ] 创建 `project_analyzer.py`
- [ ] 实现 ProjectAnalyzer 类
- [ ] 修改 `qwen_worker_v2.py` 集成分析器
- [ ] 更新 Persona 验证器使用真实元数据
- [ ] 编写 `test_project_analyzer.py`
- [ ] 运行单元测试
- [ ] 集成测试验证
- [ ] 文档更新

### Phase 4: 智能专家匹配
- [ ] 创建 `expert_matcher.py`
- [ ] 实现 ExpertMatcher 类
- [ ] 修改 `qwen_worker_v2.py` 集成匹配器
- [ ] 编写 `test_expert_matcher.py`
- [ ] 运行单元测试
- [ ] 集成测试验证
- [ ] 文档更新

---

## 🚀 后续扩展（Phase 5+）

### 扩展到其他 Worker
- [ ] Doubao Worker 集成
- [ ] DeepSeek Worker 集成
- [ ] Gemini Worker 集成
- [ ] 统一验证器接口

### 高级功能
- [ ] 用户能力评分系统
- [ ] 动态调整人格优先级
- [ ] 跨项目经验迁移
- [ ] 协作模式验证

### UI 增强
- [ ] VSCode 扩展显示推荐人格
- [ ] 用户能力可视化
- [ ] 项目复杂度仪表盘
- [ ] Skill 使用历史统计

---

## 📝 注意事项

### 1. 向后兼容
- 所有新功能都有开关控制
- 验证失败时有安全降级
- 不破坏现有流程

### 2. 性能考虑
- 项目分析结果缓存
- Memory Service 查询超时控制
- 验证器异步执行（可选）

### 3. 错误处理
- Memory Service 不可用时的降级策略
- 分析失败时的默认值
- 详细的错误日志

### 4. 配置管理
```python
# 环境变量开关
ENABLE_PERSONA_VERIFICATION = os.getenv("ENABLE_PERSONA_VERIFICATION", "true")
ENABLE_SKILL_VERIFICATION = os.getenv("ENABLE_SKILL_VERIFICATION", "true")
ENABLE_PROJECT_ANALYSIS = os.getenv("ENABLE_PROJECT_ANALYSIS", "true")
ENABLE_EXPERT_MATCHING = os.getenv("ENABLE_EXPERT_MATCHING", "true")
```

---

## 🎉 预期成果

实施完成后，AlphaPilot 将具备：

1. **智能人格管理**
   - 自动验证用户资格
   - 合理降级到适合的人格
   - 保护高级人格不被滥用

2. **技能能力认证**
   - 首次使用时增强指导
   - 根据用户历史动态调整
   - 防止错误建议

3. **项目深度理解**
   - 准确计算项目复杂度
   - 识别项目领域和架构
   - 为专家匹配提供依据

4. **智能专家推荐**
   - 根据项目自动推荐专家
   - 考虑用户历史偏好
   - 提供推荐理由和置信度

---

**工作日志版本**: v1.0  
**创建日期**: 2026-10-13  
**主线**: qwen_worker_v2  
**预计总耗时**: 5-9 天（4 个 Phase）
