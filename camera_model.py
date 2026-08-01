"""
camera_model.py

Build stable, read-only camera records from BlinkPy camera objects.

The records produced here are intended to be shared by:
    - The Windows Dashboard
    - The future headless Raspberry Pi controller
    - Diagnostic and reporting programs

Developer note — 2026-07-31, Dan and Sage:
This module was created after examining representative owl, hawk, tulip,
and sedona camera records from capability_probe.py.

Important design decisions:
    1. Blink dictionary keys and raw camera names are preserved exactly
       because Blink commands may depend upon them.
    2. Cleaned names are provided separately for display and searching.
    3. Camera and network identifiers are normalized to strings because
       Blink sometimes returns them as integers and sometimes as strings.
    4. A method being exposed by BlinkPy does not prove that Blink will
       accept the command. Such capabilities are marked exposed_untested.
    5. Missing values mean not supplied or not exposed. They must not be
       interpreted as zero, false, offline, or failed.
"""

from __future__ import annotations

from typing import Any


CAPABILITY_AVAILABLE = "available"
CAPABILITY_NOT_AVAILABLE = "not_available"
CAPABILITY_EXPOSED_UNTESTED = "exposed_untested"
CAPABILITY_KNOWN_NOT_EXPOSED = "known_not_exposed"
CAPABILITY_UNKNOWN = "unknown"

# This reproduces the product-type recognition used by capability_probe.py.
KNOWN_NIGHT_VISION_PRODUCT_TYPES = {"owl", "catalina"}


def safe_getattr(obj: object, name: str, default: Any = None) -> Any:
    """Read an object attribute without allowing a property error to escape."""
    try:
        return getattr(obj, name, default)
    except Exception:
        return default


def has_method(obj: object, name: str) -> bool:
    """Return True when the installed class exposes a callable member."""
    return callable(safe_getattr(obj, name))


def normalized_id(value: Any) -> str | None:
    """Return a Blink identifier as a string, or None when it is absent."""
    if value is None:
        return None

    text = str(value).strip()
    return text or None


def camera_value(camera: object, name: str, default: Any = None) -> Any:
    """Read a value from camera.attributes, then fall back to the object.

    BlinkPy's camera.attributes dictionary provides the normalized values
    used by capability_probe.py. The object fallback provides resilience if
    a future BlinkPy release moves a value out of that dictionary.
    """
    attributes = safe_getattr(camera, "attributes", {})

    if isinstance(attributes, dict) and name in attributes:
        return attributes.get(name)

    return safe_getattr(camera, name, default)


def command_capability(camera: object, method_name: str) -> str:
    """Classify an exposed BlinkPy command without executing it."""
    if has_method(camera, method_name):
        return CAPABILITY_EXPOSED_UNTESTED

    return CAPABILITY_NOT_AVAILABLE


def value_capability(*values: Any) -> str:
    """Classify whether at least one related status value is present."""
    if any(value is not None for value in values):
        return CAPABILITY_AVAILABLE

    return CAPABILITY_NOT_AVAILABLE


