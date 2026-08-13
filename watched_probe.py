"""
watched_probe.py

Diagnostic test for Blink clip review status.

This probe:
1. Connects to Blink using the saved credentials.
2. Finds recent media events whose Blink "watched" flag is false.
3. Lets one event be selected.
4. Performs the same authenticated media GET used by BlinkPy's downloader.
5. Re-fetches Blink metadata and reports whether "watched" changed.

This program does not modify Dashboard code or local sidecars.
"""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from aiohttp import ClientSession
from blinkpy.auth import Auth, BlinkTwoFARequiredError
from blinkpy.blinkpy import Blink


ROOT = Path(__file__).parent
CREDS_PATH = ROOT / "config" / "credentials.json"


def load_creds():
    if CREDS_PATH.exists():
        with open(CREDS_PATH, "r") as f:
            return json.load(f)
    return None


async def setup_blink(session):
    saved = load_creds()

    if not saved:
        raise RuntimeError(
            "No config/credentials.json found. "
            "Run first_login.py first."
        )

    blink = Blink(session=session)
    blink.auth = Auth(saved, no_prompt=True, session=session)

    try:
        await blink.start()
    except BlinkTwoFARequiredError as exc:
        raise RuntimeError(
            "Saved Blink token has expired. "
            "Re-run first_login.py."
        ) from exc

    return blink


async def get_recent_events(blink):
    since = (
        datetime.now(timezone.utc) - timedelta(hours=24)
    ).strftime("%Y/%m/%d %H:%M:%S")

    events = await blink.get_videos_metadata(
        since=since,
        stop=10,
    )

    # 2026-08-13 - Dan/Sage:
    # Temporary diagnostic while determining whether Blink media events
    # contain a system/network identifier needed by the clip-list display.
    if events:
        print("\nRaw Blink media-event fields:")
        print(sorted(events[0].keys()))

        print("\nFirst raw media event:")
        print(json.dumps(events[0], indent=2, default=str))

    return events

async def find_event_by_id(blink, event_id):
    events = await get_recent_events(blink)

    for event in events:
        if event.get("id") == event_id:
            return event

    return None


async def main():
    async with ClientSession() as session:
        blink = await setup_blink(session)

        events = await get_recent_events(blink)

        unreviewed = [
            event
            for event in events
            if event.get("watched") is False
            and event.get("media")
            and event.get("id") is not None
        ]

        if not unreviewed:
            print("No unreviewed Blink events found in the last 24 hours.")
            return

        print("\nUnreviewed Blink events:\n")

        for number, event in enumerate(unreviewed, start=1):
            print(
                f"{number:2}. "
                f"{event.get('device_name', 'Unknown camera')} | "
                f"{event.get('created_at')} | "
                f"ID {event.get('id')}"
            )

        print()

        while True:
            choice = input(
                f"Select an event (1-{len(unreviewed)}), "
                "or press Enter to cancel: "
            ).strip()

            if not choice:
                print("Cancelled.")
                return

            try:
                number = int(choice)

                if 1 <= number <= len(unreviewed):
                    break
            except ValueError:
                pass

            print("Invalid selection.")

        selected = unreviewed[number - 1]
        event_id = selected["id"]

        print("\nSelected event:")
        print(f"  Camera:     {selected.get('device_name')}")
        print(f"  Created:    {selected.get('created_at')}")
        print(f"  Event ID:   {event_id}")
        print(f"  Watched:    {selected.get('watched')}")
        print(f"  Updated at: {selected.get('updated_at')}")

        answer = input(
            "\nMark this Blink event as viewed? [y/N]: "
        ).strip().lower()

        if answer != "y":
            print("Cancelled. No media request was made.")
            return

        print("\nMarking event as viewed...")

        url = (
            f"{blink.urls.base_url}/api/v4/accounts/{blink.account_id}"
            f"/media/mark_as_viewed"
        )

        headers = dict(blink.auth.header)
        headers["Content-Type"] = "application/json"

        body = {
            "media_list": [event_id]
        }

        await blink.auth.query(
            url=url,
            data=json.dumps(body),
            headers=headers,
            reqtype="post",
            json_resp=False,
        )

        print("Mark-as-viewed POST completed.")

        print("\nChecking Blink review status...")

        for attempt in range(1, 6):
            await asyncio.sleep(2)

            refreshed = await find_event_by_id(blink, event_id)

            if refreshed is None:
                print(
                    f"Attempt {attempt}: event ID {event_id} "
                    "was not returned by Blink."
                )
                continue

            print(
                f"Attempt {attempt}: "
                f"watched={refreshed.get('watched')}, "
                f"updated_at={refreshed.get('updated_at')}"
            )

            if refreshed.get("watched") is True:
                print(
                    "\nSUCCESS: Blink changed this event "
                    "from watched=false to watched=true."
                )
                return

        print(
            "\nBlink still reports watched=false after the media GET."
        )


if __name__ == "__main__":
    asyncio.run(main())