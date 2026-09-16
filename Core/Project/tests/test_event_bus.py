from core.event_bus import EventBus
from core.events import USER_COMMAND


def handle_command(command: str) -> None:
    print(f"EVENT RECEIVED: {command}")


bus = EventBus()

bus.subscribe(USER_COMMAND, handle_command)

bus.publish(
    USER_COMMAND,
    command="hello"
)