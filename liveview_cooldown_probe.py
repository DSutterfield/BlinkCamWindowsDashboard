"""
liveview_cooldown_probe.py

Diagnostic test for Blink Live View restart timing.

2026-08-07 - Dan/Sage:
Determine whether the Dashboard's fixed 45-second Live View cooldown is
necessary and observe Blink's command state without changing production
Live View behavior.

This diagnostic intentionally accesses a few LiveViewBridge private members.
That is acceptable here because this file is an experiment, not production
Dashboard code.
"""

from __future__ import annotations

import asyncio
import time

from blinkpy import api

from liveview_bridge import LiveViewBridge


CAMERA_NAME = "Well House"
COOLDOWN_SECONDS = 20


def command_status(
    bridge: LiveViewBridge,
    network_id: int,
    command_id: int,
) -> dict:
    """Query Blink for one Live View command on the bridge event loop."""

    async def query() -> dict:
        if bridge._blink is None:
            raise RuntimeError("Blink connection is unavailable.")

        return await api.request_command_status(
            bridge._blink,
            network_id,
            command_id,
        )

    future = asyncio.run_coroutine_threadsafe(
        query(),
        bridge._loop,
    )

    response = future.result(timeout=15)

    command = next(
        (
            item
            for item in response.get("commands", [])
            if str(item.get("id")) == str(command_id)
        ),
        None,
    )

    return {
        "status_code": response.get("status_code"),
        "found": command is not None,
        "condition": (
            command.get("state_condition") if command else None
        ),
        "stage": (
            command.get("state_stage") if command else None
        ),
    }


def show_command_status(
    label: str,
    bridge: LiveViewBridge,
    network_id: int,
    command_id: int,
) -> None:
    """Print Blink's state for the selected Live View command."""

    try:
        status = command_status(
            bridge,
            network_id,
            command_id,
        )

        print(
            f"{label}: "
            f"command={command_id}, "
            f"network={network_id}, "
            f"http_status={status['status_code']}, "
            f"found={status['found']}, "
            f"condition={status['condition']}, "
            f"stage={status['stage']}"
        )

    except Exception as exc:
        print(
            f"{label}: status query failed: "
            f"{type(exc).__name__}: {exc}"
        )


def main() -> None:
    bridge = LiveViewBridge()

    try:
        print(f"\nStarting first Live View: {CAMERA_NAME}")

        start_time = time.perf_counter()
        bridge.start(CAMERA_NAME)

        print(
            f"First Live View ready after "
            f"{time.perf_counter() - start_time:.2f} seconds."
        )

        stream = bridge._stream

        if stream is None:
            raise RuntimeError(
                "Live View started, but the Blink stream object is missing."
            )

        command_id = stream.command_id
        network_id = stream.camera.network_id

        print(
            f"Blink Live View command: "
            f"network={network_id}, command={command_id}"
        )

        show_command_status(
            "Before Stop",
            bridge,
            network_id,
            command_id,
        )

        input("\nLive View is running. Press Enter to STOP it...")

        stop_time = time.perf_counter()
        bridge.stop()
        stop_elapsed = time.perf_counter() - stop_time

        print(
            f"\nbridge.stop() completed after "
            f"{stop_elapsed:.2f} seconds."
        )

        show_command_status(
            "Immediately after Stop",
            bridge,
            network_id,
            command_id,
        )

        print(
            f"\nWaiting {COOLDOWN_SECONDS} seconds before restart..."
        )
        time.sleep(COOLDOWN_SECONDS)

        show_command_status(
            f"After {COOLDOWN_SECONDS} seconds",
            bridge,
            network_id,
            command_id,
        )

        print("\nAttempting second Live View...")

        restart_time = time.perf_counter()

        try:
            bridge.start(CAMERA_NAME)

            restart_elapsed = time.perf_counter() - restart_time

            print(
                f"\nSUCCESS: Second Live View became ready after "
                f"{restart_elapsed:.2f} seconds."
            )

            input(
                "\nSecond Live View is running. "
                "Press Enter to stop..."
            )

        except Exception as exc:
            restart_elapsed = time.perf_counter() - restart_time

            print(
                f"\nFAILED after {restart_elapsed:.2f} seconds:"
            )
            print(f"{type(exc).__name__}: {exc}")

    finally:
        print("\nCleaning up...")
        bridge.shutdown()
        print("Cooldown probe finished.")


if __name__ == "__main__":
    main()