"""
controller_api.py

Blink Management System - Pi Controller API

Provides the network interface between the Raspberry Pi Blink Controller
and the Windows Management Console.

API Version: 1
"""

from fastapi import FastAPI, HTTPException


app = FastAPI(
    title="Blink Controller API",
    version="1.0",
)


@app.get("/api/v1/health")
async def health():
    """Return basic Pi Controller API health information."""
    return {
        "status": "ok",
        "controller": "blink-controller",
        "api_version": "1",
    }
"""
controller_api.py

Blink Management System - Pi Controller API

Provides the network interface between the Raspberry Pi Blink Controller
and the Windows Management Console.

API Version: 1
"""

from fastapi import FastAPI


def create_app(controller):
    """Create the Controller API around an existing BlinkController."""

    app = FastAPI(
        title="Blink Controller API",
        version="1.0",
    )

    @app.get("/api/v1/health")
    async def health():
        """Return Pi Controller and Blink connection health."""

        connected = controller.blink is not None

        if connected:
            camera_count = len(controller.blink.cameras)
        else:
            camera_count = 0

        return {
            "status": "ok",
            "controller": "blink-controller",
            "api_version": "1",
            "blink_connected": connected,
            "camera_count": camera_count,
        }
    @app.get("/api/v1/devices")
    async def devices():
        """Return devices known to the Pi Controller."""

        if controller.blink is None:
            raise HTTPException(
                status_code=503,
                detail="Blink controller is not connected",
            )

        result = []

        for dictionary_key, camera in controller.blink.cameras.items():
            result.append(
                {
                    "id": str(camera.camera_id),
                    "name": camera.name or dictionary_key,
                    "system_id": str(camera.sync.network_id),
                    "system_name": camera.sync.name,
                    "device_type": camera.product_type,
                    "class_name": camera.__class__.__name__,
                    "serial": camera.serial,
                    "firmware_version": camera.version,
                    "motion_enabled": camera.motion_enabled,
                    "online": camera.online,
                    "battery": camera.battery,
                }
            )

        return {
            "count": len(result),
            "devices": sorted(
                result,
                key=lambda device: (
                    device["system_name"].lower(),
                    device["name"].lower(),
                ),
            ),
        }

    @app.get("/api/v1/systems")
    async def systems():
        """Return Blink systems known to the Pi Controller."""

        if controller.blink is None:
            raise HTTPException(
                status_code=503,
                detail="Blink controller is not connected",
            )

        result = []

        for dictionary_key, system in controller.blink.sync.items():
            system_id = str(system.network_id)

            camera_count = sum(
                1
                for camera in controller.blink.cameras.values()
                if str(camera.sync.network_id) == system_id
            )

            result.append(
                {
                    "id": system_id,
                    "name": (system.name or dictionary_key).strip(),
                    "armed": system.arm,
                    "online": system.online,
                    "camera_count": camera_count,
                }
            )

        return {
            "count": len(result),
            "systems": sorted(
                result,
                key=lambda system: system["name"].lower(),
            ),
        }

    return app
