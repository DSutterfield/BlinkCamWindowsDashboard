"""
controller_api.py

Blink Management System - Pi Controller API

Provides the network interface between the Raspberry Pi Blink Controller
and the Windows Management Console.

API Version: 1
"""

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from pathlib import Path
from fastapi.responses import FileResponse
from catalog_store import list_clips

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

class MotionRequest(BaseModel):
    enabled: bool

class SystemArmRequest(BaseModel):
    armed: bool

def create_app(controller):
    """Create the Controller API around an existing BlinkController."""

    app = FastAPI(
        title="Blink Controller API",
        version="1.0",
    )

    @app.get("/api/v1/health")
    async def health():
        """Return Pi Controller, storage, and Blink connection health."""

        connected = controller.blink is not None

        if connected:
            camera_count = len(controller.blink.cameras)
        else:
            camera_count = 0

        archive_available = controller.archive_dir.is_dir()
        catalog_available = controller.catalog_db_path.is_file()

        return {
            "status": (
                "ok"
                if archive_available and catalog_available
                else "degraded"
            ),
            "controller": "blink-controller",
            "api_version": "1",
            "blink_connected": connected,
            "blink_cloud_reachable": (
                controller.blink_cloud_reachable
            ),
            "last_poll_success_at": (
                controller.last_poll_success_at
            ),
            "last_poll_error": controller.last_poll_error,
            "archive_available": archive_available,
            "catalog_available": catalog_available,
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

    @app.put("/api/v1/systems/{system_id}/arm")
    async def set_system_arm(system_id: str, request: SystemArmRequest):
        """Arm or disarm one Blink system."""

        if controller.blink is None:
            raise HTTPException(
                status_code=503,
                detail="Blink controller is not connected",
            )

        system = next(
            (
                system
                for system in controller.blink.sync.values()
                if str(system.network_id) == system_id
            ),
            None,
        )

        if system is None:
            raise HTTPException(
                status_code=404,
                detail=f"System {system_id} was not found",
            )

        previous_state = system.arm

        try:
            response = await system.async_arm(request.armed)
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Blink system arm command failed: {exc}",
            ) from exc

        if response is None:
            raise HTTPException(
                status_code=502,
                detail="Blink did not return a response",
            )

        # Refresh this system's network information so the returned
        # state comes back from Blink rather than from our request.
        await system.get_network_info()

        return {
            "id": str(system.network_id),
            "name": system.name.strip(),
            "previous_armed": previous_state,
            "armed": system.arm,
        }

    @app.put("/api/v1/devices/{device_id}/motion")
    async def set_device_motion(device_id: str, request: MotionRequest):
        """Enable or disable motion detection for one camera."""

        if controller.blink is None:
            raise HTTPException(
                status_code=503,
                detail="Blink controller is not connected",
            )

        camera = next(
            (
                camera
                for camera in controller.blink.cameras.values()
                if str(camera.camera_id) == device_id
            ),
            None,
        )

        if camera is None:
            raise HTTPException(
                status_code=404,
                detail=f"Device {device_id} was not found",
            )

        previous_state = camera.motion_enabled

        try:
            response = await camera.async_arm(request.enabled)
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Blink motion command failed: {exc}",
            ) from exc

        if response is None:
            raise HTTPException(
                status_code=502,
                detail="Blink did not return a response",
            )

        # BlinkPy sends the command but does not update this cached field.
        # Keep our controller state synchronized with the accepted request.
        camera.motion_enabled = request.enabled

        return {
            "id": str(camera.camera_id),
            "name": camera.name.strip(),
            "previous_motion_enabled": previous_state,
            "motion_enabled": camera.motion_enabled,
        }

    @app.get("/api/v1/clips")
    def clips(
        limit: int = Query(default=100, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
    ):
        """Return locally archived recorded clips from SQLite."""

        if not controller.catalog_db_path.is_file():
            raise HTTPException(
                status_code=503,
                detail="Local clip catalog is unavailable",
            )

        try:
            return list_clips(
                db_path=controller.catalog_db_path,
                limit=limit,
                offset=offset,
            )
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Clip catalog query failed: {exc}",
            ) from exc

    @app.get("/api/v1/clips/{filename}/video")
    async def clip_video(filename: str):
        """Return one locally archived MP4 clip."""

        if (
            "/" in filename
            or "\\" in filename
            or Path(filename).name != filename
            or Path(filename).suffix.lower() != ".mp4"
        ):
            raise HTTPException(
                status_code=400,
                detail="Invalid clip filename",
            )

        video_path = controller.archive_dir / filename

        if not video_path.is_file():
            raise HTTPException(
                status_code=404,
                detail="Clip video was not found",
            )

        return FileResponse(
            path=video_path,
            media_type="video/mp4",
            filename=filename,
            content_disposition_type="inline",
        )

    @app.get("/api/v1/clips/{filename}/thumbnail")
    async def clip_thumbnail(filename: str):
        """Return the cached thumbnail for one locally archived clip."""

        if (
            "/" in filename
            or "\\" in filename
            or Path(filename).name != filename
            or Path(filename).suffix.lower() != ".mp4"
        ):
            raise HTTPException(
                status_code=400,
                detail="Invalid clip filename",
            )

        thumbnail_name = f"{Path(filename).stem}.jpg"
        thumbnail_path = controller.clip_thumbs_dir / thumbnail_name

        if not thumbnail_path.is_file():
            raise HTTPException(
                status_code=404,
                detail="Clip thumbnail was not found",
            )

        return FileResponse(
            path=thumbnail_path,
            media_type="image/jpeg",
            filename=thumbnail_name,
            content_disposition_type="inline",
        )

    return app
