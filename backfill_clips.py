"""
Historical Blink clip backfill utility.

Downloads older Blink clips that are not already present and creates
metadata sidecars for newly downloaded clips.

This is a one-time/manual utility.  It is separate from blink_dvr.py,
which remains the continuous 24-hour DVR poller.
"""

import asyncio
import configparser
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from aiohttp import ClientSession
from blinkpy.blinkpy import Blink
from blinkpy.auth import Auth

from metadata_helper import (
    metadata_path_for,
    write_sidecar,
    match_event_to_file,
)


ROOT = Path(__file__).parent
CONFIG_PATH = ROOT / "config" / "settings.ini"
LOCAL_CONFIG_PATH = ROOT / "config" / "settings.local.ini"
CREDS_PATH = ROOT / "config" / "credentials.json"

config = configparser.ConfigParser()
config.read([CONFIG_PATH, LOCAL_CONFIG_PATH])

CLIPS_DIR = Path(config["download"]["output_dir"])

# Start conservatively.  We can increase these after the first test.
DAYS_BACK = 7
PAGE_STOP = 100


async def main():
    print(f"Historical clip backfill")
    print(f"Clip directory: {CLIPS_DIR}")
    print(f"Looking back:   {DAYS_BACK} days")

    if not CLIPS_DIR.exists():
        print("Clip directory does not exist.")
        return

    saved = json.loads(CREDS_PATH.read_text())

    since = (
        datetime.now(timezone.utc) - timedelta(days=DAYS_BACK)
    ).strftime("%Y/%m/%d %H:%M:%S")

    before = set(CLIPS_DIR.rglob("*.mp4"))
    print(f"Existing MP4 files: {len(before)}")

    async with ClientSession() as session:
        blink = Blink(session=session)
        blink.auth = Auth(saved, no_prompt=True, session=session)
        await blink.start()

        print("\nFetching historical Blink metadata...")

        events = await blink.get_videos_metadata(
            since=since,
            stop=PAGE_STOP,
        )

        print(f"Retrieved {len(events)} Blink media events.")

        print("\nDownloading missing historical clips...")

        await blink.download_videos(
            path=str(CLIPS_DIR),
            since=since,
            camera="all",
            stop=PAGE_STOP,
            delay=1,
        )

        after = set(CLIPS_DIR.rglob("*.mp4"))
        new_files = sorted(after - before)

        print(f"\nDownloaded {len(new_files)} new MP4 file(s).")

        sidecar_count = 0
        unmatched_count = 0

        for mp4 in new_files:
            matched_event = None

            for event in events:
                matched = match_event_to_file(event, [mp4])
                if matched:
                    matched_event = event
                    break

            if matched_event is None:
                unmatched_count += 1
                print(f"  No metadata match: {mp4.name}")
                continue

            if not metadata_path_for(mp4).exists():
                write_sidecar(mp4, matched_event)
                sidecar_count += 1

        print(f"Wrote {sidecar_count} metadata sidecar(s).")

        if unmatched_count:
            print(
                f"{unmatched_count} downloaded clip(s) did not "
                f"receive a sidecar."
            )

    print("\nHistorical clip backfill complete.")


if __name__ == "__main__":
    asyncio.run(main())
