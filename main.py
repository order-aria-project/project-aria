from __future__ import annotations

import json
import re
import signal
import time
from datetime import datetime
from pathlib import Path

from core.ai_brain import AIBrain
from core.app_registry import AppRegistry
from core.conversation_manager import ConversationManager
from core.event_bus import EventBus
from core.events import (
    ARIA_RESPONSE,
    CORE_SHUTDOWN,
    CORE_STARTED,
    USER_COMMAND,
)
from core.tool_router import ToolRouter

from tools.application_tools import ApplicationTools
from tools.calculator_tools import calculate
from tools.time_tools import (
    get_current_date,
    get_current_datetime,
    get_current_time,
)
from tools.system_tools import (
    get_battery,
    get_cpu_usage,
    get_disk_space,
    get_gpu_info,
    get_ram_usage,
    get_running_applications,
    get_system_status,
)

from voice.speech_listener import SpeechListener
from voice.voice_controller import VoiceController


PROJECT_ROOT = Path(
    __file__
).resolve().parent


PROFILE_PATH = (
    PROJECT_ROOT
    / "core"
    / "aria_profile.json"
)


SETTINGS_PATH = (
    PROJECT_ROOT
    / "config"
    / "settings.json"
)


# ============================================================
# CONFIGURATION
# ============================================================

def load_json(
    path: Path,
) -> dict:

    try:

        with path.open(
            "r",
            encoding="utf-8",
        ) as file:

            return json.load(
                file
            )

    except FileNotFoundError as exc:

        raise SystemExit(
            f"Configuration file not found: {path}"
        ) from exc

    except json.JSONDecodeError as exc:

        raise SystemExit(
            f"Invalid JSON in {path}: {exc}"
        ) from exc


# ============================================================
# LOGGING
# ============================================================

def log_event(
    message: str,
    log_path: Path,
) -> None:

    timestamp = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    log_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with log_path.open(
        "a",
        encoding="utf-8",
    ) as log_file:

        log_file.write(
            f"[{timestamp}] {message}\n"
        )


# ============================================================
# TOOL REGISTRATION
# ============================================================

def register_optional_tool(
    router: ToolRouter,
    tool_name: str,
    owner: object,
) -> None:

    function = getattr(
        owner,
        tool_name,
        None,
    )

    if not callable(function):
        return

    try:

        router.register(
            tool_name,
            function,
        )

        print(
            f"[TOOLS] Registered: {tool_name}",
            flush=True,
        )

    except ValueError:
        pass


def register_media_tools(
    router: ToolRouter,
) -> None:

    from tools import media_tools

    print(
        "[TOOLS] Loading media controls...",
        flush=True,
    )

    media_names = (
        "mute_system_audio",
        "unmute_system_audio",
        "mute_application",
        "unmute_application",
        "list_audio_sessions",
    )

    for name in media_names:

        function = getattr(
            media_tools,
            name,
            None,
        )

        if not callable(function):

            print(
                "[TOOLS] ERROR: Missing media tool: "
                f"{name}",
                flush=True,
            )

            continue

        try:

            router.register(
                name,
                function,
            )

            print(
                f"[TOOLS] Registered: {name}",
                flush=True,
            )

        except ValueError:
            pass


# ============================================================
# COMMAND NORMALISATION
# ============================================================

def normalize_command(
    text: str,
) -> str:

    return " ".join(
        str(text or "")
        .lower()
        .replace(
            ".",
            " ",
        )
        .replace(
            ",",
            " ",
        )
        .replace(
            "!",
            " ",
        )
        .replace(
            "?",
            " ",
        )
        .replace(
            "'",
            " ",
        )
        .split()
    )


# ============================================================
# KNOWN AUDIO APPLICATIONS
# ============================================================

APP_ALIASES = {
    "brave": "Brave",
    "brave browser": "Brave",

    "chrome": "Chrome",
    "google chrome": "Chrome",

    "discord": "Discord",

    "spotify": "Spotify",

    "blender": "Blender",

    "roblox": "Roblox",

    "obs": "OBS",
    "obs studio": "OBS",

    "firefox": "Firefox",

    "edge": "Edge",
    "microsoft edge": "Edge",

    "steam": "Steam",
}


def resolve_known_app(
    value: str,
) -> str | None:

    normalized = normalize_command(
        value
    )

    if normalized in APP_ALIASES:
        return APP_ALIASES[
            normalized
        ]

    compact = normalized.replace(
        " ",
        "",
    )

    for alias, canonical in APP_ALIASES.items():

        if compact == alias.replace(
            " ",
            "",
        ):

            return canonical

    return None


# ============================================================
# DETERMINISTIC MEDIA COMMANDS
# ============================================================

