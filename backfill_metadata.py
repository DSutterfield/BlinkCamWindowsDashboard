"""
Backfill .json sidecar metadata files for all existing MP4 clips.
Run once to catch up. Idempotent — re-running is safe and skips clips
that already have sidecars.
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
    read_sidecar,
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


async def fetch_all_events(blink, days_back: int = 90) -> list:
    """Fetch rich Blink media metadata for historical sidecar enrichment."""

    since = (
        datetime.now(timezone.utc) - timedelta(days=days_back)
    ).strftime("%Y/%m/%d %H:%M:%S")

    print(
        f"  Fetching rich media metadata for the last "
        f"{days_back} days..."
    )

    events = await blink.get_videos_metadata(
        since=since,
        stop=100,
    )

    print(f"  Retrieved {len(events)} Blink media events.")
    return events

async def main():
    print(f"Reading clips from: {CLIPS_DIR}")

    if not CLIPS_DIR.exists():
        print("Clip directory does not exist.")
        return

    all_mp4s = list(CLIPS_DIR.glob("*.mp4"))
    print(f"Found {len(all_mp4s)} MP4 files.")

    saved = json.loads(CREDS_PATH.read_text())

    async with ClientSession() as session:
        blink = Blink(session=session)
        blink.auth = Auth(saved, no_prompt=True, session=session)
        await blink.start()

        print("\nFetching rich event history from Blink...")
        events = await fetch_all_events(blink, days_back=90)

        events_by_id = {
            event.get("id"): event
            for event in events
            if event.get("id") is not None
        }

        print(
            f"Got {len(events_by_id)} identifiable Blink events.\n"
        )

        updated_sidecars = 0
        unchanged_sidecars = 0
        no_matching_event = 0
        no_sidecar = 0

        fields_to_backfill = (
            "network_id",
            "network_name",
            "thumbnail",
        )

        print("Enriching existing sidecars...")

        for mp4 in all_mp4s:
            sidecar = read_sidecar(mp4)

            if not sidecar:
                no_sidecar += 1
                continue

            event_id = sidecar.get("id")
            event = events_by_id.get(event_id)

            if not event:
                no_matching_event += 1
                continue

            changed = False

            for field in fields_to_backfill:
                new_value = event.get(field)

                if (
                    new_value is not None
                    and sidecar.get(field) != new_value
                ):
                    sidecar[field] = new_value
                    changed = True

            if changed:
                metadata_path_for(mp4).write_text(
                    json.dumps(sidecar, indent=2)
                )
                updated_sidecars += 1
            else:
                unchanged_sidecars += 1

        print("\nBackfill complete.")
        print(f"  Updated sidecars:     {updated_sidecars}")
        print(f"  Already up to date:   {unchanged_sidecars}")
        print(f"  No matching event:    {no_matching_event}")
        print(f"  Missing sidecar:      {no_sidecar}")

if __name__ == "__main__":
    asyncio.run(main())