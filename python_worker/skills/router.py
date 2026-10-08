import importlib
import pkgutil
import re
from typing import Dict, Optional

from . import __path__ as _package_path
from .base import Skill


class SkillRegistry:
    def __init__(self):
        self._skills: Dict[str, Skill] = {}

    def register(self, skill: Skill):
        if not re.fullmatch(r"[a-z][a-z0-9_.-]*", skill.id):
            raise ValueError(f"Invalid skill id: {skill.id}")
        if not re.fullmatch(r"\d+\.\d+\.\d+", skill.version):
            raise ValueError(f"Skill {skill.id} must use semantic versioning")
        if skill.id in self._skills:
            raise ValueError(f"Duplicate skill id: {skill.id}")
        self._skills[skill.id] = skill

    def unregister(self, skill_id: str) -> bool:
        return self._skills.pop(skill_id, None) is not None

    def get(self, skill_id: str) -> Optional[Skill]:
        return self._skills.get(skill_id)

    def list_skills(self):
        return tuple(sorted(self._skills.values(), key=lambda item: item.id))

    def route(self, prompt: str) -> Optional[Skill]:
        if not isinstance(prompt, str) or not prompt.strip():
            return None

        matches = [
            (skill, skill.match_count(prompt))
            for skill in self._skills.values()
            if skill.match_count(prompt) > 0
        ]
        if not matches:
            return None
        matches.sort(key=lambda item: (-item[0].priority, -item[1], item[0].id))
        return matches[0][0]

    def reload(self):
        self._skills.clear()
        for module_info in pkgutil.iter_modules(_package_path):
            if module_info.name in {"base", "router"} or module_info.name.startswith("_"):
                continue
            module_name = f"{__package__}.{module_info.name}"
            module = importlib.import_module(module_name)
            module = importlib.reload(module)
            register = getattr(module, "register", None)
            if not callable(register):
                raise TypeError(f"Skill module {module_name} must export register(registry)")
            register(self)
        return self.list_skills()

_registry = SkillRegistry()
_registry.reload()


def route_skill(prompt: str) -> Optional[Skill]:
    return _registry.route(prompt)


def list_skills():
    return _registry.list_skills()


def reload_skills():
    return _registry.reload()


def get_registry() -> SkillRegistry:
    return _registry