def try_direct_media_command(
    user_input: str,
    tool_router: ToolRouter,
) -> str | None:

    """
    Clear media commands are handled deterministically.

    This means:
        "mute Brave"
        "unmute Brave"
        "mute the computer"
        "unmute system audio"

    do not rely on Qwen deciding whether to emit a tool call.
    """

    normalized = normalize_command(
        user_input
    )

    # --------------------------------------------------------
    # APPLICATION AUDIO
    # --------------------------------------------------------

    application_match = re.match(
        r"^(mute|unmute|restore)\s+(.+)$",
        normalized,
    )

    if application_match:

        action = application_match.group(
            1
        )

        requested_app = (
            application_match.group(
                2
            ).strip()
        )

        # Do not turn nonsense into an application name.
        if requested_app in {
            "phrase",
            "it",
            "that",
            "this",
            "the app",
            "application",
        }:

            return None

        app_name = resolve_known_app(
            requested_app
        )

        if app_name is None:
            return None

        if action == "mute":

            tool_name = (
                "mute_application"
            )

        else:

            tool_name = (
                "unmute_application"
            )

        print(
            "[INTENT] Direct media command: "
            f"{tool_name} "
            f"app_name={app_name!r}",
            flush=True,
        )

        result = tool_router.execute(
            tool_name,
            {
                "app_name": app_name,
            },
        )

        print(
            f"[TOOL RESULT] {result}",
            flush=True,
        )

        if result.startswith(
            "STATUS=SUCCESS"
        ):

            if action == "mute":

                return (
                    f"{app_name} has been muted."
                )

            return (
                f"{app_name} has been unmuted."
            )

        return (
            f"I couldn't change the audio for "
            f"{app_name}."
        )

    # --------------------------------------------------------
    # GLOBAL MUTE
    # --------------------------------------------------------

    if normalized in {
        "mute computer",
        "mute the computer",
        "mute system audio",
        "mute all audio",
        "mute the system",
        "mute sound",
    }:

        print(
            "[INTENT] Direct system mute.",
            flush=True,
        )

        result = tool_router.execute(
            "mute_system_audio",
            {},
        )

        print(
            f"[TOOL RESULT] {result}",
            flush=True,
        )

        if result.startswith(
            "STATUS=SUCCESS"
        ):

            return (
                "The computer audio is muted."
            )

        return (
            "I couldn't mute the computer audio."
        )

    # --------------------------------------------------------
    # GLOBAL UNMUTE
    # --------------------------------------------------------

    if normalized in {
        "unmute computer",
        "unmute the computer",
        "unmute system audio",
        "unmute all audio",
        "unmute the system",
        "unmute sound",
        "restore computer audio",
    }:

        print(
            "[INTENT] Direct system unmute.",
            flush=True,
        )

        result = tool_router.execute(
            "unmute_system_audio",
            {},
        )

        print(
            f"[TOOL RESULT] {result}",
            flush=True,
        )

        if result.startswith(
            "STATUS=SUCCESS"
        ):

            return (
                "The computer audio has been restored."
            )

        return (
            "I couldn't restore the computer audio."
        )

    return None


# ============================================================
# COMMAND PIPELINE
# ============================================================