def build_camera_record(
    dictionary_key: object,
    camera: object,
) -> dict[str, Any]:
    """Convert one BlinkPy camera object into a stable camera record."""
    raw_dictionary_key = str(dictionary_key)

    raw_name_value = camera_value(camera, "name", raw_dictionary_key)
    raw_name = str(raw_name_value)
    display_name = raw_name.strip()

    raw_network_value = camera_value(camera, "sync_module")
    raw_network = (
        str(raw_network_value)
        if raw_network_value is not None
        else ""
    )
    display_network = raw_network.strip()

    raw_type_value = camera_value(camera, "type")
    raw_type = (
        str(raw_type_value).strip().lower()
        if raw_type_value is not None
        else ""
    )

    battery_state = camera_value(camera, "battery")
    battery_level = camera_value(camera, "battery_level")
    battery_voltage = camera_value(camera, "battery_voltage")

    temperature_f = camera_value(camera, "temperature")
    temperature_c = camera_value(camera, "temperature_c")
    temperature_calibrated_f = camera_value(
        camera,
        "temperature_calibrated",
    )

    wifi_strength = camera_value(camera, "wifi_strength")
    sync_signal_strength = camera_value(
        camera,
        "sync_signal_strength",
    )

    night_vision_read_exposed = hasattr(type(camera), "night_vision")
    night_vision_write_exposed = has_method(
        camera,
        "async_set_night_vision",
    )
    night_vision_product_type_known = (
        raw_type in KNOWN_NIGHT_VISION_PRODUCT_TYPES
    )

    warnings: list[str] = []

    if raw_name != display_name:
        warnings.append(
            "Camera name contains leading or trailing whitespace."
        )

    if raw_network != display_network:
        warnings.append(
            "Network name contains leading or trailing whitespace."
        )

    if raw_dictionary_key != raw_name:
        warnings.append(
            "Blink dictionary key differs from the returned camera name."
        )

    if (
        night_vision_read_exposed or night_vision_write_exposed
    ) and not night_vision_product_type_known:
        warnings.append(
            "Night-vision members are exposed, but this product type "
            "is not in the probe's recognized night-vision list."
        )

    if raw_type == "hawk":
        light_control = CAPABILITY_KNOWN_NOT_EXPOSED
    else:
        light_control = CAPABILITY_UNKNOWN

    return {
        "id": normalized_id(camera_value(camera, "camera_id")),
        "dictionary_key": raw_dictionary_key,
        "raw_name": raw_name,
        "name": display_name,
        "raw_network": raw_network,
        "network": display_network,
        "network_id": normalized_id(
            camera_value(camera, "network_id")
        ),
        "raw_type": raw_type,
        "class_name": type(camera).__name__,
        "serial": normalized_id(camera_value(camera, "serial")),
        "firmware_version": normalized_id(
            camera_value(camera, "version")
        ),

        "status": {
            "motion_enabled": camera_value(
                camera,
                "motion_enabled",
            ),
            "motion_detected": camera_value(
                camera,
                "motion_detected",
            ),

            "battery": {
                "state": battery_state,
                "level": battery_level,
                "voltage_raw": battery_voltage,
            },

            "temperature": {
                "fahrenheit": temperature_f,
                "celsius": temperature_c,
                "calibrated_fahrenheit": temperature_calibrated_f,
            },

            "wifi_signal": {
                "value": wifi_strength,
                "units": None,
            },

            "sync_signal": {
                "value": sync_signal_strength,
                "units": None,
            },

            "last_record": camera_value(camera, "last_record"),
        },

        "capabilities": {
            "snapshot": command_capability(
                camera,
                "snap_picture",
            ),
            "record": command_capability(
                camera,
                "record",
            ),
            "motion_control": command_capability(
                camera,
                "async_arm",
            ),
            "thumbnail_download": command_capability(
                camera,
                "get_thumbnail",
            ),
            "video_download": command_capability(
                camera,
                "get_video_clip",
            ),
            "live_view": command_capability(
                camera,
                "get_liveview",
            ),
            "livestream": command_capability(
                camera,
                "init_livestream",
            ),

            "night_vision_read": (
                CAPABILITY_EXPOSED_UNTESTED
                if night_vision_read_exposed
                else CAPABILITY_NOT_AVAILABLE
            ),
            "night_vision_write": (
                CAPABILITY_EXPOSED_UNTESTED
                if night_vision_write_exposed
                else CAPABILITY_NOT_AVAILABLE
            ),
            "night_vision_product_type_known":
                night_vision_product_type_known,

            "battery_status": value_capability(
                battery_state,
                battery_level,
                battery_voltage,
            ),
            "temperature": value_capability(
                temperature_f,
                temperature_c,
                temperature_calibrated_f,
            ),
            "wifi_signal": value_capability(wifi_strength),
            "sync_signal": value_capability(
                sync_signal_strength
            ),

            # Well House is a Mini 2 with a controllable light in the
            # official Blink app, but no corresponding BlinkPy interface
            # has yet been found.
            "light_control": light_control,

            # Blink is experimenting with AI clip evaluations. No stable
            # data or control interface has yet been identified.
            "ai_clip_evaluation":
                CAPABILITY_KNOWN_NOT_EXPOSED,
        },

        "warnings": warnings,
    }


def build_camera_records(blink: object) -> list[dict[str, Any]]:
    """Build normalized records for every camera discovered by BlinkPy."""
    cameras = safe_getattr(blink, "cameras", {}) or {}

    return [
        build_camera_record(dictionary_key, camera)
        for dictionary_key, camera in cameras.items()
    ]
