import pytest

from python_worker.skills import get_registry, list_skills, reload_skills, route_skill


def test_builtin_skills_are_registered_and_route_by_domain():
    assert {skill.id for skill in list_skills()} == {
        "backend.python",
        "dependency.manager",
        "frontend.ui",
        "workspace.file-deletion",
    }
    assert route_skill("修复 VS Code Webview 的 React 界面").id == "frontend.ui"
    assert route_skill("修复 Python worker 的接口").id == "backend.python"
    assert route_skill("升级 package.json 中的依赖").id == "dependency.manager"


def test_dependency_skill_only_advertises_proposal_capabilities():
    skill = route_skill("install package from package.json")

    assert skill is not None
    assert "changes.propose" in skill.capabilities
    assert "package.install" not in skill.capabilities
    assert "unavailable" in skill.guidance


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
