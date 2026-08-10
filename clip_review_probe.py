"""
clip_review_probe.py

Read-only diagnostic probe for Blink clip/event review status.

This program:
1. Connects to Blink using the saved credentials.
2. Fetches the most recent page of raw media events.
3. Displays the newest raw event exactly as Blink returned it.
4. Searches that event for fields whose names might represent
   viewed/reviewed/watched status.

It does not modify Blink data, downloaded clips, sidecars, or the Dashboard.
"""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from aiohttp import ClientSession
from blinkpy.auth import Auth
from blinkpy.blinkpy import Blink


ROOT = Path(__file__).parent
CREDS_PATH = ROOT / "config" / "credentials.json"

CANDIDATE_WORDS = (
    "review",
    "view",
    "watch",
    "seen",
    "read",
    "play",
)


def find_candidate_fields(value, path=""):
    """Recursively find fields whose names may indicate review/view status."""

    matches = []

    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key

            key_lower = key.lower()
            if any(word in key_lower for word in CANDIDATE_WORDS):
                matches.append((child_path, child))

            matches.extend(find_candidate_fields(child, child_path))

    elif isinstance(value, list):
        for index, child in enumerate(value):
            child_path = f"{path}[{index}]"
            matches.extend(find_candidate_fields(child, child_path))

    return matches


async def main():
    saved = json.loads(CREDS_PATH.read_text())

    async with ClientSession() as session:
        blink = Blink(session=session)
        blink.auth = Auth(saved, no_prompt=True, session=session)

        print("Connecting to Blink...")
        await blink.start()

        since = (
            datetime.now(timezone.utc) - timedelta(days=2)
        ).strftime("%Y-%m-%dT%H:%M:%S+0000")

        url = (
            f"{blink.urls.base_url}/api/v1/accounts/{blink.account_id}"
            f"/media/changed?since={since}&page=1"
        )

        print("Fetching recent raw media events...")

        response = await blink.auth.query(
            url=url,
            headers=blink.auth.header,
            reqtype="get",
            json_resp=True,
        )

        if not isinstance(response, dict):
            print("Blink returned an unexpected response.")
            return

        events = response.get("media", [])

        if not events:
            print("No recent media events were returned.")
            return

        events.sort(
            key=lambda event: event.get("created_at", ""),
            reverse=True,
        )

        event = events[0]

        print(f"\nBlink returned {len(events)} events on this page.")
        print("\nNewest raw event:")
        print("-" * 70)
        print(json.dumps(event, indent=2, sort_keys=True))
        print("-" * 70)

        matches = find_candidate_fields(event)

        print("\nPossible review/view-status fields:")

        
        if matches:
            for field_path, field_value in matches:
                print(f"  {field_path}: {field_value!r}")
        else:
            print("  None found.")


if __name__ == "__main__":
    asyncio.run(main())