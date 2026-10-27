from dataclasses import dataclass, field
from typing import Dict, Tuple


@dataclass(frozen=True)
class Skill:
    id: str
    name: str
    version: str
    description: str
    triggers: Tuple[str, ...]
    priority: int
    capabilities: Tuple[str, ...]
    guidance: str
    output_profile: Dict = field(default_factory=dict)
    read_only: bool = False

    def match_count(self, prompt: str) -> int:
        normalized = prompt.casefold()
        return sum(1 for trigger in self.triggers if trigger.casefold() in normalized)

    def as_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "capabilities": list(self.capabilities),
            "output_profile": dict(self.output_profile),
            "guidance": self.guidance,
        }