import pytest

from python_worker.skills import get_registry, list_skills, reload_skills, route_skill


def test_builtin_skills_are_registered_and_route_by_domain():
    registered_ids = {skill.id for skill in list_skills()}
    # 核心基础设施 skill 必须存在
    core_skills = {
        "backend.python",
        "dependency.manager",
        "frontend.ui",
        "workspace.file-deletion",
    }
    assert core_skills <= registered_ids, f"缺失核心 skill: {core_skills - registered_ids}"
    # v4.0 新增 creative/vision skill
    v40_skills = {
        "creative.pure-text",
        "creative.document-proposal",
        "creative.brand-content",
        "vision.image-analysis",
        "diagnosis.runtime-error",  # ⭐ v4.0 Phase 5
    }
    assert v40_skills <= registered_ids, f"缺失 v4.0 skill: {v40_skills - registered_ids}"
    assert route_skill("修复 VS Code Webview 的 React 界面").id == "frontend.ui"
    assert route_skill("修复 Python worker 的接口").id == "backend.python"
    assert route_skill("升级 package.json 中的依赖").id == "dependency.manager"
    # v4.0 新增路由
    assert route_skill("写一首诗").id == "creative.pure-text"
    assert route_skill("写个招商方案").id == "creative.document-proposal"
    # ⭐ Phase 5: 运行时错误诊断路由
    assert route_skill("端口被占用 Errno 10048").id == "diagnosis.runtime-error"
    assert route_skill("出现了ConnectionRefused错误").id == "diagnosis.runtime-error"
    assert route_skill("权限不足 Permission denied").id == "diagnosis.runtime-error"


def test_dependency_skill_only_advertises_proposal_capabilities():
    skill = route_skill("install package from package.json")

    assert skill is not None
    assert "changes.propose" in skill.capabilities
    assert "package.install" not in skill.capabilities
    assert "unavailable" in skill.guidance


def test_diagnosis_runtime_error_skill_skips_test_and_constrains_behavior():
    """⭐ Phase 5: 运行时错误诊断 Skill 的 profile 和 guidance 验证"""
    skill = get_registry().get("diagnosis.runtime-error")
    assert skill is not None, "diagnosis.runtime-error skill 必须注册"

    assert skill.priority == 90
    assert "diagnosis.log" in skill.capabilities
    assert skill.output_profile["requires_test"] is False
    assert skill.output_profile["workspace_dependency"] == "read_write"
    assert skill.output_profile["requires_workspace_scan"] is True

    guidance = skill.guidance.lower()
    assert "minimum-viable fix" in guidance or "最小化修复" in guidance
    assert "do not modify" in guidance or "严禁修改" in guidance
    assert "port" in guidance
    assert "permission" in guidance


def test_registry_rejects_duplicate_ids_and_supports_runtime_removal():
    registry = get_registry()
    skill = registry.get("frontend.ui")

    assert skill is not None
    with pytest.raises(ValueError, match="Duplicate skill id"):
        registry.register(skill)
    assert registry.unregister("frontend.ui")
    assert route_skill("React frontend") is None
    reload_skills()
    assert route_skill("React frontend").id == "frontend.ui"