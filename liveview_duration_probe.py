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
import time

from aiohttp import ClientSession
from blinkpy.auth import Auth
from blinkpy.blinkpy import Blink
from blinkpy import api


CREDS_PATH = Path("config/credentials.json")
PROBE_SECONDS = 90


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

            print(f"Command ID:       {stream.command_id}")
            print(f"Polling interval: {stream.polling_interval}")
            print(f"Blink server:     {stream.target.geturl()}")

            await stream.start()

            host, port = stream.socket.getsockname()[:2]

            print(f"Local stream relay: {stream.url}")
            print("Connecting diagnostic reader...")

            local_reader, local_writer = await asyncio.open_connection(
                host,
                port,
            )

            started_at = time.monotonic()

            async def probe_poll():
                try:
                    while not stream.target_reader.at_eof():
                        elapsed = time.monotonic() - started_at

                        response = await api.request_command_status(
                            blink,
                            camera.network_id,
                            stream.command_id,
                        )

                        print(
                            f"[{elapsed:6.1f}s] "
                            f"status_code={response.get('status_code')}"
                        )

                        for command in response.get("commands", []):
                            if command.get("id") == stream.command_id:
                                print(
                                    "          "
                                    f"state_condition={command.get('state_condition')!r}, "
                                    f"state_stage={command.get('state_stage')!r}"
                                )

                                if command.get("state_condition") not in (
                                    "new",
                                    "running",
                                ):
                                    return

                        await asyncio.sleep(stream.polling_interval)

                finally:
                    elapsed = time.monotonic() - started_at

                    print(
                        f"\n[{elapsed:6.1f}s] "
                        "Command polling finished."
                    )

                    response = await api.request_command_done(
                        blink,
                        camera.network_id,
                        stream.command_id,
                    )

                    print(f"Done response: {response}")

            stream.poll = probe_poll

            async def probe_recv():
                """Receive complete IMMI packets using readexactly()."""
                try:
                    while not stream.target_reader.at_eof():
                        try:
                            header = await stream.target_reader.readexactly(9)
                        except asyncio.IncompleteReadError as exc:
                            print(
                                f"IMMI header ended early: "
                                f"{len(exc.partial)} bytes received, expected 9."
                            )
                            break

                        msgtype = header[0]
                        payload_length = int.from_bytes(
                            header[5:9],
                            byteorder="big",
                        )

                        if payload_length <= 0:
                            continue

                        try:
                            data = await stream.target_reader.readexactly(
                                payload_length
                            )
                        except asyncio.IncompleteReadError as exc:
                            print(
                                f"IMMI payload ended early: "
                                f"{len(exc.partial)} bytes received, "
                                f"expected {payload_length}."
                            )
                            break

                        if msgtype != 0x00:
                            continue

                        if not data or data[0] != 0x47:
                            continue

                        for writer in stream.clients:
                            if not writer.is_closing():
                                writer.write(data)
                                await writer.drain()

                        await asyncio.sleep(0)

                finally:
                    if (
                        stream.target_writer is not None
                        and not stream.target_writer.is_closing()
                    ):
                        stream.target_writer.close()

            # feed() connects to Blink and relays the live transport stream
            # to the local TCP client opened immediately above.
            async def feed_with_command_poll():
                await stream.auth()

                try:
                    await asyncio.gather(
                        probe_recv(),
                        stream.send(),
                        probe_poll(),
                    )
                finally:
                    stream.stop()

            feed_task = asyncio.create_task(feed_with_command_poll())

            total_bytes = 0

            print(
                f"\nWatching Live View for up to {PROBE_SECONDS} seconds..."
            )

            while True:
                elapsed = time.monotonic() - started_at

                if elapsed >= PROBE_SECONDS:
                    print(
                        f"\n[{elapsed:6.1f}s] "
                        "Reached probe time limit."
                    )
                    break

                try:
                    data = await asyncio.wait_for(
                        local_reader.read(188 * 100),
                        timeout=5,
                    )
                except asyncio.TimeoutError:
                    elapsed = time.monotonic() - started_at

                    print(
                        f"[{elapsed:6.1f}s] "
                        "No video data received for 5 seconds."
                    )

                    if feed_task.done():
                        print("Stream feed task has ended.")
                        break

                    continue

                if not data:
                    elapsed = time.monotonic() - started_at

                    print(
                        f"\n[{elapsed:6.1f}s] "
                        "Live stream closed."
                    )
                    break

                total_bytes += len(data)

            elapsed = time.monotonic() - started_at

            print("\nProbe summary:")
            print(f"  Elapsed:        {elapsed:.1f} seconds")
            print(f"  Bytes received: {total_bytes:,}")
            print(f"  Feed finished:  {feed_task.done()}")

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