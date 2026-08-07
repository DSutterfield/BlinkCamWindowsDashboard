"""
liveview_cooldown_probe.py

Diagnostic test for Blink Live View restart timing.

2026-08-07 - Dan/Sage:
Created to determine whether the Dashboard's fixed 45-second Live View
cooldown is necessary.  This test does not change Dashboard behavior.

It:
1. Starts Live View.
2. Waits for the first frame.
3. Stops Live View and measures BlinkPy shutdown time.
4. Waits a selected cooldown interval.
5. Attempts to start Live View again.
"""

from __future__ import annotations

import time

from liveview_bridge import LiveViewBridge


CAMERA_NAME = "Well House"
COOLDOWN_SECONDS = 20


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

        input("\nLive View is running. Press Enter to STOP it...")

        stop_time = time.perf_counter()
        bridge.stop()
        stop_elapsed = time.perf_counter() - stop_time

        print(
            f"\nbridge.stop() completed after "
            f"{stop_elapsed:.2f} seconds."
        )

        print(f"\nWaiting {COOLDOWN_SECONDS} seconds before restart...")
        time.sleep(COOLDOWN_SECONDS)

        print("\nAttempting second Live View...")
        restart_time = time.perf_counter()

        try:
            bridge.start(CAMERA_NAME)

            restart_elapsed = time.perf_counter() - restart_time

            print(
                f"\nSUCCESS: Second Live View became ready after "
                f"{restart_elapsed:.2f} seconds."
            )

            input("\nSecond Live View is running. Press Enter to stop...")

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