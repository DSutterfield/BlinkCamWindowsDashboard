"""
Read-only Blink capability inventory.

Creates timestamped JSON and text reports under:
    reports/capability_probe/

The probe does not arm/disarm, change motion settings, request snapshots,
record clips, start live view, download media, or alter local storage.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import getpass
import json
import logging
import sys
from pathlib import Path
from typing import Any

from aiohttp import ClientSession
from blinkpy.auth import Auth, BlinkTwoFARequiredError
from blinkpy.blinkpy import Blink


CREDS_PATH = Path("config/credentials.json")
REPORT_DIR = Path("reports/capability_probe")
REFRESH_RATE_SECONDS = 60
MEDIA_LOOKBACK_HOURS = 24       # Set to 0 to skip media metadata.
MEDIA_PAGE_STOP = 2             # blinkpy range(1, stop): 2 means page 1 only.

SENSITIVE_WORDS = (
    "password", "token", "authorization", "cookie", "csrf", "secret"
)


def sensitive_key(key: object) -> bool:
    """Return True for dictionary keys that probably contain secrets."""
    text = str(key).lower()
    return any(word in text for word in SENSITIVE_WORDS)


def json_safe(value: Any, depth: int = 0, seen: set[int] | None = None) -> Any:
    """Convert Blink/Python values to sanitized JSON-compatible values."""
    if seen is None:
        seen = set()

    if depth > 10:
        return "<maximum depth reached>"

    if value is None or isinstance(value, (bool, int, float, str)):
        return value

    if isinstance(value, (dt.datetime, dt.date, dt.time)):
        return value.isoformat()

    if isinstance(value, Path):
        return str(value)

    if isinstance(value, bytes):
        return {"_type": "bytes", "length": len(value)}

    object_id = id(value)
    if object_id in seen:
        return "<circular reference>"

    if isinstance(value, dict):
        seen.add(object_id)
        result: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            result[key_text] = (
                "<redacted>"
                if sensitive_key(key_text)
                else json_safe(item, depth + 1, seen)
            )
        seen.remove(object_id)
        return result

    if isinstance(value, (list, tuple, set, frozenset)):
        seen.add(object_id)
        result = [json_safe(item, depth + 1, seen) for item in value]
        seen.remove(object_id)
        return result

    items_method = getattr(value, "items", None)
    if callable(items_method):
        try:
            return json_safe(dict(items_method()), depth + 1, seen)
        except Exception:
            pass

    try:
        return str(value)
    except Exception:
        return repr(value)


def object_state(obj: object, excluded: set[str]) -> dict[str, Any]:
    """Return useful object state without back-references or secret fields."""
    return {
        key: json_safe(value)
        for key, value in vars(obj).items()
        if key not in excluded and not sensitive_key(key)
    }


def has_method(obj: object, name: str) -> bool:
    """Return True when the installed class exposes a callable member."""
    try:
        return callable(getattr(obj, name, None))
    except Exception:
        return False


def load_login_data() -> dict[str, Any]:
    """Use the existing saved credentials, or prompt on the first run."""
    if CREDS_PATH.exists():
        with CREDS_PATH.open("r", encoding="utf-8") as file:
            data = json.load(file)
        if not isinstance(data, dict):
            raise ValueError(f"{CREDS_PATH} does not contain a JSON object.")
        print(f"Using saved credentials from {CREDS_PATH}")
        return data

    print(f"{CREDS_PATH} was not found.")
    username = input("Blink email: ").strip()
    password = getpass.getpass("Blink password: ")
    if not username or not password:
        raise ValueError("Blink email and password are required.")
    return {"username": username, "password": password}


async def connect(session: ClientSession) -> Blink:
    """Authenticate and initialize blinkpy, including 2FA when required."""
    blink = Blink(refresh_rate=REFRESH_RATE_SECONDS, session=session)
    blink.auth = Auth(load_login_data(), no_prompt=True, session=session)

    try:
        started = await blink.start()
    except BlinkTwoFARequiredError:
        print("\nBlink requires two-factor authentication.")
        code = input("Enter the Blink 2FA code: ").strip()
        if not code:
            raise RuntimeError("No 2FA code was entered.")
        started = await blink.send_2fa_code(code)

    if not started or not blink.available:
        raise RuntimeError("Blink login/setup did not complete successfully.")

    CREDS_PATH.parent.mkdir(parents=True, exist_ok=True)
    await blink.save(str(CREDS_PATH))
    print(f"Refreshed credentials saved to {CREDS_PATH}")
    return blink


def camera_capabilities(camera: object) -> dict[str, Any]:
    """Infer exposed members without issuing any camera command."""
    product_type = getattr(camera, "product_type", None)
    return {
        "snapshot_command_exposed": has_method(camera, "snap_picture"),
        "record_command_exposed": has_method(camera, "record"),
        "motion_control_exposed": has_method(camera, "async_arm"),
        "thumbnail_download_exposed": has_method(camera, "get_thumbnail"),
        "video_download_exposed": has_method(camera, "get_video_clip"),
        "liveview_request_exposed": has_method(camera, "get_liveview"),
        "livestream_initialization_exposed": has_method(camera, "init_livestream"),
        "night_vision_read_member_exposed": hasattr(type(camera), "night_vision"),
        "night_vision_write_member_exposed": has_method(
            camera, "async_set_night_vision"
        ),
        "night_vision_product_type_known": product_type
        in {
            "catalina",
            "hawk",
            "owl",
            "sedona",
            "tulip",
        },
        "temperature_value_present": getattr(camera, "temperature", None) is not None,
        "battery_value_present": any(
            value is not None
            for value in (
                getattr(camera, "battery_state", None),
                getattr(camera, "battery_level", None),
                getattr(camera, "_battery_voltage", None),
            )
        ),
        "wifi_strength_present": getattr(camera, "wifi_strength", None) is not None,
        "sync_signal_strength_present": getattr(
            camera, "sync_signal_strength", None
        ) is not None,
    }


def collect_systems(blink: Blink) -> list[dict[str, Any]]:
    """Collect normalized and diagnostic state for every system/module."""
    systems: list[dict[str, Any]] = []

    for dictionary_key, sync in blink.sync.items():
        try:
            online = sync.online
        except Exception as error:
            online = f"<error: {error}>"

        try:
            armed = sync.arm
        except Exception as error:
            armed = f"<error: {error}>"

        systems.append(
            {
                "dictionary_key": dictionary_key,
                "python_class": type(sync).__name__,
                "available": getattr(sync, "available", None),
                "online": online,
                "armed": armed,
                "attributes": json_safe(getattr(sync, "attributes", {})),
                "camera_names": list(getattr(sync, "cameras", {}).keys()),
                "summary": json_safe(getattr(sync, "summary", None)),
                "network_info": json_safe(getattr(sync, "network_info", None)),
                "local_storage_internal_state": json_safe(
                    getattr(sync, "_local_storage", None)
                ),
                "object_state": object_state(
                    sync,
                    excluded={
                        "blink", "cameras", "motion", "last_records", "_names_table"
                    },
                ),
            }
        )

    return systems


def collect_cameras(blink: Blink) -> list[dict[str, Any]]:
    """Collect normalized and diagnostic state for every camera."""
    cameras: list[dict[str, Any]] = []

    for dictionary_key, camera in blink.cameras.items():
        cached_image = getattr(camera, "_cached_image", None) or b""
        cached_video = getattr(camera, "_cached_video", None) or b""

        cameras.append(
            {
                "dictionary_key": dictionary_key,
                "python_class": type(camera).__name__,
                "normalized_attributes": json_safe(
                    getattr(camera, "attributes", {})
                ),
                "capabilities_inferred": camera_capabilities(camera),
                "object_state": object_state(
                    camera,
                    excluded={"sync", "_cached_image", "_cached_video"},
                ),
                "cached_image_bytes": len(cached_image),
                "cached_video_bytes": len(cached_video),
            }
        )

    return cameras


async def collect_media(blink: Blink) -> dict[str, Any]:
    """Read one page of recent metadata without downloading any clip."""
    if MEDIA_LOOKBACK_HOURS <= 0:
        return {
            "enabled": False,
            "reason": "MEDIA_LOOKBACK_HOURS is 0",
            "items": [],
            "field_inventory": [],
        }

    since = dt.datetime.now() - dt.timedelta(hours=MEDIA_LOOKBACK_HOURS)
    since_text = since.strftime("%Y/%m/%d %H:%M:%S")

    try:
        items = await blink.get_videos_metadata(
            since=since_text,
            stop=MEDIA_PAGE_STOP,
        )
        fields = sorted(
            {
                str(key)
                for item in items
                if isinstance(item, dict)
                for key in item.keys()
            }
        )
        return {
            "enabled": True,
            "lookback_hours": MEDIA_LOOKBACK_HOURS,
            "page_stop": MEDIA_PAGE_STOP,
            "item_count": len(items),
            "field_inventory": fields,
            "items": json_safe(items),
        }
    except Exception as error:
        return {
            "enabled": True,
            "lookback_hours": MEDIA_LOOKBACK_HOURS,
            "page_stop": MEDIA_PAGE_STOP,
            "error": f"{type(error).__name__}: {error}",
            "field_inventory": [],
            "items": [],
        }


async def build_report(blink: Blink) -> dict[str, Any]:
    """Assemble the complete report."""
    try:
        notifications = await blink.get_status()
    except Exception as error:
        notifications = {"_error": f"{type(error).__name__}: {error}"}

    return {
        "probe": {
            "generated_local": dt.datetime.now().astimezone().isoformat(),
            "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "program": Path(__file__).name,
            "read_only_design": True,
            "media_lookback_hours": MEDIA_LOOKBACK_HOURS,
        },
        "blink_account": {
            "blinkpy_version": getattr(blink, "version", None),
            "available": getattr(blink, "available", None),
            "account_id": getattr(blink, "account_id", None),
            "client_id": getattr(blink, "client_id", None),
            "user_id": getattr(blink, "user_id", None),
            "network_ids": json_safe(getattr(blink, "network_ids", [])),
            "last_refresh": getattr(blink, "last_refresh", None),
            "refresh_rate_seconds": getattr(blink, "refresh_rate", None),
        },
        "counts": {
            "systems": len(blink.sync),
            "cameras": len(blink.cameras),
        },
        "notification_settings": json_safe(notifications),
        "systems": collect_systems(blink),
        "cameras": collect_cameras(blink),
        "cloud_media_metadata": await collect_media(blink),
        "raw_setup_data": {
            "homescreen": json_safe(getattr(blink, "homescreen", {})),
            "networks": json_safe(getattr(blink, "networks", {})),
        },
    }


def text_report(report: dict[str, Any]) -> str:
    """Build a compact human-readable summary."""
    lines: list[str] = [
        "BLINK CAPABILITY PROBE",
        "=" * 72,
        f"Generated: {report['probe']['generated_local']}",
        f"blinkpy version: {report['blink_account']['blinkpy_version']}",
        (
            f"Systems: {report['counts']['systems']}    "
            f"Cameras: {report['counts']['cameras']}"
        ),
        "",
        "SYSTEMS / SYNC MODULES",
        "-" * 72,
    ]

    for system in report["systems"]:
        lines.extend(
            [
                f"{system['dictionary_key']} ({system['python_class']})",
                f"  available: {system['available']}",
                f"  online: {system['online']}",
                f"  armed: {system['armed']}",
            ]
        )
        for key, value in system["attributes"].items():
            lines.append(f"  {key}: {value}")
        lines.append("  cameras: " + ", ".join(system["camera_names"]))
        lines.append("")

    lines.extend(["CAMERAS", "-" * 72])
    for camera in report["cameras"]:
        lines.append(f"{camera['dictionary_key']} ({camera['python_class']})")
        lines.append("  Normalized attributes:")
        for key, value in camera["normalized_attributes"].items():
            lines.append(f"    {key}: {value}")
        lines.append("  Inferred capabilities:")
        for key, value in camera["capabilities_inferred"].items():
            lines.append(f"    {key}: {value}")
        lines.append(f"  cached_image_bytes: {camera['cached_image_bytes']}")
        lines.append(f"  cached_video_bytes: {camera['cached_video_bytes']}")
        lines.append("")

    media = report["cloud_media_metadata"]
    lines.extend(
        [
            "CLOUD MEDIA METADATA",
            "-" * 72,
            f"enabled: {media.get('enabled')}",
            f"item_count: {media.get('item_count', 0)}",
            "fields returned: " + ", ".join(media.get("field_inventory", [])),
        ]
    )
    if media.get("error"):
        lines.append(f"error: {media['error']}")

    lines.extend(
        [
            "",
            "The matching JSON file contains the sanitized raw data.",
            "No control commands were intentionally issued by this probe.",
            "",
        ]
    )
    return "\n".join(lines)


def write_reports(report: dict[str, Any]) -> tuple[Path, Path]:
    """Write timestamped JSON and text files."""
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = REPORT_DIR / f"capability_probe_{stamp}.json"
    text_path = REPORT_DIR / f"capability_probe_{stamp}.txt"

    with json_path.open("w", encoding="utf-8") as file:
        json.dump(report, file, indent=2, ensure_ascii=False)

    with text_path.open("w", encoding="utf-8") as file:
        file.write(text_report(report))

    return json_path, text_path


async def async_main() -> int:
    """Run the probe."""
    print("Blink capability probe")
    print("----------------------")
    print("Mode: read-only inventory\n")

    async with ClientSession() as session:
        blink = await connect(session)
        print(
            f"\nConnected. Found {len(blink.sync)} system(s) "
            f"and {len(blink.cameras)} camera(s)."
        )
        print("Collecting report data...")
        report = await build_report(blink)
        json_path, text_path = write_reports(report)

    print("\nCapability probe completed.")
    print(f"JSON report: {json_path}")
    print(f"Text report: {text_path}")
    return 0


def main() -> int:
    """Entry point with readable error handling."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        return asyncio.run(async_main())
    except KeyboardInterrupt:
        print("\nProbe cancelled.")
        return 130
    except json.JSONDecodeError as error:
        print(f"\nCredential JSON error: {error}", file=sys.stderr)
        return 3
    except Exception as error:
        logging.exception("Capability probe failed")
        print(
            f"\nProbe failed: {type(error).__name__}: {error}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
