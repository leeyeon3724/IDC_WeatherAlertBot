from __future__ import annotations

from typing import Protocol

from app.domain.health import ApiHealthState


class HealthStateRepository(Protocol):
    @property
    def state(self) -> ApiHealthState:
        ...

    def update_state(self, state: ApiHealthState) -> None:
        ...
