import json
from pathlib import Path

from content_agent.schemas import AgentInput


class MockProvider:
    def __init__(self, scene_path: str = "examples/scene.json") -> None:
        self.scene_path = Path(scene_path)

    def get_scene(self) -> AgentInput:
        return AgentInput.model_validate_json(self.scene_path.read_text(encoding="utf-8-sig"))
