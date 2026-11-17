from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any


class RoundState(str, Enum):
    WAITING_PROJECT_CONFIRMATION = "WAITING_PROJECT_CONFIRMATION"
    WAITING_MODEL_CONFIRMATION = "WAITING_MODEL_CONFIRMATION"
    READY_TO_SEND = "READY_TO_SEND"
    WAITING_COMMIT = "WAITING_COMMIT"
    BLOCKED = "BLOCKED"
    STALLED = "STALLED"
    ROUND_COMPLETE = "ROUND_COMPLETE"
    TASK_COMPLETE = "TASK_COMPLETE"


class AgentLifecycle(str, Enum):
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    ARCHIVED = "ARCHIVED"


@dataclass
class RoundRecord:
    round_id: str
    agent_id: str
    generation: int
    round_number: int
    lease_id: str
    state: RoundState
    task: str
    project_confirmed: bool = False
    model_confirmed: bool = False

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["state"] = self.state.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RoundRecord":
        data = dict(data)
        data["state"] = RoundState(data["state"])
        return cls(**data)


@dataclass
class AgentRecord:
    agent_id: str
    generation: int = 1
    lifecycle: AgentLifecycle = AgentLifecycle.ACTIVE
    current_round_number: int = 0

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["lifecycle"] = self.lifecycle.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentRecord":
        data = dict(data)
        data["lifecycle"] = AgentLifecycle(data["lifecycle"])
        return cls(**data)
