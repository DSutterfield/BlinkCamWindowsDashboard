"""
capability_matrix.py

Create compact CSV and text capability matrices from the newest JSON report
written by capability_probe.py.

This program does not contact Blink and does not issue camera commands.

Usage:
    python capability_matrix.py
    python capability_matrix.py path\\to\\capability_probe_report.json
"""

# =============================================================================
# Change history
#
# 2026-07-28 — Dan / Sage
#     Created the capability matrix from previously collected probe data.
#     The program remains read-only and does not contact Blink.
#
#     Added CSV and fixed-width text reports for comparing device families,
#     blinkpy classes, status values, and exposed methods.
#
#     Changed the text-report encoding for reliable display in Windows tools.
# =============================================================================from __future__ import annotations

import csv
import datetime as dt
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

PROBE_REPORT_DIR = Path("reports/capability_probe")
OUTPUT_DIR = Path("reports/capability_matrix")


def newest_probe_report() -> Path:
    """Return the most recently modified capability-probe JSON report."""    
    # 2026-07-28 — When no report is named on the command line, use the
    # newest successfully written probe report as the matrix source.
    # Modification time is used because a report may have been copied,
    # restored, or supplied with a filename that does not reflect its age.
    reports = sorted(
        PROBE_REPORT_DIR.glob("capability_probe_*.json"),
        key=lambda path: path.stat().st_mtime,
    )
    if not reports:
        raise FileNotFoundError(
            f"No capability-probe JSON reports were found in "
            f"{PROBE_REPORT_DIR.resolve()}"
        )
    return reports[-1]


def load_report(path: Path) -> dict[str, Any]:
    """Load a JSON report and verify its basic capability-probe structure."""
    # 2026-07-28 — Include the UTF-8 signature so Windows text utilities can
    # recognize the file encoding without relying on their default code page.
    
    with path.open("r", encoding="utf-8-sig") as report_file:
        report = json.load(report_file)

    if not isinstance(report, dict):
        raise ValueError("The probe report is not a JSON object.")
    if "cameras" not in report or "systems" not in report:
        raise ValueError(
            "The JSON file does not appear to be a capability-probe report."
        )
    return report


def value_or_blank(value: Any) -> Any:
    """Convert None to a blank field without changing other values."""
    return "" if value is None else value


def bool_text(value: Any) -> str:
    """Format booleans as Yes or No while preserving unexpected values."""
    if value is True:
        return "Yes"
    if value is False:
        return "No"
    if value is None:
        return ""
    return str(value)


def normalized_device_type(camera: dict[str, Any]) -> str:
    """Return a stable, human-readable device type for report display."""
    python_class = str(camera.get("python_class", ""))
    attributes = camera.get("normalized_attributes", {}) or {}
    raw_type = str(attributes.get("type") or "").lower()

    if python_class == "BlinkDoorbell":
        return "Blink Doorbell"
    if python_class == "BlinkCameraMini":
        return "Blink Mini"
        # All BlinkCamera objects in the current inventory are Outdoor cameras.
        # Revisit this label if Indoor, XT, or another standard family is added.
    if python_class == "BlinkCamera":
        return "Blink Outdoor Camera"
    return raw_type or python_class or "Unknown"


def make_row(camera: dict[str, Any]) -> dict[str, Any]:
    """Flatten one camera report into one capability-matrix row."""
    attributes = camera.get("normalized_attributes", {}) or {}
    capabilities = camera.get("capabilities_inferred", {}) or {}

    raw_name = str(
        attributes.get("name")
        or camera.get("dictionary_key")
        or ""
    )
    trimmed_name = raw_name.strip()

    return {
        "Network": value_or_blank(attributes.get("sync_module")),
        "Device": trimmed_name,
        "NameWhitespaceWarning": (
            "Leading/trailing whitespace"
            if raw_name != trimmed_name
            else ""
        ),
        "DisplayType": normalized_device_type(camera),
        "PythonClass": value_or_blank(camera.get("python_class")),
        "RawType": value_or_blank(attributes.get("type")),
        "Firmware": value_or_blank(attributes.get("version")),
        "MotionEnabled": bool_text(attributes.get("motion_enabled")),
        "MotionDetected": bool_text(attributes.get("motion_detected")),
        "BatteryState": value_or_blank(attributes.get("battery")),
        "BatteryLevel": value_or_blank(attributes.get("battery_level")),
        "BatteryVoltageRaw": value_or_blank(attributes.get("battery_voltage")),
        "TemperatureF": value_or_blank(attributes.get("temperature")),
        "TemperatureC": value_or_blank(attributes.get("temperature_c")),
        "WiFiStrength": value_or_blank(attributes.get("wifi_strength")),
        "SyncSignalStrength": value_or_blank(
            attributes.get("sync_signal_strength")
        ),
        "SnapshotMethod": bool_text(
            capabilities.get("snapshot_command_exposed")
        ),
        "RecordMethod": bool_text(
            capabilities.get("record_command_exposed")
        ),
        "MotionControlMethod": bool_text(
            capabilities.get("motion_control_exposed")
        ),
        "LiveViewMethod": bool_text(
            capabilities.get("liveview_request_exposed")
        ),
        "LiveStreamMethod": bool_text(
            capabilities.get("livestream_initialization_exposed")
        ),
        "NightVisionReadMethod": bool_text(
            capabilities.get("night_vision_read_member_exposed")
        ),
        "NightVisionWriteMethod": bool_text(
            capabilities.get("night_vision_write_member_exposed")
        ),
        "NightVisionKnownFamily": bool_text(
            capabilities.get("night_vision_product_type_known")
        ),
        "ThumbnailCachedBytes": value_or_blank(
            camera.get("cached_image_bytes")
        ),
    }