def process_voice_command(
    user_input: str,
    event_bus: EventBus,
    conversation: ConversationManager,
    brain: AIBrain,
    tool_router: ToolRouter,
    log_path: Path,
    guest_mode: bool = False,
) -> str:

    event_bus.publish(
        USER_COMMAND,
        command=user_input,
    )

    active_conversation = conversation

    if guest_mode:
        active_conversation = ConversationManager(
            max_messages=10
        )

    active_conversation.add_user_message(
        user_input
    )

    try:

        # ----------------------------------------------------
        # DIRECT MEDIA INTENT
        # ----------------------------------------------------

        direct_response = (
            try_direct_media_command(
                user_input,
                tool_router,
            )
        )

        if direct_response is not None:

            conversation.add_assistant_message(
                direct_response
            )

            print(
                f"ARIA: {direct_response}",
                flush=True,
            )

            event_bus.publish(
                ARIA_RESPONSE,
                response=direct_response,
            )

            return direct_response

        # ----------------------------------------------------
        # AI
        # ----------------------------------------------------

        response = brain.ask(
            active_conversation.get_messages(),
            tools=tool_router.get_tools(),
            guest_mode=guest_mode,
        )

        assistant_content = (
            response.message.content
            or ""
        )

        tool_calls = (
            response.message.tool_calls
        )

        # ----------------------------------------------------
        # NO TOOL
        # ----------------------------------------------------

        if not tool_calls:

            active_conversation.add_assistant_message(
                assistant_content
            )

            print(
                f"ARIA: {assistant_content}",
                flush=True,
            )

            event_bus.publish(
                ARIA_RESPONSE,
                response=assistant_content,
            )

            return assistant_content

        # ----------------------------------------------------
        # RECORD TOOL CALL
        # ----------------------------------------------------

        active_conversation.add_assistant_message(
            assistant_content,
            tool_calls=[
                {
                    "function": {
                        "name": call.function.name,
                        "arguments": call.function.arguments,
                    }
                }
                for call in tool_calls
            ],
        )

        # ----------------------------------------------------
        # EXECUTE TOOLS
        # ----------------------------------------------------

        for call in tool_calls:

            tool_name = (
                call.function.name
            )

            arguments = (
                call.function.arguments
            )

            if arguments is None:

                arguments = {}

            if not isinstance(
                arguments,
                dict,
            ):

                try:

                    arguments = json.loads(
                        arguments
                    )

                except Exception:

                    arguments = {}

            log_event(
                (
                    "TOOL REQUEST: "
                    f"{tool_name} "
                    f"{arguments}"
                ),
                log_path,
            )

            print(
                f"[TOOL] "
                f"{tool_name}"
                f"({arguments})",
                flush=True,
            )

            result = (
                tool_router.execute(
                    tool_name,
                    arguments,
                )
            )

            log_event(
                f"TOOL RESULT: {result}",
                log_path,
            )

            print(
                f"[TOOL RESULT] {result}",
                flush=True,
            )

            active_conversation.add_tool_result(
                result
            )

        # ----------------------------------------------------
        # FINAL RESPONSE
        # ----------------------------------------------------

        final_response = brain.ask(
            active_conversation.get_messages(),
            guest_mode=guest_mode,
        )

        final_content = (
            final_response.message.content
            or ""
        )

        active_conversation.add_assistant_message(
            final_content
        )

        print(
            f"ARIA: {final_content}",
            flush=True,
        )

        event_bus.publish(
            ARIA_RESPONSE,
            response=final_content,
        )

        return final_content

    except Exception as exc:

        error_message = (
            "I encountered an error while "
            f"processing that: {exc}"
        )

        print(
            f"ARIA: {error_message}",
            flush=True,
        )

        log_event(
            f"ERROR: {exc}",
            log_path,
        )

        event_bus.publish(
            ARIA_RESPONSE,
            response=error_message,
        )

        return error_message


# ============================================================
# MAIN
# ============================================================

