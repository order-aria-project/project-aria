from collections import defaultdict
from typing import Callable, Any


class EventBus:
    def __init__(self) -> None:
        self._listeners: dict[str, list[Callable[..., Any]]] = defaultdict(list)

    def subscribe(self, event_name: str, callback: Callable[..., Any]) -> None:
        """Subscribe a function to an event."""
        if callback not in self._listeners[event_name]:
            self._listeners[event_name].append(callback)

    def publish(self, event_name: str, **data: Any) -> None:
        """Publish an event to all subscribers."""
        for callback in self._listeners.get(event_name, []):
            callback(**data)