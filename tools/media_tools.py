from __future__ import annotations

from voice.media_controller import MediaController


# One persistent MediaController for the entire ARIA process.
#
# This is important because application unmute restores the state that
# was saved when the application was muted.
_CONTROLLER = MediaController()


def mute_system_audio() -> str:
    """
    Mute the Windows system speaker/output audio.
    """

    success = _CONTROLLER.mute()

    if success:
        return (
            "STATUS=SUCCESS "
            "Windows system audio was muted."
        )

    return (
        "STATUS=FAILED "
        "Windows system audio could not be muted."
    )


def unmute_system_audio() -> str:
    """
    Restore the previous Windows system speaker/output audio state.
    """

    success = _CONTROLLER.unmute()

    if success:
        return (
            "STATUS=SUCCESS "
            "Previous Windows system audio state was restored."
        )

    return (
        "STATUS=FAILED "
        "Windows system audio could not be restored."
    )


def mute_application(
    app_name: str,
) -> str:
    """
    Mute an individual application's Windows audio session.
    """

    app_name = str(
        app_name or ""
    ).strip()

    if not app_name:
        return (
            "STATUS=FAILED "
            "No application name was provided."
        )

    success = (
        _CONTROLLER.mute_application(
            app_name
        )
    )

    if success:
        return (
            "STATUS=SUCCESS "
            f"Audio for '{app_name}' was muted."
        )

    return (
        "STATUS=FAILED "
        f"Audio for '{app_name}' could not be muted."
    )


def unmute_application(
    app_name: str,
) -> str:
    """
    Restore an application's previous Windows audio state.
    """

    app_name = str(
        app_name or ""
    ).strip()

    if not app_name:
        return (
            "STATUS=FAILED "
            "No application name was provided."
        )

    success = (
        _CONTROLLER.unmute_application(
            app_name
        )
    )

    if success:
        return (
            "STATUS=SUCCESS "
            f"Previous audio state for '{app_name}' "
            "was restored."
        )

    return (
        "STATUS=FAILED "
        f"Audio for '{app_name}' could not be restored."
    )


def list_audio_sessions() -> str:
    """
    Return currently active readable Windows audio sessions.
    """

    try:

        sessions = (
            _CONTROLLER.list_applications()
        )

    except Exception as exc:

        return (
            "STATUS=FAILED "
            f"Could not list audio sessions: {exc}"
        )

    if not sessions:

        return (
            "STATUS=SUCCESS "
            "No readable active audio sessions were found."
        )

    lines = []

    for session in sessions:

        process = session.get(
            "process",
            "unknown",
        )

        display = session.get(
            "display",
            "unknown",
        )

        pid = session.get(
            "pid",
            "unknown",
        )

        lines.append(
            f"process={process} "
            f"display={display} "
            f"pid={pid}"
        )

    return (
        "STATUS=SUCCESS "
        "Active audio sessions:\n"
        + "\n".join(lines)
    )


def close() -> None:
    """
    Release the MediaController resources.
    """

    try:
        _CONTROLLER.close()
    except Exception:
        pass