"""
liveview_raw.py

Diagnostic test for Blink live view.

This test:
1. Connects to Blink using the saved credentials.
2. Lists all discovered cameras.
3. Allows one camera to be selected.
4. Starts Blink's live-view stream.
5. Opens Blinkpy's local TCP relay.
6. Verifies that live MPEG transport-stream data is received.
7. Stops the stream cleanly.

This program does not yet display the video in the Dashboard.
"""

import asyncio
import contextlib
import json
from pathlib import Path

from aiohttp import ClientSession
from blinkpy.auth import Auth
from blinkpy.blinkpy import Blink


CREDS_PATH = Path("config/credentials.json")
STREAM_TIMEOUT_SECONDS = 30


def select_camera(blink: Blink):
    """Display discovered cameras and return the selected camera."""

    cameras = sorted(
        blink.cameras.items(),
        key=lambda item: item[0].lower(),
    )

    if not cameras:
        raise RuntimeError("Blink did not discover any cameras.")

    print("\nAvailable cameras:\n")

    for number, (name, camera) in enumerate(cameras, start=1):
        print(
            f"{number:2}. {name} "
            f"({type(camera).__name__}, "
            f"camera_type={camera.camera_type!r})"
        )

    while True:
        selection = input("\nEnter camera number: ").strip()

        try:
            selected_number = int(selection)
        except ValueError:
            print("Please enter one of the displayed camera numbers.")
            continue

        if 1 <= selected_number <= len(cameras):
            return cameras[selected_number - 1]

        print("That camera number is outside the displayed range.")


async def main():
    """Run one isolated live-view transport test."""

    if not CREDS_PATH.exists():
        raise FileNotFoundError(
            f"Saved Blink credentials were not found at {CREDS_PATH}"
        )

    saved_credentials = json.loads(
        CREDS_PATH.read_text(encoding="utf-8")
    )

    async with ClientSession() as session:
        blink = Blink(session=session)
        blink.auth = Auth(
            saved_credentials,
            no_prompt=True,
            session=session,
        )

        print("Connecting to Blink...")
        await blink.start()

        camera_name, camera = select_camera(blink)

        stream = None
        feed_task = None
        local_writer = None

        try:
            print(f"\nRequesting live view for {camera_name}...")

            stream = await camera.init_livestream()
            await stream.start()

            host, port = stream.socket.getsockname()[:2]

            print(f"Local stream relay: {stream.url}")
            print("Connecting diagnostic reader...")

            local_reader, local_writer = await asyncio.open_connection(
                host,
                port,
            )

            # feed() connects to Blink and relays the live transport stream
            # to the local TCP client opened immediately above.
            feed_task = asyncio.create_task(stream.feed())

            print(
                f"Waiting up to {STREAM_TIMEOUT_SECONDS} seconds "
                "for live video data..."
            )

            data = await asyncio.wait_for(
                local_reader.read(188 * 20),
                timeout=STREAM_TIMEOUT_SECONDS,
            )

            if not data:
                print("\nFAILED: The local stream closed without sending data.")
                return

            print(f"\nReceived {len(data):,} bytes of live-stream data.")

            if data[0] == 0x47:
                print(
                    "SUCCESS: The data begins with the MPEG transport-stream "
                    "synchronization byte 0x47."
                )
                print("Blink live view is reaching this computer.")
            else:
                print(
                    "PARTIAL SUCCESS: Stream data was received, but its first "
                    f"byte was 0x{data[0]:02X} instead of 0x47."
                )

        except asyncio.TimeoutError:
            print(
                "\nFAILED: No live-stream data arrived before the "
                f"{STREAM_TIMEOUT_SECONDS}-second timeout."
            )

        except NotImplementedError as exc:
            print(f"\nUNSUPPORTED LIVE-VIEW RESPONSE: {exc}")

        except Exception as exc:
            print(f"\nERROR: {type(exc).__name__}: {exc}")

        finally:
            print("\nStopping live view...")

            if local_writer is not None:
                local_writer.close()
                with contextlib.suppress(Exception):
                    await local_writer.wait_closed()

            if stream is not None:
                stream.stop()

            if feed_task is not None and not feed_task.done():
                feed_task.cancel()
                with contextlib.suppress(
                    asyncio.CancelledError,
                    Exception,
                ):
                    await feed_task

            print("Live-view test finished.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nLive-view test interrupted.")