def make_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Build matrix rows and sort them by network and device name."""

    rows = [make_row(camera) for camera in report.get("cameras", [])]
    return sorted(
        rows,
        key=lambda row: (
            str(row["Network"]).lower(),
            str(row["Device"]).lower(),
        ),
    )


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    """Write the complete matrix as an Excel-friendly UTF-8 CSV file."""
    if not rows:
        raise ValueError("The report contains no cameras.")
        # The UTF-8 byte-order mark helps Excel recognize the file encoding.
        with path.open("w", newline="", encoding="utf-8-sig") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)


def compact(value: Any, width: int) -> str:
    """Format a value to a fixed width, shortening long text with an ellipsis."""
    text = str(value_or_blank(value))

    # 2026-07-28 — Use three ordinary periods instead of the Unicode
    # ellipsis character. This prevents corrupted display when a Windows
    # program interprets the text file using a non-UTF-8 code page.
    if len(text) > width:
        if width <= 3:
            return "." * width
        return text[: width - 3] + "..."

    return text.ljust(width)

def write_text(
    report: dict[str, Any],
    rows: list[dict[str, Any]],
    source_path: Path,
    path: Path,
) -> None:
    """Write the compact text matrix and its diagnostic summaries."""

    family_counts = Counter(str(row["RawType"]) for row in rows)
    class_counts = Counter(str(row["PythonClass"]) for row in rows)

    systems = report.get("systems", []) or []
    online_count = sum(system.get("online") is True for system in systems)
    armed_count = sum(system.get("armed") is True for system in systems)
    local_storage_count = sum(
        bool((system.get("attributes") or {}).get("local_storage"))
        for system in systems
    )

    columns = [
        ("Network", 10),
        ("Device", 24),
        ("DisplayType", 20),
        ("RawType", 8),
        ("MotionEnabled", 7),
        ("BatteryState", 7),
        ("TemperatureF", 6),
        ("WiFiStrength", 6),
        ("SyncSignalStrength", 6),
        ("LiveViewMethod", 7),
    ]

    lines: list[str] = []
    lines.append("BLINK DEVICE CAPABILITY MATRIX")
    lines.append("=" * 118)
    lines.append(f"Source report: {source_path}")
    lines.append(f"Generated: {dt.datetime.now().astimezone().isoformat()}")
    lines.append(
        f"Systems: {len(systems)}  Online: {online_count}  "
        f"Armed: {armed_count}  "
        f"Local storage enabled: {local_storage_count}"
    )
    lines.append(f"Cameras: {len(rows)}")
    lines.append("")

    lines.append(" | ".join(compact(name, width) for name, width in columns))
    lines.append("-+-".join("-" * width for _, width in columns))
    for row in rows:
        lines.append(
            " | ".join(
                compact(row[name], width) for name, width in columns
            )
        )

    lines.append("")
    lines.append("RAW DEVICE FAMILIES")
    lines.append("-" * 72)
    for family, count in sorted(family_counts.items()):
        lines.append(f"{family or '<blank>'}: {count}")

    lines.append("")
    lines.append("BLINKPY CLASSES")
    lines.append("-" * 72)
    for class_name, count in sorted(class_counts.items()):
        lines.append(f"{class_name or '<blank>'}: {count}")

    lines.append("")
    lines.append("NAME WARNINGS")
    lines.append("-" * 72)
    warning_rows = [row for row in rows if row["NameWhitespaceWarning"]]
    if warning_rows:
        for row in warning_rows:
            lines.append(
                f"{row['Network']} / {row['Device']}: "
                f"{row['NameWhitespaceWarning']}"
            )
    else:
        lines.append("None")

    lines.append("")
    lines.append("INTERPRETATION NOTE")
    lines.append("-" * 72)
    lines.append(
        "A method marked Yes means the installed blinkpy class exposes that "
        "method. It does not prove that Blink will accept the command for the "
        "specific device. Command support must be verified later with "
        "controlled tests."
    )

    with path.open("w", encoding="utf-8") as text_file:
        text_file.write("\n".join(lines) + "\n")


def main() -> int:
    """Select the input report, write both outputs, and return an exit code."""
    try:
        source_path = (
            Path(sys.argv[1]) if len(sys.argv) > 1 else newest_probe_report()
        )
        report = load_report(source_path)
        rows = make_rows(report)

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_path = OUTPUT_DIR / f"capability_matrix_{stamp}.csv"
        text_path = OUTPUT_DIR / f"capability_matrix_{stamp}.txt"

        write_csv(rows, csv_path)
        write_text(report, rows, source_path, text_path)

        print("Capability matrix completed.")
        print(f"Source: {source_path}")
        print(f"CSV:    {csv_path}")
        print(f"Text:   {text_path}")
        print()
        print(f"Devices summarized: {len(rows)}")
        return 0

    except KeyboardInterrupt:
        print("\nCapability matrix cancelled.")
        return 130
    except Exception as error:
        print(
            f"Capability matrix failed: {type(error).__name__}: {error}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