def main() -> None:

    profile = load_json(
        PROFILE_PATH
    )

    settings = load_json(
        SETTINGS_PATH
    )

    log_path = Path(
        settings["log_path"]
    )

    # --------------------------------------------------------
    # EVENT BUS
    # --------------------------------------------------------

    event_bus = EventBus()

    event_bus.subscribe(
        USER_COMMAND,
        lambda command: log_event(
            f"USER: {command}",
            log_path,
        ),
    )

    event_bus.subscribe(
        ARIA_RESPONSE,
        lambda response: log_event(
            f"ARIA: {response}",
            log_path,
        ),
    )

    event_bus.subscribe(
        CORE_STARTED,
        lambda: log_event(
            "CORE INITIALIZED",
            log_path,
        ),
    )

    event_bus.subscribe(
        CORE_SHUTDOWN,
        lambda: log_event(
            "CORE SHUTDOWN",
            log_path,
        ),
    )

    # --------------------------------------------------------
    # APPLICATION REGISTRY
    # --------------------------------------------------------

    registry_path = (
        PROJECT_ROOT
        / "config"
        / "applications.json"
    )

    app_registry = (
        AppRegistry(
            registry_path
        )
    )

    application_tools = (
        ApplicationTools(
            app_registry
        )
    )

    # --------------------------------------------------------
    # TOOL ROUTER
    # --------------------------------------------------------

    tool_router = ToolRouter()

    register_optional_tool(
        tool_router,
        "launch",
        application_tools,
    )

    register_optional_tool(
        tool_router,
        "open",
        application_tools,
    )

    register_optional_tool(
        tool_router,
        "close",
        application_tools,
    )

    tool_router.register(
        "calculate",
        calculate,
    )

    tool_router.register(
        "get_current_time",
        get_current_time,
    )

    tool_router.register(
        "get_current_date",
        get_current_date,
    )

    tool_router.register(
        "get_current_datetime",
        get_current_datetime,
    )

    tool_router.register(
        "get_cpu_usage",
        get_cpu_usage,
    )

    tool_router.register(
        "get_ram_usage",
        get_ram_usage,
    )

    tool_router.register(
        "get_gpu_info",
        get_gpu_info,
    )

    tool_router.register(
        "get_disk_space",
        get_disk_space,
    )

    tool_router.register(
        "get_battery",
        get_battery,
    )

    tool_router.register(
        "get_running_applications",
        get_running_applications,
    )

    tool_router.register(
        "get_system_status",
        get_system_status,
    )

    # --------------------------------------------------------
    # MEDIA TOOLS
    # --------------------------------------------------------

    register_media_tools(
        tool_router
    )

    # --------------------------------------------------------
    # AI
    # --------------------------------------------------------

    brain = AIBrain()

    conversation = (
        ConversationManager(
            max_messages=30
        )
    )

    # --------------------------------------------------------
    # SPEECH
    # --------------------------------------------------------

    speech_listener = (
        SpeechListener(
            model_path=(
                PROJECT_ROOT
                / "voice"
                / "model-whisper-small-en"
            )
        )
    )

    # --------------------------------------------------------
    # VOICE CONTROLLER
    # --------------------------------------------------------

    voice_controller = (
        VoiceController(
            command_callback=lambda command:
                process_voice_command(
                    command,
                    event_bus,
                    conversation,
                    brain,
                    tool_router,
                    log_path,
                    guest_mode=voice_controller.is_guest_mode(),
                ),
            speech_listener=speech_listener,
        )
    )

    # --------------------------------------------------------
    # STARTUP
    # --------------------------------------------------------

    event_bus.publish(
        CORE_STARTED
    )

    print(
        "=" * 60
    )

    print(
        f"{profile['name']} — "
        f"{profile['version']}"
    )

    print(
        f"Meaning: "
        f"{profile['meaning']}"
    )

    print(
        f"Owner: "
        f"{profile['owner']}"
    )

    print(
        f"Build: "
        f"{profile['build']}"
    )

    print(
        "=" * 60
    )

    print(
        "CORE ONLINE"
    )

    print(
        "AI ONLINE"
    )

    print(
        "TOOLS ONLINE"
    )

    print(
        "MEMORY ONLINE"
    )

    print(
        "SYSTEM AWARENESS ONLINE"
    )

    print(
        "VOICE ONLINE"
    )

    print(
        "=" * 60
    )

    print(
        "Say 'ARIA' to begin."
    )

    print(
        "Normal ARIA mode stays conversational."
    )

    print(
        "Guest Mode requires ARIA before each interaction."
    )

    print(
        "=" * 60
    )

    # VoiceController.start() owns its own internal thread.
    voice_controller.start()

    shutdown_requested = False
    last_interrupt_time = 0.0
    interrupt_notice_time = 0.0
    shutdown_event = __import__("threading").Event()
    restart_count = 0

    def handle_sigint(signum, frame):
        nonlocal shutdown_requested
        nonlocal last_interrupt_time
        nonlocal interrupt_notice_time

        now = time.monotonic()

        # Never let Ctrl+C traffic tear down an active voice session.
        # ARIA's voice interruption path is separate from console shutdown.
        state = getattr(voice_controller, "state", None)
        active_state = getattr(
            voice_controller,
            "STATE_ACTIVE",
            "active",
        )
        guest_state = getattr(
            voice_controller,
            "STATE_GUEST",
            "guest",
        )

        if state in {active_state, guest_state}:
            if now - interrupt_notice_time >= 2.0:
                print(
                    "\n[CORE] Ctrl+C ignored while ARIA is active; "
                    "voice session remains running.",
                    flush=True,
                )
                interrupt_notice_time = now
            return

        # Only the idle/guest boundary may arm console shutdown.
        # Debounce repeated terminal events so one burst cannot count as
        # multiple deliberate presses.
        if now - last_interrupt_time < 1.0:
            return

        last_interrupt_time = now

        if not shutdown_requested:
            shutdown_requested = True
            print(
                "\n[CORE] Ctrl+C received while idle. "
                "Press Ctrl+C again within 3s to shut down.",
                flush=True,
            )
            return

        shutdown_event.set()

    previous_sigint = signal.getsignal(signal.SIGINT)
    signal.signal(signal.SIGINT, handle_sigint)

    try:
        while not shutdown_event.is_set():
            if not voice_controller.running and not shutdown_requested:
                restart_count += 1
                print(
                    "[CORE] Voice controller stopped unexpectedly; "
                    f"keeping ARIA online and restarting the voice loop "
                    f"(attempt={restart_count}).",
                    flush=True,
                )
                try:
                    voice_controller.start()
                except Exception as exc:
                    print(
                        f"[CORE] Voice controller restart failed: {exc}",
                        flush=True,
                    )
                    time.sleep(1.0)
                    continue

            time.sleep(0.25)

    finally:
        signal.signal(signal.SIGINT, previous_sigint)

        if shutdown_event.is_set():
            print(
                "\n[CORE] Shutdown requested.",
                flush=True,
            )


        voice_controller.stop()

        try:

            speech_listener.close()

        except Exception:
            pass

        try:

            from tools import media_tools

            media_tools.close()

        except Exception:
            pass

        event_bus.publish(
            CORE_SHUTDOWN
        )

        print(
            "ARIA: Goodbye, Beau.",
            flush=True,
        )


if __name__ == "__main__":
    main()